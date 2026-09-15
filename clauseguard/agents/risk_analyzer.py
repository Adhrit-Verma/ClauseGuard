"""Risk Analyzer agent: checks extracted clauses against the configured rule
set and produces structured findings. Rules only apply to clause types that
are actually present in the document -- this is the piece of conditional
logic that motivates a graph over a flat script (see FLOW.md)."""

from clauseguard.llm import call_llm, parse_json_response
from clauseguard.models.schemas import Clause, RiskAnalysisResult, Rule

SYSTEM_PROMPT = """You are a contract risk analysis engine. You will be given \
a list of contract clauses and a list of rules to check them against. For \
every clause that violates an applicable rule, produce a finding. Do not \
invent violations that aren't supported by the clause text -- if nothing \
clearly violates a rule, omit it.

Respond with ONLY a JSON object of this exact shape, no prose:
{"findings": [{"clause_id": "c1", "rule_id": "<rule id>", "rule_name": "<rule name>", "severity": "low|medium|high|critical", "explanation": "<why this clause violates the rule>"}]}

If no clauses violate any rule, return {"findings": []}."""


def analyze_risk(clauses: list[Clause], rules: list[Rule]) -> RiskAnalysisResult:
    if not clauses:
        return RiskAnalysisResult(findings=[])

    present_types = {clause.type for clause in clauses}
    applicable_rules = [rule for rule in rules if rule.applies_to in present_types]
    if not applicable_rules:
        return RiskAnalysisResult(findings=[])

    clauses_block = "\n".join(f"- id={c.id} type={c.type.value}: {c.text}" for c in clauses)
    rules_block = "\n".join(
        f"- id={r.id} name={r.name!r} applies_to={r.applies_to.value} severity={r.severity.value}: {r.description}"
        for r in applicable_rules
    )
    user_prompt = f"Clauses:\n{clauses_block}\n\nRules to check:\n{rules_block}"

    raw = call_llm(SYSTEM_PROMPT, user_prompt)
    data = parse_json_response(raw)
    return RiskAnalysisResult.model_validate(data)
