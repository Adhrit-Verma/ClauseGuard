from clauseguard.rules.loader import load_rules


def test_load_default_rules():
    rules = load_rules()
    ids = [r.id for r in rules]

    assert {"liability_cap_too_low", "auto_renewal_no_optout", "overbroad_non_compete", "bond_or_clawback"} <= set(ids)
    assert len(ids) == len(set(ids))
    assert all(r.keywords for r in rules)  # the BM25 retrieval step matches clauses on these
