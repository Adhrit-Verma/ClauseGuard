# Architecture

## Problem

Legal/procurement/compliance teams manually read long contracts to spot
risky clauses (auto-renewal traps, low liability caps, one-sided
indemnity). Slow, inconsistent between reviewers, doesn't scale.
ClauseGuard automates the first pass: extract, evaluate against a known
standard, summarize -- a human still reviews the flagged items, but they
start from a report instead of a blank document.

## Three-agent pipeline

```
PDF --> [Extractor] --> clauses --> [Risk Analyzer] --> findings --> [Summarizer] --> ExecutiveSummary
```

| Agent | Input | Job | Output |
|---|---|---|---|
| Extractor | raw document text | segment into clauses, label each by type | `ExtractionResult` (list of `Clause`) |
| Risk Analyzer | clauses + rule set | check each clause against applicable rules | `RiskAnalysisResult` (list of `RiskFinding`) |
| Summarizer | clauses + findings | synthesize a plain-English summary + verdict | `ExecutiveSummary` |

Each agent is one function, one LLM call, one Pydantic-validated output.
See [clauseguard/agents/CLAUDE.md](clauseguard/agents/CLAUDE.md) for the
actual signatures.

## Why LangGraph instead of three function calls in sequence

A plain sequential script (`extract(); analyze(); summarize()`) works for
the happy path. Two things it handles poorly as the pipeline grows:

1. **Conditional routing.** If the Extractor finds zero clauses, there's
   nothing for the Risk Analyzer to check -- calling it anyway wastes an
   LLM call and risks the model inventing findings against nothing.
   `graph.py`'s `route_after_extract` sends the state straight to
   `summarize` in that case. LangGraph expresses this as a first-class
   conditional edge; a script would need an `if` wrapped around every
   call site that might grow more branches later (skip Summarizer on
   Extractor failure, retry a node, re-run just the Risk Analyzer with a
   different rule set, etc.).
2. **Shared state across agents.** All three nodes read and write one
   `ReviewState` object instead of threading positional arguments through
   an ever-growing call chain. Adding a fourth agent means adding a node
   and an edge, not touching every existing function's signature.

The honest trade-off: for exactly three agents with exactly one branch,
LangGraph is arguably more machinery than the problem needs today. It's
included here because (a) the brief calls for it, (b) it's the standard
answer to "how do you orchestrate more than one LLM call reliably," and
(c) the branch that already exists (skip-if-empty) is a preview of the
kind of routing that gets painful to hand-roll once there's more than one
of it.

## Progress tracking: a status column, polled, not a live connection

A review takes minutes on a local model. Early on, `POST /review` ran the
whole pipeline in the request and returned the finished report -- which
meant a page refresh mid-review genuinely lost the review: the browser's
only handle on it was the in-flight HTTP request, and reloading killed
that. The fix wasn't "make it faster," it was to stop treating the
client's connection as where progress lives at all.

Now `POST /review` inserts a row (`status='extracting'`) and returns its
id in well under a second; the pipeline runs afterward as a background
task and writes its own progress into that same row as it goes
(`extracting -> analyzing -> summarizing -> done`, or `failed`). The
client's only job is to remember *which id* it's watching
(`localStorage`) and ask the server for that row's current state. A
refresh, a closed tab, a different browser entirely -- all of them
recover by asking the same question: "what's the status of review N?"

The alternative was a persistent connection (WebSocket or SSE) pushing
progress to the client live. That's smoother (no poll delay, no wasted
requests) but doesn't fix the actual bug on its own -- the *server* still
needs to know a review's status independent of any one connection, or a
reconnecting client has nothing to catch up on. Once that server-side
state exists, polling it every few seconds is the smaller amount of
machinery for one browser tab at a time; a persistent-connection layer
would be worth it if reviews needed to push updates to multiple viewers
at once, which nothing here does yet.

## Structured, validated output at every stage

Every agent returns JSON, and every JSON response is validated against a
Pydantic model (`clauseguard/models/schemas.py`) before the next agent
sees it. This is the "reduce hallucination via structure" pattern: an
agent can't silently pass a malformed or half-formed object downstream --
`ExtractionResult.model_validate(data)` raises immediately if the LLM
returned something that doesn't fit the schema (wrong enum value, missing
field, wrong type).

## Configurable rule set = grounded comparison, not free-form summarization

The Risk Analyzer doesn't ask "is this risky?" in the abstract -- it
checks each clause against a specific, named rule
(`clauseguard/rules/default_rules.json`). This is the same pattern as
comparing a design against WCAG criteria: content evaluated against a
known, swappable standard, not just summarized. Swap the rules file
(`CLAUSEGUARD_RULES_FILE`) to point the same pipeline at an NDA, a vendor
SLA, or an HR policy without touching agent code.

## Stack

- **Python 3.12+, FastAPI** -- `POST /review` (upload PDF, get a
  `ReviewRecord` id immediately; the report lands on it asynchronously),
  `GET /reviews` (list with status), `GET /reviews/{id}` (poll one).
- **LangGraph** -- orchestrates the three agents as a graph (see above).
- **Ollama or Anthropic API** (`clauseguard/llm.py`) -- the reasoning
  engine inside each agent. One thin wrapper function, `call_llm`, is the
  only place either SDK/API is touched -- this is also the seam every
  test mocks.
- **pdfplumber** -- PDF text extraction.
- **Pydantic** -- schema validation at every agent hand-off.
- **SQLite** (`clauseguard/storage/db.py`) -- audit history, one table,
  stdlib `sqlite3`, no ORM.
- **pytest** -- one test file per agent, `call_llm` mocked, no live API
  calls in the suite.

## Failure modes (and what to do about them)

- **Extractor misses a clause.** Under-extraction is silent -- there's no
  ground truth to compare against at runtime. Mitigation: the `confidence`
  field on `Clause` lets the Extractor flag ambiguous matches; a
  low-confidence clause could be routed to a human-review queue instead of
  straight into risk analysis (not built yet -- the schema supports it).
- **LLM hallucinates a risk that isn't there.** The Risk Analyzer's prompt
  explicitly instructs "do not invent violations... if nothing clearly
  violates a rule, omit it," and every finding must carry `explanation`
  text tied to the actual clause. Still not a guarantee -- the next lever
  is a confidence/severity threshold below which a finding gets flagged
  "needs human review" instead of surfaced as fact.
- **Malformed JSON from the LLM.** Handled today: `parse_json_response`
  strips markdown fences, and Pydantic validation raises loudly rather
  than passing a partial object downstream. Not handled today: automatic
  retry-with-correction. A production version would retry once with the
  validation error fed back to the model before giving up.
- **Rule set doesn't match the document type.** The Risk Analyzer only
  applies rules whose `applies_to` matches a present clause type, so an
  NDA reviewed with vendor-SLA rules mostly no-ops rather than producing
  garbage findings -- but a wrong rule file still means real risks go
  unchecked. This is a configuration problem, not something the code can
  detect on its own.
- **Server restarts mid-review.** A `BackgroundTask` is in-process: if
  uvicorn is killed while one is running, that review's row is stuck at
  whatever stage it last reached -- `status` never reaches `done` or
  `failed`, and a client polling it waits forever. Not handled today:
  there's no timeout-based "reap stale in-progress reviews on startup."
  Acceptable for a single local instance; a multi-worker or multi-process
  deployment would need a real job queue (e.g. Celery/RQ) instead of an
  in-process background task, since a review started on one worker isn't
  visible to another anyway.
