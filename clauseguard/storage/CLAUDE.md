# clauseguard/storage/

Audit history persistence, and -- since the async rework -- the source of
truth for a review's progress. `db.py`: stdlib `sqlite3`, one table
(`reviews`), no ORM: a single-table JSON-blob store doesn't need one.

A row exists from the moment a PDF is uploaded, before any agent has run,
not just once a report is ready. That's deliberate: it's what lets `GET
/reviews/{id}` be polled from a browser that just refreshed and has no
other memory of the review it was watching -- see FLOW.md.

- `create_review(document_name, created_at, path) -> id` -- inserts with
  `status='extracting'`. Called synchronously in the request, before the
  background task starts.
- `update_status(id, status, path)` -- called from `agents/graph.py`'s
  `on_stage` callback as the pipeline moves between stages.
- `complete_review(id, report, path)` -- sets `status='done'` and stores
  the full `ReviewReport` as JSON.
- `fail_review(id, error, path)` -- sets `status='failed'` with a
  human-readable message (no traceback -- that goes to server logs, not
  the client).
- `get_review(id, path) -> dict | None` -- full row, `report` parsed back
  into a `ReviewReport` if present.
- `list_reviews(path) -> list[dict]` -- `id, document_name, created_at,
  status` for every review, in-progress ones included (fetch one by id
  for its full report or error).

DB file location: `CLAUSEGUARD_DB` env var, defaults to `clauseguard.db`
in the working directory. Schema migration is a plain idempotent `ALTER
TABLE ... ADD COLUMN` wrapped in a try/except on `sqlite3.OperationalError`
(a database from before status tracking existed just gets the columns
added on next connect) -- rows that already have a `report_json` are
backfilled to `status='done'` in the same pass, since they finished
before this column existed and treating them as freshly-uploaded would
be wrong. See `tests/test_db.py` for the migration test against a
hand-built legacy schema.
