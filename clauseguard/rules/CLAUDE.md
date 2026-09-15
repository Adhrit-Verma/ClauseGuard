# clauseguard/rules/

The configurable rule set the Risk Analyzer checks clauses against. This is
what makes the project "compare against a known standard" rather than
"summarize this PDF".

- `default_rules.json` -- 13 rules: 7 for commercial contracts (liability
  cap, auto-renewal, indemnity, termination for convenience, payment terms,
  confidentiality, governing law) and 6 for offer letters / employment
  contracts (non-compete, notice period, training bond / clawback,
  unilateral changes, IP assignment, probation). Each rule: `id`, `name`,
  `applies_to` (a `ClauseType`), `description` (fed to the LLM as the
  check), `severity`, and `keywords`.
- `loader.py` -- `load_rules(path=None) -> list[Rule]`. Reads
  `CLAUSEGUARD_RULES_FILE` if set, else `default_rules.json`; validates each
  entry against the `Rule` model.

## How a rule reaches a clause

`applies_to` is a hint, not a gate. The Risk Analyzer checks a rule against
clauses labeled with that type **and** the top few clauses a BM25 keyword
index ranks highest for the rule's `keywords` (`clauseguard/retrieval.py`),
because the Extractor's type labels are unreliable on unfamiliar documents
(an offer letter once got 13 of 18 clauses labeled "termination").

So `keywords` matter: list the distinctive words a violating clause would
contain, with variants the tokenizer won't merge (`renew` / `renewal`;
plural "s" is stripped automatically). Avoid generic words like "term",
"agreement" or "employee" that appear in most clauses -- they pull in
irrelevant candidates, and every candidate is an extra LLM check.

Commercial and employment rules can share one file: a rule whose type and
keywords match nothing in a document is never checked for it.

## Reviewing a different document type

Add rules here, or point `CLAUSEGUARD_RULES_FILE` at your own JSON with the
same shape -- no code changes. A new clause type goes in `ClauseType`
(`models/schemas.py`); the Extractor's prompt picks it up automatically.
