# clauseguard/ (package root)

- `main.py` -- FastAPI app. `GET /` serves `static/index.html`;
  `GET /api/info` reports the active provider/model. `POST /review`
  extracts PDF text (400/422 on failure), inserts a `status='extracting'`
  row via `storage/db.py`, schedules the pipeline as a `BackgroundTask`,
  and returns 202 with that row's id **immediately** -- it does not wait
  for the review to finish. The pipeline (`_process_review`) then runs
  off-request: on success it calls `db.complete_review`, on an LLM
  failure (`OSError`/`ValueError` from `run_review`) it calls
  `db.fail_review` with a readable message; any other exception is
  logged and also marks the review failed, so a review can never sit
  mid-stage forever. `GET /reviews` lists every
  review with its current status; `GET /reviews/{id}` is what a client
  polls -- see FLOW.md for the full id-based job lifecycle and why it
  survives a browser refresh.
- `static/index.html` -- the whole web UI: upload, a step-wise progress
  tracker (extract/analyze/summarize) driven by polling `GET
  /reviews/{id}`, the report (verdict, findings by severity, clauses), and
  a past-reviews sidebar with live status badges. Vanilla JS, no build
  step. Tracks only *which* review it's watching in
  `localStorage['clauseguard:activeReviewId']` -- all progress state is
  re-fetched from the server, never cached client-side, which is what
  makes a refresh resume correctly instead of losing the review. Renders
  all model output via `textContent` since it derives from an untrusted
  PDF -- keep it that way (no `innerHTML`).
- `llm.py` -- the only file that talks to an LLM backend. Two providers,
  switched by `CLAUSEGUARD_LLM_PROVIDER` (`anthropic` or `ollama`, see the
  module docstring for defaults). Exposes `call_llm(system, user) -> str`
  and `parse_json_response(text) -> dict` (strips markdown code fences
  before `json.loads`). Every agent imports `call_llm` from here and every
  agent test monkeypatches it there -- agent code never knows which
  provider is active.

Subpackages: [models/](models/CLAUDE.md), [agents/](agents/CLAUDE.md),
[rules/](rules/CLAUDE.md), [storage/](storage/CLAUDE.md).
