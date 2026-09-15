"""Shared fixtures. Every LLM call in these tests is mocked -- no network,
no API key needed."""

import pytest

from clauseguard.models.schemas import Clause, ClauseType, Rule, Severity


@pytest.fixture
def sample_clauses() -> list[Clause]:
    return [
        Clause(id="c1", type=ClauseType.LIABILITY, text="Liability capped at $100.", confidence=0.95),
        Clause(id="c2", type=ClauseType.AUTO_RENEWAL, text="Auto-renews with 5 days notice.", confidence=0.9),
    ]


@pytest.fixture
def sample_rules() -> list[Rule]:
    return [
        Rule(
            id="liability_cap_too_low",
            name="Liability cap too low",
            applies_to=ClauseType.LIABILITY,
            description="Flag caps under $50,000.",
            severity=Severity.HIGH,
        ),
        Rule(
            id="auto_renewal_no_optout",
            name="Auto-renewal without opt-out",
            applies_to=ClauseType.AUTO_RENEWAL,
            description="Flag auto-renewal without 30 days notice.",
            severity=Severity.MEDIUM,
        ),
        Rule(
            id="unfavorable_governing_law",
            name="Unfavorable governing law",
            applies_to=ClauseType.GOVERNING_LAW,
            description="Flag one-sided venue selection.",
            severity=Severity.LOW,
        ),
    ]
