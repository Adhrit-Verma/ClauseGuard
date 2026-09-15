# clauseguard/storage/

Audit history persistence. `db.py` -- stdlib `sqlite3`, one table
(`reviews`), no ORM: a single-table JSON-blob store doesn't need one.

- `save_report(report, path) -> id`
- `get_report(id, path) -> ReviewReport | None`
- `list_reports(path) -> list[dict]` (id, document_name, created_at only --
  fetch a single report for the full JSON)

DB file location: `CLAUSEGUARD_DB` env var, defaults to `clauseguard.db` in
the working directory. The full `ReviewReport` is stored as a JSON blob
(`report_json` column) rather than normalized across tables -- there's no
query pattern yet that needs querying inside a report, just listing and
fetching by id.
