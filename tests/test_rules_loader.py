from clauseguard.rules.loader import load_rules


def test_load_default_rules():
    rules = load_rules()

    assert len(rules) == 7
    assert {r.id for r in rules} >= {"liability_cap_too_low", "auto_renewal_no_optout"}
