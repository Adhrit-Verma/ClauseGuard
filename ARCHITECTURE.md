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
  `ReviewReport`), `GET /reviews`, `GET /reviews/{id}`.
- **LangGraph** -- orchestrates the three agents as a graph (see above).
- **Anthropic API** (`clauseguard/llm.py`) -- the reasoning engine inside
  each agent. One thin wrapper function, `call_llm`, is the only place the
  SDK is touched -- this is also the seam every test mocks.
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
