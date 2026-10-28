"""News source records: configuration plus the outcome of the latest fetch."""
from __future__ import annotations

from typing import Optional

from src.storage.database import Database


class SourceRepository:
    def __init__(self, db: Database):
        self.db = db

    def list_sources(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sources ORDER BY LOWER(name), id").fetchall()
        return [dict(r) for r in rows]

    def get(self, source_id: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def name_exists(self, name: str, exclude_id: Optional[int] = None) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sources WHERE LOWER(name) = LOWER(?) AND id IS NOT ?",
                (name, exclude_id),
            ).fetchone()
        return row is not None

    def add(self, name: str, feed_url: str, created_at: str, enabled: bool = True) -> int:
        """Insert a source. Raises sqlite3.IntegrityError if the URL already exists."""
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sources (name, feed_url, enabled, created_at) VALUES (?, ?, ?, ?)",
                (name, feed_url, int(enabled), created_at),
            )
            return cursor.lastrowid

    def add_if_missing(self, name: str, feed_url: str, created_at: str, enabled: bool) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO sources (name, feed_url, enabled, created_at) VALUES (?, ?, ?, ?)",
                (name, feed_url, int(enabled), created_at),
            )
            return cursor.rowcount > 0

    def update(self, source_id: int, name: str, feed_url: str) -> bool:
        """Edit a source. Articles stored under the old name follow the rename."""
        with self.db.connect() as conn:
            row = conn.execute("SELECT name FROM sources WHERE id = ?", (source_id,)).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE sources SET name = ?, feed_url = ? WHERE id = ?", (name, feed_url, source_id)
            )
            if row["name"] != name:
                conn.execute("UPDATE articles SET source = ? WHERE source = ?", (name, row["name"]))
            return True

    def set_enabled(self, source_id: int, enabled: bool) -> bool:
        with self.db.connect() as conn:
            return conn.execute(
                "UPDATE sources SET enabled = ? WHERE id = ?", (int(enabled), source_id)
            ).rowcount > 0

    def delete(self, source_id: int) -> bool:
        """Remove the source only. Already collected articles are kept."""
        with self.db.connect() as conn:
            return conn.execute("DELETE FROM sources WHERE id = ?", (source_id,)).rowcount > 0

    def record_result(self, feed_url: str, when: str, error: Optional[str] = None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE sources SET last_fetched_at = ?, last_status = ?, last_error = ? WHERE feed_url = ?",
                (when, "error" if error else "ok", error, feed_url),
            )

    def count(self, enabled_only: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM sources" + (" WHERE enabled = 1" if enabled_only else "")
        with self.db.connect() as conn:
            return conn.execute(sql).fetchone()[0]
