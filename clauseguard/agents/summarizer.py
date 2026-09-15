"""Summarizer agent: synthesizes clauses + risk findings into a plain-English
executive summary with a top-line verdict."""

from clauseguard.llm import call_llm, parse_json_response
from clauseguard.models.schemas import Clause, ExecutiveSummary, RiskFinding

SYSTEM_PROMPT = """You are a contract review summarization engine. Given a \
list of extracted clauses and the risk findings against them, write a \
plain-English executive summary a non-lawyer can read in under a minute, \
plus an overall risk verdict.

Respond with ONLY a JSON object of this exact shape, no prose:
{"verdict": "low_risk|moderate_risk|high_risk", "summary": "<2-4 sentence summary>", "key_points": ["<bullet>", ...]}

Base the verdict on the number and severity of findings: no findings or only \
low severity -> low_risk; some medium severity -> moderate_risk; any high or \
critical severity, or many medium findings -> high_risk."""


def summarize(clauses: list[Clause], findings: list[RiskFinding]) -> ExecutiveSummary:
    clauses_block = "\n".join(f"- id={c.id} type={c.type.value}: {c.text}" for c in clauses) or "(none extracted)"
    findings_block = (
        "\n".join(
            f"- clause={f.clause_id} rule={f.rule_name} severity={f.severity.value}: {f.explanation}"
            for f in findings
        )
        or "(no risk findings)"
    )
    user_prompt = f"Clauses:\n{clauses_block}\n\nRisk findings:\n{findings_block}"

    raw = call_llm(SYSTEM_PROMPT, user_prompt)
    data = parse_json_response(raw)
    return ExecutiveSummary.model_validate(data)
