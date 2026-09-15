"""HTTP layer: UI is served, and upload/LLM failures map to clear status codes the UI can show."""

import asyncio
import urllib.error
from pathlib import Path

from fastapi.testclient import TestClient

from clauseguard import main

client = TestClient(main.app)
SAMPLE_PDF = (Path(__file__).parent.parent / "sample_docs" / "sample_nda.pdf").read_bytes()


def _post(name: str, data: bytes):
    return client.post("/review", files={"file": (name, data, "application/pdf")})


def _raises(exc: Exception):
    def fake_review(text):
        raise exc

    return fake_review


def test_index_serves_ui():
    res = client.get("/")
    assert res.status_code == 200
    assert "ClauseGuard" in res.text


def test_info_reports_provider_and_model():
    assert set(client.get("/api/info").json()) == {"provider", "model"}


def test_review_rejects_non_pdf_name():
    assert _post("notes.txt", b"hello").status_code == 400


def test_review_rejects_corrupt_pdf():
    assert _post("broken.pdf", b"not really a pdf").status_code == 400


def test_review_llm_unreachable_returns_503(monkeypatch):
    monkeypatch.setattr(main, "run_review", _raises(urllib.error.URLError("connection refused")))
    assert _post("nda.pdf", SAMPLE_PDF).status_code == 503


def test_review_model_read_timeout_returns_504(monkeypatch):
    monkeypatch.setattr(main, "run_review", _raises(TimeoutError("timed out")))
    assert _post("nda.pdf", SAMPLE_PDF).status_code == 504


def test_review_model_connect_timeout_returns_504(monkeypatch):
    monkeypatch.setattr(main, "run_review", _raises(urllib.error.URLError(TimeoutError("timed out"))))
    assert _post("nda.pdf", SAMPLE_PDF).status_code == 504


def test_review_malformed_model_output_returns_502(monkeypatch):
    monkeypatch.setattr(main, "run_review", _raises(ValueError("bad json")))
    assert _post("nda.pdf", SAMPLE_PDF).status_code == 502


def test_review_runs_pipeline_off_the_event_loop(monkeypatch):
    # Running the minutes-long pipeline on the loop froze every other request.
    seen = {}

    def fake_review(text):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        raise ValueError("stop after recording")

    monkeypatch.setattr(main, "run_review", fake_review)
    _post("nda.pdf", SAMPLE_PDF)
    assert seen == {"on_loop": False}
