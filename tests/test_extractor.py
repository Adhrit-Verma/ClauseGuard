import pytest

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


def test_long_document_is_split_across_calls_with_global_line_numbers(monkeypatch):
    prompts = []

    def fake(system, user):
        prompts.append(user)
        if "2: 1. Liability" in user:
            return '{"clauses": [["liability", 2]]}'
        return '{"clauses": [["governing_law", 4], ["other", 1]]}'  # line 1 isn't in this chunk -> ignored

    monkeypatch.setattr(extractor, "call_llm", fake)
    # Room for ~2 numbered lines per call, so DOC splits into lines 1-2 and 3-4.
    monkeypatch.setattr(extractor, "prompt_budget", lambda system: len(extractor._CONTINUED) + 60)

    result = extractor.extract_clauses(DOC)

    assert len(prompts) == 2
    assert prompts[1].startswith(extractor._CONTINUED) and "2: 1. Liability" not in prompts[1]
    assert [(c.id, c.type.value, c.text) for c in result.clauses] == [
        ("c1", "liability", "1. Liability. Total liability is capped at $100."),  # runs across the cut
        ("c2", "governing_law", "2. Law. Governed by Delaware law."),
    ]


def test_calls_are_capped_by_line_count_even_when_they_would_fit(monkeypatch):
    prompts = []

    def fake(system, user):
        prompts.append(user)
        rows = []
        if "2: 1. Liability" in user:
            rows.append('["liability", 2]')  # seen by two overlapping calls -> kept once
        if "4: 2. Law" in user:
            rows.append('["governing_law", 4]')
        return '{"clauses": [' + ", ".join(rows) + "]}"

    monkeypatch.setattr(extractor, "call_llm", fake)
    monkeypatch.setattr(extractor, "_MAX_LINES_PER_CALL", 2)  # budget is huge; only the line cap splits

    result = extractor.extract_clauses(DOC)

    assert len(prompts) == 3  # lines 1-2, 2-3, 3-4 (one line of overlap at each cut)
    assert [(c.id, c.type.value, c.text) for c in result.clauses] == [
        ("c1", "liability", "1. Liability. Total liability is capped at $100."),
        ("c2", "governing_law", "2. Law. Governed by Delaware law."),
    ]


def test_extract_clauses_empty_document(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", _fake('{"clauses": []}'))
    assert extractor.extract_clauses("").clauses == []


def test_invented_type_becomes_other_and_a_bad_row_is_skipped(monkeypatch):
    # Seen live: "limitation_of_liability" used to fail the whole review.
    rows = '{"clauses": [["limitation_of_liability", 2], ["liability", "not a line"], ["governing_law", 4]]}'
    monkeypatch.setattr(extractor, "call_llm", _fake(rows))

    result = extractor.extract_clauses(DOC)

    assert [(c.type.value, c.text) for c in result.clauses] == [
        ("other", "1. Liability. Total liability is capped at $100."),
        ("governing_law", "2. Law. Governed by Delaware law."),
    ]


def test_reply_without_a_clauses_list_is_malformed(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", _fake('{"items": []}'))
    with pytest.raises(ValueError):
        extractor.extract_clauses(DOC)
