# clauseguard/rules/

The configurable rule set the Risk Analyzer checks clauses against. This is
what makes the project "compare against a known standard" rather than
"summarize this PDF" -- the same evaluative pattern as checking content
against WCAG criteria, applied to contracts.

- `default_rules.json` -- 7 rules, one per clause type that has a rule
  (termination, liability, payment_terms, confidentiality, indemnity,
  auto_renewal, governing_law). Each rule: `id`, `name`, `applies_to`
  (a `ClauseType`), `description` (fed to the LLM as the check to perform),
  `severity`.
- `loader.py` -- `load_rules(path=None) -> list[Rule]`. Reads
  `CLAUSEGUARD_RULES_FILE` env var if set, else `default_rules.json`.
  Validates every entry against the `Rule` Pydantic model.

## Reviewing a different document type

Write a new JSON file with the same shape and point `CLAUSEGUARD_RULES_FILE`
at it -- no code changes needed. The Risk Analyzer already only applies
rules whose `applies_to` matches a clause type present in the document, so
an NDA-focused rule set and an HR-policy-focused rule set can coexist.
