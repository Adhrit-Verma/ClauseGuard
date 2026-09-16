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
  mid-stage forever. Starting a review also sweeps failed rows older than
  `CLAUSEGUARD_FAILED_TTL` (default 1h, 0 disables) so they don't pile up
  in the sidebar, while a fresh failure stays readable. `GET /reviews` lists every
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
  before `json.loads`), plus `prompt_budget(system)` -- how many prompt
  characters fit one call. Agents split long documents to it; `_call_ollama`
  refuses anything still over it, since Ollama would silently truncate. Every agent imports `call_llm` from here and every
  agent test monkeypatches it there -- agent code never knows which
  provider is active. Also owns metrics: `collect_calls()` (a thread-local
  context manager) records model, tokens and seconds for every call made
  inside it, and `summarize_calls()` totals them, pricing tokens with
  `CLAUSEGUARD_*_COST_PER_MTOK` (0 for local models). `main._process_review`
  wraps a whole review in one collector.

- `guardrails.py` -- the document is untrusted input that lands in prompts.
  `find_injection(text)` flags lines that read like instructions to the
  model (they go on the report as `warnings`; the review still runs, since
  refusing would be trivial to weaponize), and the agents' prompts say the
  document is data, never instructions. `redact_pii(text)` replaces obvious
  identifiers before a prompt leaves the machine -- off for local Ollama,
  on for a remote provider (`CLAUSEGUARD_REDACT_PII=auto|always|never`,
  applied in `llm.call_llm`).
- `retrieval.py` -- picks the (clause, rule) pairs the Risk Analyzer checks,
  independent of the Extractor's type labels. `candidate_pairs()` combines
  three signals: the type label, BM25 keywords (`bm25_scores`), and cosine
  similarity over embeddings (`cosine_scores`) when an embedding model is
  installed, merged with `rrf_fuse()` (reciprocal rank fusion). Embeddings
  are optional -- `llm.embed()` returns None without them and retrieval is
  keyword-only. Each pair carries how it was found (`type`/`keyword`/
  `hybrid`), which ends up on the finding as `retrieved_by`.

Subpackages: [models/](models/CLAUDE.md), [agents/](agents/CLAUDE.md),
[rules/](rules/CLAUDE.md), [storage/](storage/CLAUDE.md).
