# tests/

pytest, every LLM call mocked via `monkeypatch.setattr(<agent module>,
"call_llm", ...)`. No `ANTHROPIC_API_KEY` needed to run this suite.

- `conftest.py` -- shared fixtures: `sample_clauses`, `sample_rules`.
- `test_extractor.py`, `test_risk_analyzer.py`, `test_summarizer.py` --
  one agent each, in isolation. They pin the code-side half of each
  agent: turning start lines into clause text (next start = end, snapping
  onto a skipped numbered heading, dropping bad rows), mapping numbered
  checklist answers back to clause/rule pairs with severity from the rule
  set, and computing the verdict regardless of what the model claims.
- `test_rules_loader.py` -- default rule set loads and validates.
- `test_llm.py` -- the markdown-fence-stripping JSON parser, and the
  context-overflow guard (refuses a too-long prompt before calling Ollama).
- `test_db.py` -- the review status lifecycle (extracting -> ... -> done
  or failed) directly against `storage/db.py`, plus the schema migration
  from a hand-built legacy table with no status/error columns.
- `test_api.py` -- FastAPI layer via `TestClient`: UI served, `/api/info`,
  `POST /review` returns 202 immediately in `extracting` status (patches
  `main.run_review`), and the background task's outcome (done/failed +
  message) lands on that same review id. Relies on a verified Starlette
  behavior: `TestClient.post()` doesn't return until that request's
  `BackgroundTasks` finish, so `GET /reviews/{id}` right after already
  reflects the final status -- no polling loop needed in these tests.
- `test_graph.py` -- end-to-end through `graph.run_review`, including the
  skip-Risk-Analyzer-when-no-clauses branch (asserts `call_llm` is never
  called on that path) and the `on_stage` callback's sequence of
  `ReviewStatus` values for both the normal and skip-analyze routes.

Pattern for a new agent test: monkeypatch `call_llm` on the agent's own
module object (not on `clauseguard.llm`) -- each agent module imported
`call_llm` by name at the top, so patching the origin module doesn't
affect the copy the agent already bound.
