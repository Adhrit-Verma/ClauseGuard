# clauseguard/models/

Pydantic schemas (`schemas.py`) -- the contract every agent hand-off must
satisfy. If an LLM's JSON doesn't validate against one of these, the
pipeline raises right there instead of passing a malformed object to the
next agent.

- `Clause` / `ExtractionResult` -- Extractor's output. `ClauseType` enum
  caps what a clause can be labeled (termination, liability, payment_terms,
  confidentiality, indemnity, auto_renewal, governing_law, other).
- `Rule` -- one entry from the configurable rule set (see
  [rules/](../rules/CLAUDE.md)). `applies_to` is a `ClauseType`, so the
  Risk Analyzer can cheaply filter to only the rules relevant to the
  clauses actually present.
- `RiskFinding` / `RiskAnalysisResult` -- Risk Analyzer's output. Links a
  finding back to both the clause (`clause_id`) and the rule it violated.
- `ExecutiveSummary` -- Summarizer's output. `RiskVerdict` is the top-line
  low/moderate/high call.
- `ReviewReport` -- what `POST /review` returns and what gets persisted:
  clauses + findings + executive_summary + metadata, all in one object.

Adding a new clause type or a new finding field means editing this file
first -- everything downstream (rules JSON, prompts, DB storage) follows
from the schema, not the other way around.
