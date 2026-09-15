# tests/

pytest, every LLM call mocked via `monkeypatch.setattr(<agent module>,
"call_llm", ...)`. No `ANTHROPIC_API_KEY` needed to run this suite.

- `conftest.py` -- shared fixtures: `sample_clauses`, `sample_rules`.
- `test_extractor.py`, `test_risk_analyzer.py`, `test_summarizer.py` --
  one agent each, in isolation.
- `test_rules_loader.py` -- default rule set loads and validates.
- `test_llm.py` -- the markdown-fence-stripping JSON parser.
- `test_api.py` -- FastAPI layer via `TestClient`: UI served, `/api/info`,
  upload/LLM failures mapping to 400/502/503/504, and that the pipeline
  runs off the event loop (patches `main.run_review`).
- `test_graph.py` -- end-to-end through `graph.run_review`, including the
  skip-Risk-Analyzer-when-no-clauses branch (asserts `call_llm` is never
  called on that path, not just that the result looks right).

Pattern for a new agent test: monkeypatch `call_llm` on the agent's own
module object (not on `clauseguard.llm`) -- each agent module imported
`call_llm` by name at the top, so patching the origin module doesn't
affect the copy the agent already bound.
