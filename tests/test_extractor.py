import pytest

from clauseguard.agents import extractor


def test_extract_clauses_parses_valid_json(monkeypatch):
    fake_response = """```json
    {"clauses": [{"id": "c1", "type": "liability", "text": "Liability capped at $100.", "confidence": 0.9}]}
    ```"""
    monkeypatch.setattr(extractor, "call_llm", lambda system, user: fake_response)

    result = extractor.extract_clauses("some contract text")

    assert len(result.clauses) == 1
    assert result.clauses[0].id == "c1"
    assert result.clauses[0].type.value == "liability"


def test_extract_clauses_empty_document(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", lambda system, user: '{"clauses": []}')

    result = extractor.extract_clauses("")

    assert result.clauses == []


def test_extract_clauses_invalid_type_raises(monkeypatch):
    monkeypatch.setattr(
        extractor,
        "call_llm",
        lambda system, user: '{"clauses": [{"id": "c1", "type": "not_a_real_type", "text": "x"}]}',
    )

    with pytest.raises(Exception):
        extractor.extract_clauses("some contract text")
