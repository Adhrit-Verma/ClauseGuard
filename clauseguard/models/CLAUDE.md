# clauseguard/models/

Pydantic schemas (`schemas.py`) -- the contract every agent hand-off must
satisfy. If an LLM's JSON doesn't validate against one of these, the
pipeline raises right there instead of passing a malformed object to the
next agent.

- `Clause` / `ExtractionResult` -- Extractor's output. `ClauseType` enum
  caps what a clause can be labeled: commercial types (termination,
  liability, payment_terms, confidentiality, indemnity, auto_renewal,
  governing_law), employment types (compensation, notice_period,
  non_compete, ip_assignment, probation), and other. The Extractor's prompt
  lists them straight from the enum.
- `Rule` -- one entry from the configurable rule set (see
  [rules/](../rules/CLAUDE.md)). `applies_to` is a `ClauseType` hint and
  `keywords` feed the BM25 retrieval step; the Risk Analyzer checks a rule
  against clauses matching either.
- `RiskFinding` / `RiskAnalysisResult` -- Risk Analyzer's output. Links a
  finding back to both the clause (`clause_id`) and the rule it violated,
  plus `retrieved_by` (`type`/`keyword`/`hybrid`): how retrieval paired the
  two, so a finding can show why that clause was even examined.
- `ExecutiveSummary` -- Summarizer's output. `RiskVerdict` is the top-line
  low/moderate/high call.
- `ReviewReport` -- the finished result: clauses + findings +
  executive_summary + metadata, all in one object, plus `warnings` (e.g.
  the document contains text aimed at the model -- see
  [guardrails.py](../guardrails.py)). Only exists once a review reaches
  `status=done`.
- `ReviewStatus` -- the job lifecycle a review moves through:
  `extracting -> analyzing -> summarizing -> done`, or `failed` from any
  stage. Mirrors the stage names `agents/graph.py`'s `on_stage` callback
  emits -- see [agents/CLAUDE.md](../agents/CLAUDE.md) and FLOW.md.
- `ReviewRecord` -- what `POST /review` (immediately) and `GET
  /reviews/{id}` (on every poll) return: `id`, `status`, and either
  `report` (once done) or `error` (once failed) -- never both -- plus
  `metrics` (calls, tokens, model seconds, cost) once the review ends.
- `ClauseSpan`, `RiskCheck`, `SummaryDraft` -- the *raw* LLM outputs,
  deliberately smaller than the models above. Each agent validates the
  model's JSON against one of these, then builds the full `Clause` /
  `RiskFinding` / `ExecutiveSummary` by adding what code already knows
  (clause text, which rule a check was about, rule name/severity, verdict).
  `ClauseSpan` and `RiskCheck` subclass `_Row`, which also accepts a
  compact JSON row in field order (`["liability", 5, 0.9]`,
  `[1, true, "reason"]`) -- that's what the prompts ask for. Field order is
  therefore part of the contract: don't reorder those fields without
  updating the prompts. Agents read row lists through `parse_rows()`, which
  validates each row on its own and drops ones that don't fit (an invented
  clause type becomes `other` instead), so one bad row can't fail a review;
  a reply missing the list entirely is still malformed.

Adding a new clause type or a new finding field means editing this file
first -- everything downstream (rules JSON, prompts, DB storage) follows
from the schema, not the other way around.
