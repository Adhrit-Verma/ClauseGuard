"""FastAPI entrypoint: serves the web UI at /, and POST /review runs the full
extract -> analyze -> summarize pipeline over an uploaded PDF and persists the result."""

import asyncio
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from clauseguard import llm
from clauseguard.agents.graph import run_review
from clauseguard.models.schemas import ReviewReport
from clauseguard.storage.db import DEFAULT_DB_PATH, get_report, list_reports, save_report

app = FastAPI(title="ClauseGuard", description="Multi-agent contract & policy review pipeline")

DB_PATH = os.environ.get("CLAUSEGUARD_DB", DEFAULT_DB_PATH)
INDEX_HTML = Path(__file__).parent / "static" / "index.html"


def extract_pdf_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.get("/api/info")
def info() -> dict:
    return {"provider": llm.PROVIDER, "model": llm.MODEL}


@app.post("/review", response_model=ReviewReport)
async def review_document(file: UploadFile = File(...)) -> ReviewReport:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    data = await file.read()
    try:
        text = await asyncio.to_thread(extract_pdf_text, data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this file as a PDF.") from exc
    if not text.strip():
        raise HTTPException(
            status_code=422, detail="No text found in this PDF. Scanned documents aren't supported yet."
        )

    try:
        # Off the event loop: a review blocks for minutes and would freeze every other request.
        state = await asyncio.to_thread(run_review, text)
    except OSError as exc:  # TimeoutError, or URLError (possibly wrapping a timeout) from Ollama
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            raise HTTPException(
                status_code=504,
                detail=f"Timed out waiting for the model after {llm.OLLAMA_TIMEOUT:g}s. "
                "Try again (the first run is slower while the model loads) or raise OLLAMA_TIMEOUT.",
            ) from exc
        raise HTTPException(
            status_code=503, detail=f"LLM backend unreachable ({reason}). Is Ollama running?"
        ) from exc
    except ValueError as exc:  # JSONDecodeError or Pydantic ValidationError on model output
        raise HTTPException(status_code=502, detail="The model returned malformed output. Please try again.") from exc

    report = ReviewReport(
        document_name=file.filename,
        created_at=datetime.now(timezone.utc),
        clauses=state["clauses"],
        findings=state["findings"],
        executive_summary=state["summary"],
    )
    save_report(report, path=DB_PATH)
    return report


@app.get("/reviews")
def get_reviews() -> list[dict]:
    return list_reports(path=DB_PATH)


@app.get("/reviews/{review_id}", response_model=ReviewReport)
def get_review(review_id: int) -> ReviewReport:
    report = get_report(review_id, path=DB_PATH)
    if report is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return report
