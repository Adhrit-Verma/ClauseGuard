"""Risk Analyzer agent: checks extracted clauses against the configured rule set.

Retrieve: each rule is checked against the clauses labeled with its type, plus the TOP_K_PER_RULE
clauses a BM25 keyword index ranks highest for the rule's keywords (clauseguard/retrieval.py), so a
clause the Extractor mislabeled is still checked.

Rerank/verify: the model answers a numbered true/false checklist over those candidate pairs. An
open-ended "list the violations" prompt let the model stop after one or two (measured: 1-2 of ~6 real
violations); a checklist answered row by row caught 5-7. Rule name and severity come from the rule
set, never the model. Long contracts are checked in batches that each fit one call."""

from clauseguard.llm import call_llm, parse_json_response, prompt_budget
from clauseguard.models.schemas import Clause, RiskAnalysisResult, RiskCheck, RiskFinding, Rule, parse_rows
from clauseguard.retrieval import bm25_scores, tokenize

SYSTEM_PROMPT = """You are a contract risk checker. For EVERY numbered check, decide whether the \
clause violates the rule. Answer every check, in order; do not skip any. Only say true when the \
clause text clearly supports it.

Respond with ONLY JSON, no prose. One row per check: [check number, true or false, reason in at \
most 12 words, or "" if false]:
{"checks": [[1, true, "<reason>"], [2, false, ""]]}"""

# ponytail: ~15 reply tokens per check keeps a full batch inside llm's reply reserve; raise both together.
MAX_CHECKS_PER_CALL = 40
# ponytail: keyword retrieval only -- a clause that both paraphrases a rule with no shared words and carries
# the wrong type label is still missed. Embedding retrieval is the upgrade if that shows up in practice.
TOP_K_PER_RULE = 3
# Retrieval runs both ways: without this, a clause no rule ranked highly and whose type matches nothing
# is checked against nothing at all, and silently gets a clean bill of health.
RULES_PER_UNMATCHED_CLAUSE = 2


def _candidate_pairs(clauses: list[Clause], rules: list[Rule]) -> list[tuple[Clause, Rule]]:
    documents = [tokenize(clause.text) for clause in clauses]
    rule_queries = [tokenize(" ".join(rule.keywords)) if rule.keywords else tokenize(rule.name) for rule in rules]

    pairs: set[tuple[int, int]] = set()
    for r, rule in enumerate(rules):
        pairs.update((c, r) for c, clause in enumerate(clauses) if clause.type == rule.applies_to)
        scores = bm25_scores(rule_queries[r], documents)
        ranked = [c for c in sorted(range(len(clauses)), key=lambda i: -scores[i]) if scores[c] > 0]
        pairs.update((c, r) for c in ranked[:TOP_K_PER_RULE])

    matched = {c for c, _ in pairs}
    for c, document in enumerate(documents):
        if c in matched:
            continue
        scores = bm25_scores(document, rule_queries)  # same index, rules as the documents this time
        ranked = [r for r in sorted(range(len(rules)), key=lambda i: -scores[i]) if scores[r] > 0]
        pairs.update((c, r) for r in ranked[:RULES_PER_UNMATCHED_CLAUSE])

    return [(clauses[c], rules[r]) for c, r in sorted(pairs)]


def analyze_risk(clauses: list[Clause], rules: list[Rule]) -> RiskAnalysisResult:
    pairs = _candidate_pairs(clauses, rules)
    if not pairs:
        return RiskAnalysisResult(findings=[])

    budget = prompt_budget(SYSTEM_PROMPT)
    findings: list[RiskFinding] = []
    batch: list[tuple[Clause, Rule]] = []
    size = 0
    for clause, rule in pairs:
        entry_size = len(rule.description) + len(clause.text) + 30  # + "N. Rule: ...\n   Clause: " overhead
        if batch and (size + entry_size > budget or len(batch) == MAX_CHECKS_PER_CALL):
            findings += _check(batch)
            batch, size = [], 0
        batch.append((clause, rule))
        size += entry_size
    findings += _check(batch)
    return RiskAnalysisResult(findings=findings)


def _check(pairs: list[tuple[Clause, Rule]]) -> list[RiskFinding]:
    checklist = "\n".join(f"{i}. Rule: {rule.description}\n   Clause: {clause.text}" for i, (clause, rule) in enumerate(pairs, start=1))
    checks = parse_rows(parse_json_response(call_llm(SYSTEM_PROMPT, checklist)), "checks", RiskCheck)

    found: dict[int, RiskFinding] = {}
    for check in checks:
        if not check.violates or check.index > len(pairs):
            continue
        clause, rule = pairs[check.index - 1]
        found.setdefault(
            check.index,
            RiskFinding(
                clause_id=clause.id,
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                explanation=check.reason or rule.name,
            ),
        )
    return [found[i] for i in sorted(found)]
