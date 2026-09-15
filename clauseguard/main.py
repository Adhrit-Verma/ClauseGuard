"""FastAPI entrypoint: POST /review runs the full extract -> analyze ->
summarize pipeline over an uploaded PDF and persists the result."""

import io
import os
from datetime import datetime, timezone

import pdfplumber
from fastapi import FastAPI, File, HTTPException, UploadFile

from clauseguard.agents.graph import run_review
from clauseguard.models.schemas import ReviewReport
from clauseguard.storage.db import DEFAULT_DB_PATH, get_report, list_reports, save_report

app = FastAPI(title="ClauseGuard", description="Multi-agent contract & policy review pipeline")

DB_PATH = os.environ.get("CLAUSEGUARD_DB", DEFAULT_DB_PATH)


def extract_pdf_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


@app.post("/review", response_model=ReviewReport)
async def review_document(file: UploadFile = File(...)) -> ReviewReport:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    data = await file.read()
    text = extract_pdf_text(data)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from PDF")

    state = run_review(text)
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
