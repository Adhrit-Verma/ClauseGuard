# clauseguard/agents/

The three agents plus the graph that wires them together. Each agent is a
plain function: (validated input) -> LLM call -> (validated Pydantic
output). None of them touch an LLM backend directly -- they call
`clauseguard.llm.call_llm`, which is what tests monkeypatch.

Speed rule for all three: output tokens are ~95% of a review's wall time
(measured), so each prompt asks the model only for what it alone can judge,
as compact JSON rows, and code fills in everything derivable. Don't add
fields to an LLM output schema that code already knows. Accuracy was
measured against the sample NDA alongside speed -- a format that saved
seconds but lost findings was rejected (see git history).

- `extractor.py` -- `extract_clauses(document_text) -> ExtractionResult`.
  Sends the document as numbered non-blank lines; the model returns one row
  per clause, `[type, start_line, confidence]` -- never clause text, never
  an end line. Each clause runs until the next one starts. Code drops
  out-of-range starts, keeps the first of duplicate starts, and snaps a
  start back one line when the line above is an unclaimed numbered heading
  (the model consistently lands one line past headings like
  "4. Indemnification."). Trailing non-clause text is absorbed into the
  last clause. Documents too long for one call are split into line chunks
  that fit both `llm.prompt_budget()` and `_MAX_LINES_PER_CALL` (a few lines
  repeated across each cut). The line cap applies even when the context
  would fit more: on long calls the model pairs clause types with the wrong
  line numbers. Starts
  keep their global line numbers, so a clause can run across a cut, and a
  start number outside the chunk it came from is ignored.
- `risk_analyzer.py` -- `analyze_risk(clauses, rules) -> RiskAnalysisResult`.
  **Retrieve:** `retrieval.candidate_pairs()` owns this (see
  [clauseguard/retrieval.py](../retrieval.py)) -- type label, BM25 keywords
  and embedding similarity, fused, in both directions so no clause goes
  unchecked. This agent just consumes the pairs it returns. **Rerank/verify:** those (clause, rule)
  pairs go out as a numbered checklist; the model must answer each row
  `[check_number, true/false, <=12-word reason]`. Skips the LLM call
  entirely if there are no pairs -- see the conditional routing note
  below. An open-ended "list the violations" prompt caught 1-2 of ~6 real
  violations; the checklist caught 5-7 in the same single call. `rule_name`
  and `severity` come from the rule set, never the model; unknown check
  numbers are ignored and duplicates keep the first answer. Checks go out in
  batches that fit `llm.prompt_budget()` and hold at most
  `MAX_CHECKS_PER_CALL` (40, so the reply fits too), each numbered from 1.
- `summarizer.py` -- `summarize(clauses, findings) -> ExecutiveSummary`.
  Always runs, even with zero clauses/findings. The model writes only
  `summary` + up to 4 `key_points`; `verdict` comes from `verdict_for()`
  (any high/critical or 3+ medium -> high_risk, any medium -> moderate,
  else low) because a small model was seen misjudging it. Findings reach
  the prompt as one line per rule with a count (`Liability cap too low (x6)`),
  so the prompt stays small however long the contract is -- this agent's
  input isn't split like the other two.
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
