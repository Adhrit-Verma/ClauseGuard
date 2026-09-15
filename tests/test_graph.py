"""End-to-end pipeline test with every LLM call mocked -- verifies the
LangGraph routing, including the skip-analyze-when-no-clauses branch, and
the on_stage callback that lets main.py persist progress for polling."""

from clauseguard.agents import extractor, graph, risk_analyzer, summarizer
from clauseguard.models.schemas import ReviewStatus


def test_run_review_full_pipeline(monkeypatch):
    monkeypatch.setattr(
        extractor,
        "call_llm",
        lambda system, user: '{"clauses": [{"type": "liability", "start": 1, "end": 1, "confidence": 0.9}]}',
    )
    monkeypatch.setattr(
        risk_analyzer,
        "call_llm",
        lambda system, user: '{"checks": [[1, true, "Too low."]]}',
    )
    monkeypatch.setattr(
        summarizer,
        "call_llm",
        lambda system, user: '{"verdict": "high_risk", "summary": "Risky NDA.", "key_points": ["Low cap"]}',
    )

    stages = []
    result = graph.run_review("some contract text", on_stage=stages.append)

    assert len(result["clauses"]) == 1
    assert len(result["findings"]) == 1
    assert result["summary"].verdict.value == "high_risk"
    assert stages == [ReviewStatus.EXTRACTING, ReviewStatus.ANALYZING, ReviewStatus.SUMMARIZING]


def test_run_review_skips_analyze_when_no_clauses(monkeypatch):
    monkeypatch.setattr(extractor, "call_llm", lambda system, user: '{"clauses": []}')

    def fail_if_called(*args, **kwargs):
        raise AssertionError("risk_analyzer.call_llm should not run when there are no clauses")

    monkeypatch.setattr(risk_analyzer, "call_llm", fail_if_called)
    monkeypatch.setattr(
        summarizer,
        "call_llm",
        lambda system, user: '{"verdict": "low_risk", "summary": "Nothing found.", "key_points": []}',
    )

    stages = []
    result = graph.run_review("blank document", on_stage=stages.append)

    assert result["clauses"] == []
    assert result["findings"] == []
    assert result["summary"].verdict.value == "low_risk"
    # extract found nothing, so analyze is skipped -- stage jumps straight to summarizing.
    assert stages == [ReviewStatus.EXTRACTING, ReviewStatus.SUMMARIZING]
