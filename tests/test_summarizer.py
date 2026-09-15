from clauseguard.agents import summarizer


def test_summarize_returns_executive_summary(monkeypatch, sample_clauses):
    fake_response = (
        '{"verdict": "high_risk", "summary": "This NDA has a very low liability cap.", '
        '"key_points": ["Liability capped at $100", "Auto-renews with short notice"]}'
    )
    monkeypatch.setattr(summarizer, "call_llm", lambda system, user: fake_response)

    result = summarizer.summarize(sample_clauses, findings=[])

    assert result.verdict.value == "high_risk"
    assert len(result.key_points) == 2


def test_summarize_handles_no_clauses_or_findings(monkeypatch):
    fake_response = '{"verdict": "low_risk", "summary": "No clauses found.", "key_points": []}'
    monkeypatch.setattr(summarizer, "call_llm", lambda system, user: fake_response)

    result = summarizer.summarize([], [])

    assert result.verdict.value == "low_risk"
