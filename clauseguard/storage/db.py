"""Audit history persistence. Plain stdlib sqlite3 -- one table, no ORM
needed for a single-table JSON-blob store."""

import sqlite3
from pathlib import Path

from clauseguard.models.schemas import ReviewReport

DEFAULT_DB_PATH = "clauseguard.db"


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            report_json TEXT NOT NULL
        )"""
    )
    return conn


def save_report(report: ReviewReport, path: str | Path = DEFAULT_DB_PATH) -> int:
    conn = _connect(path)
    try:
        cur = conn.execute(
            "INSERT INTO reviews (document_name, created_at, report_json) VALUES (?, ?, ?)",
            (report.document_name, report.created_at.isoformat(), report.model_dump_json()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_report(review_id: int, path: str | Path = DEFAULT_DB_PATH) -> ReviewReport | None:
    conn = _connect(path)
    try:
        row = conn.execute("SELECT report_json FROM reviews WHERE id = ?", (review_id,)).fetchone()
        return ReviewReport.model_validate_json(row[0]) if row else None
    finally:
        conn.close()


def list_reports(path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT id, document_name, created_at FROM reviews ORDER BY id DESC"
        ).fetchall()
        return [{"id": r[0], "document_name": r[1], "created_at": r[2]} for r in rows]
    finally:
        conn.close()
