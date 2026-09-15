from clauseguard.agents import summarizer
from clauseguard.models.schemas import RiskFinding


def _finding(severity: str) -> RiskFinding:
    return RiskFinding(clause_id="c1", rule_id="r", rule_name="Rule", severity=severity, explanation="x")


def test_summarize_takes_text_from_model_but_computes_verdict(monkeypatch, sample_clauses):
    # The model claims low risk; a high-severity finding must still produce high_risk.
    fake = '{"verdict": "low_risk", "summary": "Low cap.", "key_points": ["a", "b", "c", "d", "e"]}'
    monkeypatch.setattr(summarizer, "call_llm", lambda system, user: fake)

    result = summarizer.summarize(sample_clauses, [_finding("high")])

    assert result.verdict.value == "high_risk"
    assert result.summary == "Low cap."
    assert result.key_points == ["a", "b", "c", "d"]


def test_verdict_rule():
    def verdict(severities):
        return summarizer.verdict_for([_finding(s) for s in severities]).value

    assert verdict([]) == "low_risk"
    assert verdict(["low", "low"]) == "low_risk"
    assert verdict(["medium", "low"]) == "moderate_risk"
    assert verdict(["medium"] * 3) == "high_risk"
    assert verdict(["critical"]) == "high_risk"


def test_summarize_handles_no_clauses_or_findings(monkeypatch):
    monkeypatch.setattr(summarizer, "call_llm", lambda system, user: '{"summary": "No clauses found.", "key_points": []}')
    assert summarizer.summarize([], []).verdict.value == "low_risk"


def test_prompt_lists_each_rule_once_with_a_count(monkeypatch, sample_clauses):
    seen = {}

    def fake(system, user):
        seen["prompt"] = user
        return '{"summary": "s", "key_points": []}'

    monkeypatch.setattr(summarizer, "call_llm", fake)
    other = RiskFinding(clause_id="c2", rule_id="cap", rule_name="Cap too low", severity="high", explanation="tiny cap")

    summarizer.summarize(sample_clauses, [_finding("medium"), _finding("medium"), other])

    assert seen["prompt"].split("Risk findings:\n")[1].splitlines() == [
        "- high: Cap too low -- tiny cap",
        "- medium: Rule (x2) -- x",
    ]
