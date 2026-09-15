import pytest

from clauseguard import llm
from clauseguard.llm import parse_json_response


def test_parse_json_response_plain():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_response_strips_markdown_fence():
    text = '```json\n{"a": 1}\n```'
    assert parse_json_response(text) == {"a": 1}


def test_parse_json_response_strips_bare_fence():
    text = '```\n{"a": 1}\n```'
    assert parse_json_response(text) == {"a": 1}


def test_ollama_refuses_prompts_that_would_overflow_context(monkeypatch):
    # Ollama would silently truncate the document and drop clauses; fail loudly before any network call.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 2048)
    monkeypatch.setattr(llm, "_ollama_generate", lambda payload: pytest.fail("should not reach Ollama"))
    with pytest.raises(RuntimeError, match="OLLAMA_NUM_CTX"):
        llm._call_ollama("system", "x" * 10_000)

    monkeypatch.setattr(llm, "_ollama_generate", lambda payload: {"response": "{}"})
    assert llm._call_ollama("system", "short document") == "{}"
