import pytest
from pydantic import ValidationError

from clauseguard.agents import extractor

# Lines once blanks are dropped: 1 title, 2-3 clause "1.", 4 clause "2."
DOC = "MUTUAL NDA\n\n1. Liability. Total liability\nis capped at $100.\n2. Law. Governed by Delaware law."


def _fake(response: str):
    return lambda system, user: response


def test_each_clause_runs_until_the_next_one_starts(monkeypatch):
    seen = {}

    def fake(system, user):
        seen["prompt"] = user
        return '```json\n{"clauses": [["liability", 2, 0.9], ["governing_law", 4]]}\n```'

    monkeypatch.setattr(extractor, "call_llm", fake)
    result = extractor.extract_clauses(DOC)

    assert "2: 1. Liability. Total liability" in seen["prompt"]  # blank lines dropped before numbering
    assert [(c.id, c.type.value, c.text, c.confidence) for c in result.clauses] == [
        ("c1", "liability", "1. Liability. Total liability is capped at $100.", 0.9),
        ("c2", "governing_law", "2. Law. Governed by Delaware law.", 1.0),
    ]


def test_snaps_start_back_onto_heading_and_drops_bad_rows(monkeypatch):
    # Start 3 is one line past the "1. Liability." heading; 99 is out of range; a second row at 4 is a duplicate.
    rows = '{"clauses": [["governing_law", 4], ["liability", 3, 0.8], ["other", 99], ["termination", 4]]}'
    monkeypatch.setattr(extractor, "call_llm", _fake(rows))

    result = extractor.extract_clauses(DOC)

    assert [(c.id, c.type.value, c.text) for c in result.clauses] == [
        ("c1", "liability", "1. Liability. Total liability is capped at $100."),
        ("c2", "governing_law", "2. Law. Governed by Delaware law."),
    ]


def test_does_not_snap_onto_a_line_another_clause_already_starts_on(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", _fake('{"clauses": [["liability", 2], ["other", 3]]}'))

    result = extractor.extract_clauses(DOC)

    assert [c.text for c in result.clauses] == [
        "1. Liability. Total liability",
        "is capped at $100. 2. Law. Governed by Delaware law.",
    ]


def test_extract_clauses_empty_document(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", _fake('{"clauses": []}'))
    assert extractor.extract_clauses("").clauses == []


def test_extract_clauses_invalid_type_raises(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", _fake('{"clauses": [["not_a_real_type", 1]]}'))
    with pytest.raises(ValidationError):
        extractor.extract_clauses(DOC)
