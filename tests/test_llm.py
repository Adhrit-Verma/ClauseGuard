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


def test_calls_are_recorded_only_inside_a_collector_and_summed(monkeypatch):
    monkeypatch.setattr(llm, "INPUT_COST_PER_MTOK", 3.0)
    monkeypatch.setattr(llm, "OUTPUT_COST_PER_MTOK", 15.0)

    llm._record_call("m", 10, 5, 0.5)  # outside a collector: dropped, not an error
    with llm.collect_calls() as calls:
        llm._record_call("m", 1_000_000, 200_000, 1.25)
        llm._record_call("m", 0, 0, 0.25)

    assert len(calls) == 2
    assert llm.summarize_calls(calls) == {
        "calls": 2,
        "prompt_tokens": 1_000_000,
        "output_tokens": 200_000,
        "model_seconds": 1.5,
        "cost_usd": 6.0,  # 1M in at $3/M + 200k out at $15/M
    }


def test_ollama_refuses_prompts_that_would_overflow_context(monkeypatch):
    # Ollama would silently truncate the document and drop clauses; fail loudly before any network call.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 2048)
    monkeypatch.setattr(llm, "_ollama_generate", lambda payload: pytest.fail("should not reach Ollama"))
    with pytest.raises(RuntimeError, match="OLLAMA_NUM_CTX"):
        llm._call_ollama("system", "x" * 10_000)

    monkeypatch.setattr(llm, "_ollama_generate", lambda payload: {"response": "{}"})
    assert llm._call_ollama("system", "short document") == "{}"
