"""Review lifecycle in storage: a row exists from upload onward (status
tracking), not just once a report is ready -- this is what makes GET
/reviews/{id} pollable across a browser refresh. Uses a temp file per test
so tests never touch the real clauseguard.db."""

import sqlite3

from clauseguard.models.schemas import Clause, ExecutiveSummary, ReviewReport, ReviewStatus
from clauseguard.storage import db

REPORT = ReviewReport(
    document_name="nda.pdf",
    created_at="2026-01-01T00:00:00+00:00",
    clauses=[Clause(id="c1", type="liability", text="Cap at $100.", confidence=0.9)],
    findings=[],
    executive_summary=ExecutiveSummary(verdict="low_risk", summary="ok", key_points=[]),
)


def test_create_review_starts_in_extracting_status(tmp_path):
    path = tmp_path / "test.db"
    review_id = db.create_review("nda.pdf", "2026-01-01T00:00:00+00:00", path=path)

    record = db.get_review(review_id, path=path)
    assert record["status"] == ReviewStatus.EXTRACTING.value
    assert record["report"] is None
    assert record["error"] is None


def test_status_transitions_are_visible_mid_review(tmp_path):
    path = tmp_path / "test.db"
    review_id = db.create_review("nda.pdf", "2026-01-01T00:00:00+00:00", path=path)

    db.update_status(review_id, ReviewStatus.ANALYZING, path=path)
    assert db.get_review(review_id, path=path)["status"] == "analyzing"

    db.update_status(review_id, ReviewStatus.SUMMARIZING, path=path)
    assert db.get_review(review_id, path=path)["status"] == "summarizing"


def test_complete_review_stores_full_report(tmp_path):
    path = tmp_path / "test.db"
    review_id = db.create_review("nda.pdf", "2026-01-01T00:00:00+00:00", path=path)

    db.complete_review(review_id, REPORT, path=path)

    record = db.get_review(review_id, path=path)
    assert record["status"] == "done"
    assert record["report"].clauses[0].id == "c1"


def test_fail_review_stores_error_and_no_report(tmp_path):
    path = tmp_path / "test.db"
    review_id = db.create_review("nda.pdf", "2026-01-01T00:00:00+00:00", path=path)

    db.fail_review(review_id, "LLM backend unreachable", path=path)

    record = db.get_review(review_id, path=path)
    assert record["status"] == "failed"
    assert record["error"] == "LLM backend unreachable"
    assert record["report"] is None


def test_list_reviews_includes_status_for_in_progress_and_done(tmp_path):
    path = tmp_path / "test.db"
    done_id = db.create_review("done.pdf", "2026-01-01T00:00:00+00:00", path=path)
    db.complete_review(done_id, REPORT, path=path)
    pending_id = db.create_review("pending.pdf", "2026-01-01T00:01:00+00:00", path=path)

    items = {item["id"]: item["status"] for item in db.list_reviews(path=path)}
    assert items[done_id] == "done"
    assert items[pending_id] == "extracting"


def test_get_review_returns_none_for_unknown_id(tmp_path):
    path = tmp_path / "test.db"
    db.create_review("nda.pdf", "2026-01-01T00:00:00+00:00", path=path)  # ensure table exists
    assert db.get_review(999999, path=path) is None


def test_migrates_pre_status_tracking_schema_without_data_loss(tmp_path):
    # Simulates a database created before status/error columns existed.
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            report_json TEXT NOT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO reviews (document_name, created_at, report_json) VALUES (?, ?, ?)",
        ("old.pdf", "2025-01-01T00:00:00+00:00", REPORT.model_dump_json()),
    )
    conn.commit()
    conn.close()

    items = db.list_reviews(path=path)
    assert len(items) == 1
    assert items[0]["document_name"] == "old.pdf"
    # Backfilled to 'done', not the column default 'extracting' -- it already has a report,
    # so treating it as freshly-uploaded-and-stuck would be wrong.
    assert items[0]["status"] == "done"

    record = db.get_review(items[0]["id"], path=path)
    assert record["report"].clauses[0].id == "c1"  # pre-existing report_json still readable
