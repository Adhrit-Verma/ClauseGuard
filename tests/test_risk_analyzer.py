from clauseguard.agents import risk_analyzer
from clauseguard.models.schemas import Clause, ClauseType, Rule, Severity


def test_keyword_retrieval_checks_a_rule_against_a_mislabeled_clause(monkeypatch):
    rule = Rule(
        id="overbroad_non_compete",
        name="Overbroad non-compete",
        applies_to=ClauseType.NON_COMPETE,
        description="Flag non-competes longer than 12 months.",
        severity=Severity.HIGH,
        keywords=["compete", "competitor"],
    )
    clauses = [  # both mislabeled "termination"; only c1 is about competing
        Clause(id="c1", type=ClauseType.TERMINATION, text="Employee shall not join a competitor for 3 years."),
        Clause(id="c2", type=ClauseType.TERMINATION, text="Either party may end employment with 30 days notice."),
    ]
    seen = {}

    def fake(system, user):
        seen["prompt"] = user
        return '{"checks": [[1, true, "3 years is too long"]]}'

    monkeypatch.setattr(risk_analyzer, "call_llm", fake)
    result = risk_analyzer.analyze_risk(clauses, [rule])

    assert "competitor for 3 years" in seen["prompt"] and "30 days notice" not in seen["prompt"]
    assert [(f.clause_id, f.rule_id, f.severity.value) for f in result.findings] == [("c1", "overbroad_non_compete", "high")]


def _never_called(*args, **kwargs):
    raise AssertionError("call_llm should not run when there is nothing to check")


def test_clause_no_rule_retrieved_still_gets_checked_against_its_closest_rules(monkeypatch):
    rule = Rule(
        id="perpetual_or_overbroad_confidentiality",
        name="Perpetual confidentiality",
        applies_to=ClauseType.CONFIDENTIALITY,
        description="Flag confidentiality with no end date.",
        severity=Severity.MEDIUM,
        keywords=["confidential"],
    )
    # None carries the rule's type, and c4 is the weakest keyword match, so the rule's own top-3 skips it.
    clauses = [
        Clause(id="c1", type=ClauseType.OTHER, text="Confidential confidential information stays confidential."),
        Clause(id="c2", type=ClauseType.OTHER, text="Confidential confidential data is protected."),
        Clause(id="c3", type=ClauseType.OTHER, text="Confidential confidential notes are kept."),
        Clause(id="c4", type=ClauseType.OTHER, text="Confidential material is held for ten years with no end date."),
    ]
    seen = {}

    def fake(system, user):
        seen["prompt"] = user
        return '{"checks": [[4, true, "no end date"]]}'

    monkeypatch.setattr(risk_analyzer, "call_llm", fake)
    result = risk_analyzer.analyze_risk(clauses, [rule])

    assert "4. Rule:" in seen["prompt"] and "ten years with no end date" in seen["prompt"]
    assert [(f.clause_id, f.rule_id) for f in result.findings] == [("c4", "perpetual_or_overbroad_confidentiality")]


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
    rows = (
        '{"checks": [[9, true, "no such check"], ["x", true, "not a number"], [1, false, ""],'
        ' {"index": 2, "violates": true}, [2, true, "dup"]]}'
    )
    monkeypatch.setattr(risk_analyzer, "call_llm", lambda system, user: rows)

    result = risk_analyzer.analyze_risk(sample_clauses, sample_rules)

    assert [(f.clause_id, f.rule_id, f.severity.value, f.explanation) for f in result.findings] == [
        ("c2", "auto_renewal_no_optout", "medium", "Auto-renewal without opt-out")
    ]


def test_many_checks_are_split_across_calls_each_numbered_from_one(monkeypatch, sample_clauses, sample_rules):
    prompts = []

    def fake(system, user):
        prompts.append(user)
        return '{"checks": [[1, true, "flagged"]]}'

    monkeypatch.setattr(risk_analyzer, "MAX_CHECKS_PER_CALL", 1)
    monkeypatch.setattr(risk_analyzer, "call_llm", fake)

    result = risk_analyzer.analyze_risk(sample_clauses, sample_rules)

    assert len(prompts) == 2 and all(p.startswith("1. Rule:") for p in prompts)
    assert [(f.clause_id, f.rule_id) for f in result.findings] == [
        ("c1", "liability_cap_too_low"),
        ("c2", "auto_renewal_no_optout"),
    ]
