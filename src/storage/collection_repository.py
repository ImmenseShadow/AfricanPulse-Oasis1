"""History of collection runs and their per source results."""
from __future__ import annotations

from typing import Optional

from src.storage.database import Database

MAX_ERROR_CHARS = 500


class CollectionRepository:
    def __init__(self, db: Database):
        self.db = db

    def start_run(self, started_at: str, trigger: str, sources_attempted: int) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "INSERT INTO collection_runs (trigger, status, started_at, sources_attempted) "
                "VALUES (?, 'running', ?, ?)",
                (trigger, started_at, sources_attempted),
            ).lastrowid

    def add_source_result(self, run_id: int, result) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO collection_run_sources "
                "(run_id, source_name, ok, fetched, inserted, duplicates, invalid, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, result.source_name, int(result.ok), result.fetched, result.inserted,
                 result.updated + result.duplicates, result.invalid, result.error),
            )

    def finish_run(self, run_id: int, finished_at: str, results: list) -> str:
        failed = [r for r in results if not r.ok]
        if results and len(failed) == len(results):
            status = "failed"
        elif failed:
            status = "completed_with_errors"
        else:
            status = "completed"
        summary = "; ".join(f"{r.source_name}: {r.error}" for r in failed)[:MAX_ERROR_CHARS] or None
        with self.db.connect() as conn:
            conn.execute(
                """UPDATE collection_runs SET status = ?, finished_at = ?, articles_discovered = ?,
                       new_articles = ?, duplicates_skipped = ?, invalid_entries = ?,
                       sources_failed = ?, error_summary = ? WHERE id = ?""",
                (status, finished_at, sum(r.fetched for r in results),
                 sum(r.inserted for r in results),
                 sum(r.updated + r.duplicates for r in results),
                 sum(r.invalid for r in results), len(failed), summary, run_id),
            )
        return status

    def fail_run(self, run_id: int, finished_at: str, message: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE collection_runs SET status = 'failed', finished_at = ?, error_summary = ? WHERE id = ?",
                (finished_at, message[:MAX_ERROR_CHARS], run_id),
            )

    def mark_interrupted(self, finished_at: str) -> int:
        """Runs still marked running at startup were cut off by a shutdown."""
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE collection_runs SET status = 'failed', finished_at = ?, "
                "error_summary = 'Interrupted: the application stopped before this run finished.' "
                "WHERE status = 'running'",
                (finished_at,),
            ).rowcount

    def running_run(self) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM collection_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def latest_run(self) -> Optional[dict]:
        runs = self.recent_runs(1, with_sources=False)
        return runs[0] if runs else None

    def sources_done(self, run_id: int) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM collection_run_sources WHERE run_id = ?", (run_id,)
            ).fetchone()[0]

    def recent_runs(self, limit: int = 25, with_sources: bool = True) -> list[dict]:
        with self.db.connect() as conn:
            runs = [dict(r) for r in conn.execute(
                "SELECT * FROM collection_runs ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)
            )]
            if with_sources:
                for run in runs:
                    run["sources"] = [dict(r) for r in conn.execute(
                        "SELECT * FROM collection_run_sources WHERE run_id = ? ORDER BY id", (run["id"],)
                    )]
        return runs
