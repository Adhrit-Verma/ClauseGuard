# Data Flow

A review is asynchronous end to end: `POST /review` hands back an id in
well under a second, and the three-agent pipeline runs afterward as a
background task. Progress lives in SQLite as a `status` column the client
polls -- not in server memory or a WebSocket -- so the browser can refresh,
close the tab, or lose the connection entirely and reconnect to the exact
same review later just by asking for that id again. This is the fix for
"I can't track my document after a refresh": there's nothing client-side
to lose, because the client was never the thing tracking progress.

## End-to-end: upload to a pollable, resumable review

```
1. Client            POST /review, multipart PDF upload
                            |
2. main.py           file.filename must end in .pdf, else 400
                            |
3. main.py           extract_pdf_text(data) -- pdfplumber reads every page
                            |  (400 if unreadable, 422 if no text -- e.g. a scan)
                            v
4. storage/db.py     create_review(name, now) -- INSERT with status='extracting'
                            |
5. main.py           background_tasks.add_task(_process_review, id, name, text)
                            |
6. main.py           returns 202 + ReviewRecord{id, status: "extracting", report: null}
                            |                         immediately -- step 7 hasn't
                            |                         started running yet
                            v
7. main.py (background)  _process_review(id, name, text) -- runs after the response
                          is already sent; a FastAPI BackgroundTask keeps running to
                          completion even if the client disconnects
```

Step 7 runs in a worker thread (Starlette runs a sync `BackgroundTasks`
callable via `run_in_threadpool`), so one review in progress never blocks
`GET /reviews`, `GET /api/info`, or another `POST /review` from being
served immediately -- verified in `tests/test_api.py` by timing concurrent
requests against a live review.

## Inside `_process_review` (`clauseguard/main.py`)

```
run_review(text, on_stage=<db.update_status for this id>)
        |
        +--> graph.build_graph().stream(state)   yields one update per node as it finishes
        |
        |    extract finishes  -> on_stage(ANALYZING)      [or SUMMARIZING if 0 clauses -- see below]
        |    analyze finishes  -> on_stage(SUMMARIZING)
        |    (summarize finishing has no "next stage" -- the function just returns)
        v
   returns final ReviewState{clauses, findings, summary}
        |
        +-- success --> ReviewReport(...) --> db.complete_review(id, report)  status='done'
        |
        +-- OSError (Ollama unreachable/timeout) --> db.fail_review(id, message)  status='failed'
        +-- ValueError (malformed model JSON)     --> db.fail_review(id, message)  status='failed'
```

`on_stage` is called with the stage the pipeline is *about to enter*, not
the one it just left -- so a client polling mid-review always sees where
things are heading, not a state that's already stale by the time the
response arrives. See `clauseguard/agents/CLAUDE.md` for the full
extract/analyze/summarize node behavior (unchanged from before -- `on_stage`
is threaded through `run_review` without touching the graph's own routing
logic, described in ARCHITECTURE.md).

## Status values (`ReviewStatus` in `models/schemas.py`)

```
extracting -> analyzing -> summarizing -> done
     \                          ^
      \________________________/          (skip straight here if 0 clauses found)
     \
      \--> failed   (from any stage, if the LLM call raises)
```

`GET /reviews` returns `(id, document_name, created_at, status)` for
every review, in-progress ones included -- this is what lets the sidebar
show "Extracting…" / "Failed" badges. `GET /reviews/{id}` returns the
full `ReviewRecord`: same fields plus `report` (populated once `status`
is `done`) and `error` (populated once it's `failed`).

## How the browser stays in sync

`static/index.html` keeps exactly one piece of client state for this:
`localStorage['clauseguard:activeReviewId']`, the id of whichever review
it's currently watching. On submit, on opening an in-progress review from
the sidebar, and on page load if that key is already set, it calls
`watchReview(id, ...)`, which:

1. Fetches `GET /reviews/{id}` once to get the current status (it may
   already be `done` or `failed` by the time this runs).
2. If still in progress, shows the step tracker at the right stage and
   polls `GET /reviews/{id}` every 3s, updating the stepper each time.
3. On `done`/`failed`, stops polling, clears the localStorage key, and
   renders the report or the error.

Because every one of those steps re-derives its view from what the server
just returned, a refresh mid-poll just re-enters this same function with
the same id -- there's no separate "resume" code path to keep in sync with
the normal one.

## Where validation happens

Every arrow that crosses an agent boundary inside `run_review` is a
Pydantic `model_validate(...)` call on JSON parsed out of an LLM response
(`clauseguard/llm.py:parse_json_response` strips markdown code fences
first). If the LLM's JSON doesn't match the expected schema -- wrong enum
value, missing field, wrong type -- validation raises a `ValueError`
immediately at that boundary, which `_process_review` catches and turns
into a `failed` status with a readable message. Nothing malformed is ever
handed to the next agent, and nothing malformed ever reaches the client
as a raw exception.

## Running the flow without the API

`scripts/demo.py` calls `graph.run_review(text)` directly against
`sample_docs/sample_nda.txt` -- no `on_stage`, no FastAPI, no PDF parsing,
no job tracking, just the three agents run once, synchronously, useful
for iterating on prompts or rules quickly.
