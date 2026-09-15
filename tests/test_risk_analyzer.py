from clauseguard.agents import risk_analyzer
from clauseguard.models.schemas import Clause, ClauseType


def _never_called(*args, **kwargs):
    raise AssertionError("call_llm should not run when there is nothing to check")


def test_analyze_risk_no_clauses_skips_llm_call(monkeypatch, sample_rules):
    monkeypatch.setattr(risk_analyzer, "call_llm", _never_called)
    assert risk_analyzer.analyze_risk([], sample_rules).findings == []


def test_analyze_risk_no_applicable_rules_skips_llm_call(monkeypatch, sample_rules):
    monkeypatch.setattr(risk_analyzer, "call_llm", _never_called)
    clauses = [Clause(id="c1", type=ClauseType.OTHER, text="Miscellaneous clause.")]
    assert risk_analyzer.analyze_risk(clauses, sample_rules).findings == []


def test_asks_one_numbered_check_per_clause_rule_pair(monkeypatch, sample_clauses, sample_rules):
    seen = {}

    def fake(system, user):
        seen["prompt"] = user
        return '{"checks": [[1, true, "Cap of $100 is far too low."], [2, false, ""]]}'

    monkeypatch.setattr(risk_analyzer, "call_llm", fake)
    result = risk_analyzer.analyze_risk(sample_clauses, sample_rules)

    assert "1. Rule: Flag caps under $50,000.\n   Clause: Liability capped at $100." in seen["prompt"]
    assert "2. Rule: Flag auto-renewal without 30 days notice." in seen["prompt"]
    assert "one-sided venue" not in seen["prompt"]  # no governing_law clause, so that rule isn't checked
    assert [(f.clause_id, f.rule_id, f.rule_name, f.severity.value, f.explanation) for f in result.findings] == [
        ("c1", "liability_cap_too_low", "Liability cap too low", "high", "Cap of $100 is far too low.")
    ]


def test_ignores_unknown_checks_keeps_first_duplicate_and_fills_missing_reason(monkeypatch, sample_clauses, sample_rules):
    rows = '{"checks": [[9, true, "no such check"], [1, false, ""], {"index": 2, "violates": true}, [2, true, "dup"]]}'
    monkeypatch.setattr(risk_analyzer, "call_llm", lambda system, user: rows)

    result = risk_analyzer.analyze_risk(sample_clauses, sample_rules)

    assert [(f.clause_id, f.rule_id, f.severity.value, f.explanation) for f in result.findings] == [
        ("c2", "auto_renewal_no_optout", "medium", "Auto-renewal without opt-out")
    ]
