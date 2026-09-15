"""Audit history persistence, and the source of truth for review progress.

A review is a row from the moment the PDF is uploaded, not just once it
finishes: this is what lets a browser refresh reconnect to a review that's
still running instead of losing track of it. `status` walks through the
same stages as agents/graph.py (extracting -> analyzing -> summarizing)
before landing on done or failed -- see clauseguard/CLAUDE.md.
"""

import sqlite3
from pathlib import Path

from clauseguard.models.schemas import ReviewReport, ReviewStatus

DEFAULT_DB_PATH = "clauseguard.db"


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'extracting',
            error TEXT,
            report_json TEXT
        )"""
    )
    migrated = False
    for column, ddl in (("status", "TEXT NOT NULL DEFAULT 'extracting'"), ("error", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE reviews ADD COLUMN {column} {ddl}")
            migrated = True
        except sqlite3.OperationalError:
            pass  # already migrated -- pre-existing databases from before status tracking
    if migrated:
        # New rows default to 'extracting', but a pre-existing row with a report already has
        # one -- it finished before status tracking existed, so it's really 'done', not stuck.
        conn.execute("UPDATE reviews SET status = 'done' WHERE report_json IS NOT NULL")
        conn.commit()
    return conn


def create_review(document_name: str, created_at: str, path: str | Path = DEFAULT_DB_PATH) -> int:
    """Inserts a row the moment a PDF is accepted, before any agent has run."""
    conn = _connect(path)
    try:
        # '' rather than NULL: pre-migration databases have report_json NOT NULL, and SQLite
        # can't relax that without a full table rebuild. '' is falsy same as NULL wherever this
        # column is read (_row_to_record), so it means the same thing without the DDL surgery.
        cur = conn.execute(
            "INSERT INTO reviews (document_name, created_at, status, report_json) VALUES (?, ?, ?, ?)",
            (document_name, created_at, ReviewStatus.EXTRACTING.value, ""),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_status(review_id: int, status: ReviewStatus, path: str | Path = DEFAULT_DB_PATH) -> None:
    conn = _connect(path)
    try:
        conn.execute("UPDATE reviews SET status = ? WHERE id = ?", (status.value, review_id))
        conn.commit()
    finally:
        conn.close()


def complete_review(review_id: int, report: ReviewReport, path: str | Path = DEFAULT_DB_PATH) -> None:
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE reviews SET status = ?, report_json = ? WHERE id = ?",
            (ReviewStatus.DONE.value, report.model_dump_json(), review_id),
        )
        conn.commit()
    finally:
        conn.close()


def fail_review(review_id: int, error: str, path: str | Path = DEFAULT_DB_PATH) -> None:
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE reviews SET status = ?, error = ? WHERE id = ?",
            (ReviewStatus.FAILED.value, error, review_id),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_record(row: tuple) -> dict:
    review_id, document_name, created_at, status, error, report_json = row
    return {
        "id": review_id,
        "document_name": document_name,
        "created_at": created_at,
        "status": status,
        "error": error,
        "report": ReviewReport.model_validate_json(report_json) if report_json else None,
    }


def get_review(review_id: int, path: str | Path = DEFAULT_DB_PATH) -> dict | None:
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT id, document_name, created_at, status, error, report_json FROM reviews WHERE id = ?",
            (review_id,),
        ).fetchone()
        return _row_to_record(row) if row else None
    finally:
        conn.close()


def list_reviews(path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT id, document_name, created_at, status FROM reviews ORDER BY id DESC"
        ).fetchall()
        return [{"id": r[0], "document_name": r[1], "created_at": r[2], "status": r[3]} for r in rows]
    finally:
        conn.close()
