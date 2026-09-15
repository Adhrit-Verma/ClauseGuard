"""Summarizer agent: turns risk findings into a plain-English executive summary.

The verdict is computed from finding severities rather than asked of the model: the rule is
fixed, and a small model was observed calling a high-severity finding "moderate_risk"."""

from clauseguard.llm import call_llm, parse_json_response
from clauseguard.models.schemas import Clause, ExecutiveSummary, RiskFinding, RiskVerdict, Severity, SummaryDraft

SYSTEM_PROMPT = """You write executive summaries of contract risk reviews for non-lawyers. \
Given the clause types found and the risk findings, respond with ONLY JSON, no prose:
{"summary": "<at most 2 sentences>", "key_points": ["<at most 10 words>"]}

Use at most 4 key points, most serious first. If there are no findings, say no risks were found."""

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}


def verdict_for(findings: list[RiskFinding]) -> RiskVerdict:
    severities = [finding.severity for finding in findings]
    if Severity.HIGH in severities or Severity.CRITICAL in severities or severities.count(Severity.MEDIUM) >= 3:
        return RiskVerdict.HIGH_RISK
    if Severity.MEDIUM in severities:
        return RiskVerdict.MODERATE_RISK
    return RiskVerdict.LOW_RISK


def summarize(clauses: list[Clause], findings: list[RiskFinding]) -> ExecutiveSummary:
    clause_types = ", ".join(sorted({clause.type.value for clause in clauses})) or "none"
    ordered = sorted(findings, key=lambda f: _SEVERITY_ORDER[f.severity])
    findings_block = "\n".join(f"- {f.severity.value}: {f.rule_name} -- {f.explanation}" for f in ordered)
    user_prompt = f"Clause types found: {clause_types}\n\nRisk findings:\n{findings_block or '(no risk findings)'}"

    draft = SummaryDraft.model_validate(parse_json_response(call_llm(SYSTEM_PROMPT, user_prompt)))
    return ExecutiveSummary(verdict=verdict_for(findings), summary=draft.summary, key_points=draft.key_points[:4])
