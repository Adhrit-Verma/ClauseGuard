"""Risk Analyzer agent: checks extracted clauses against the configured rule set.

Code pairs every clause with every rule for its type, and the model must answer each numbered
check true/false. An open-ended "list the violations" prompt let the model stop after one or two
(measured: 1-2 of ~6 real violations); a checklist answered row by row caught 5-7 in one ~4s call.
Rule name and severity come from the rule set, never the model. Rules only apply to clause types
actually present -- the conditional logic behind using a graph (FLOW.md)."""

from clauseguard.llm import call_llm, parse_json_response
from clauseguard.models.schemas import Clause, RiskAnalysisResult, RiskChecks, RiskFinding, Rule

SYSTEM_PROMPT = """You are a contract risk checker. For EVERY numbered check, decide whether the \
clause violates the rule. Answer every check, in order; do not skip any. Only say true when the \
clause text clearly supports it.

Respond with ONLY JSON, no prose. One row per check: [check number, true or false, reason in at \
most 12 words, or "" if false]:
{"checks": [[1, true, "<reason>"], [2, false, ""]]}"""


def analyze_risk(clauses: list[Clause], rules: list[Rule]) -> RiskAnalysisResult:
    # ponytail: every check goes in one call; a long contract with a large rule set means a long prompt and reply.
    pairs = [(clause, rule) for clause in clauses for rule in rules if rule.applies_to == clause.type]
    if not pairs:
        return RiskAnalysisResult(findings=[])

    checks = "\n".join(f"{i}. Rule: {rule.description}\n   Clause: {clause.text}" for i, (clause, rule) in enumerate(pairs, start=1))
    answers = RiskChecks.model_validate(parse_json_response(call_llm(SYSTEM_PROMPT, checks)))

    findings: dict[int, RiskFinding] = {}
    for check in answers.checks:
        if not check.violates or check.index > len(pairs):
            continue
        clause, rule = pairs[check.index - 1]
        findings.setdefault(
            check.index,
            RiskFinding(
                clause_id=clause.id,
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                explanation=check.reason or rule.name,
            ),
        )
    return RiskAnalysisResult(findings=[findings[i] for i in sorted(findings)])
