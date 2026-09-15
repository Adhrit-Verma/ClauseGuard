# clauseguard/agents/

The three agents plus the graph that wires them together. Each agent is a
plain function: (validated input) -> LLM call -> (validated Pydantic
output). None of them touch the Anthropic SDK directly -- they call
`clauseguard.llm.call_llm`, which is what tests monkeypatch.

- `extractor.py` -- `extract_clauses(document_text) -> ExtractionResult`.
  One LLM call, asks for clause segmentation + typing as JSON.
- `risk_analyzer.py` -- `analyze_risk(clauses, rules) -> RiskAnalysisResult`.
  Filters `rules` down to only the ones whose `applies_to` matches a
  clause type actually present, and skips the LLM call entirely if there
  are no clauses or no applicable rules -- see the conditional routing note
  below.
- `summarizer.py` -- `summarize(clauses, findings) -> ExecutiveSummary`.
  Always runs, even with zero clauses/findings (produces a "nothing found"
  summary).
- `graph.py` -- LangGraph `StateGraph` wiring: `extract -> [analyze?] ->
  summarize -> END`. `ReviewState` is the shared TypedDict all three nodes
  read/write. `run_review(document_text, on_stage=None)` is the single
  entrypoint `main.py` and `scripts/demo.py` both call. `on_stage`, if
  given, is called with a `ReviewStatus` each time the *next* stage is
  known -- driven by iterating `app.stream(state)` instead of a single
  `app.invoke(state)`, so a caller (`main.py`) can persist progress
  between LLM calls, not just once at the end. `route_after_extract`'s
  zero-clauses branch is handled here too: if `extract` finds nothing,
  `on_stage` is called with `SUMMARIZING` directly, matching the routing
  below -- see FLOW.md for the full stage-transition diagram.

## Why a graph and not three function calls in a row

Two things a flat script handles poorly as this grows: conditional
routing (skip Risk Analyzer entirely when Extractor found zero clauses --
`route_after_extract` in `graph.py`) and a shared state object every node
reads/writes without every function needing every other function's
signature. See [FLOW.md](../../FLOW.md) for the full diagram.
