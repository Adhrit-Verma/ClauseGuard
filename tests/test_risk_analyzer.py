from clauseguard.agents import risk_analyzer
from clauseguard.models.schemas import Clause, ClauseType


def test_analyze_risk_no_clauses_skips_llm_call(monkeypatch, sample_rules):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_llm should not be called with zero clauses")

    monkeypatch.setattr(risk_analyzer, "call_llm", fail_if_called)

    result = risk_analyzer.analyze_risk([], sample_rules)

    assert result.findings == []


def test_analyze_risk_no_applicable_rules_skips_llm_call(monkeypatch, sample_rules):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("call_llm should not be called when no rule applies")

    monkeypatch.setattr(risk_analyzer, "call_llm", fail_if_called)

    clauses = [Clause(id="c1", type=ClauseType.OTHER, text="Miscellaneous clause.")]
    result = risk_analyzer.analyze_risk(clauses, sample_rules)

    assert result.findings == []


def test_analyze_risk_returns_findings(monkeypatch, sample_clauses, sample_rules):
    fake_response = (
        '{"findings": [{"clause_id": "c1", "rule_id": "liability_cap_too_low", '
        '"rule_name": "Liability cap too low", "severity": "high", '
        '"explanation": "Cap of $100 is far below a reasonable minimum."}]}'
    )
    monkeypatch.setattr(risk_analyzer, "call_llm", lambda system, user: fake_response)

    result = risk_analyzer.analyze_risk(sample_clauses, sample_rules)

    assert len(result.findings) == 1
    assert result.findings[0].clause_id == "c1"
    assert result.findings[0].severity.value == "high"
