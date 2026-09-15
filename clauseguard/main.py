"""FastAPI entrypoint: serves the web UI at /, and POST /review kicks off the
extract -> analyze -> summarize pipeline over an uploaded PDF in the
background, returning immediately with an id to poll -- see
storage/db.py for why a review is a row from the moment it's uploaded."""

import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from clauseguard import llm
from clauseguard.agents.graph import run_review
from clauseguard.models.schemas import ReviewRecord, ReviewReport, ReviewStatus
from clauseguard.storage import db

app = FastAPI(title="ClauseGuard", description="Multi-agent contract & policy review pipeline")

DB_PATH = os.environ.get("CLAUSEGUARD_DB", db.DEFAULT_DB_PATH)
INDEX_HTML = Path(__file__).parent / "static" / "index.html"


def extract_pdf_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _process_review(review_id: int, document_name: str, text: str) -> None:
    """Runs off the request entirely -- a FastAPI BackgroundTask keeps running
    to completion even if the client disconnects (e.g. the browser tab is
    refreshed or closed), which is what makes polling by id reliable."""
    try:
        state = run_review(text, on_stage=lambda stage: db.update_status(review_id, stage, path=DB_PATH))
    except OSError as exc:  # TimeoutError, or URLError (possibly wrapping one) from Ollama
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            message = (
                f"Timed out waiting for the model after {llm.OLLAMA_TIMEOUT:g}s. "
                "Try again (the first run is slower while the model loads) or raise OLLAMA_TIMEOUT."
            )
        else:
            message = f"LLM backend unreachable ({reason}). Is Ollama running?"
        db.fail_review(review_id, message, path=DB_PATH)
        return
    except ValueError:  # JSONDecodeError or Pydantic ValidationError on model output
        db.fail_review(review_id, "The model returned malformed output. Please try again.", path=DB_PATH)
        return
    except Exception as exc:  # anything else would leave the review stuck mid-stage forever
        logging.getLogger(__name__).exception("Review %s failed", review_id)
        db.fail_review(review_id, f"Review failed: {exc}", path=DB_PATH)
        return

    report = ReviewReport(
        document_name=document_name,
        created_at=datetime.now(timezone.utc),
        clauses=state["clauses"],
        findings=state["findings"],
        executive_summary=state["summary"],
    )
    db.complete_review(review_id, report, path=DB_PATH)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.get("/api/info")
def info() -> dict:
    return {"provider": llm.PROVIDER, "model": llm.MODEL}


@app.post("/review", response_model=ReviewRecord, status_code=202)
async def review_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> ReviewRecord:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    data = await file.read()
    try:
        text = extract_pdf_text(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this file as a PDF.") from exc
    if not text.strip():
        raise HTTPException(
            status_code=422, detail="No text found in this PDF. Scanned documents aren't supported yet."
        )

    created_at = datetime.now(timezone.utc)
    review_id = db.create_review(file.filename, created_at.isoformat(), path=DB_PATH)
    background_tasks.add_task(_process_review, review_id, file.filename, text)

    return ReviewRecord(
        id=review_id, document_name=file.filename, created_at=created_at, status=ReviewStatus.EXTRACTING
    )


@app.get("/reviews")
def get_reviews() -> list[dict]:
    return db.list_reviews(path=DB_PATH)


@app.get("/reviews/{review_id}", response_model=ReviewRecord)
def get_review(review_id: int) -> ReviewRecord:
    record = db.get_review(review_id, path=DB_PATH)
    if record is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewRecord.model_validate(record)
