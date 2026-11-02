"""SQLite storage for calendar events and communications schedules."""
from __future__ import annotations

from datetime import datetime, timezone

from src.storage.database import Database


class CalendarRepository:
    def __init__(self, db: Database):
        self.db = db

    def list_between(self, start: str, end: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM calendar_items
                   WHERE start_at < ? AND end_at > ?
                   ORDER BY all_day DESC, start_at, title""",
                (end, start),
            ).fetchall()
        return [dict(row) for row in rows]

    def upcoming(self, now: str, limit: int = 6) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM calendar_items WHERE start_at >= ?
                   AND status != 'cancelled' ORDER BY start_at, title LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, item_id: int) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM calendar_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def create(self, item: dict) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fields = (
            "kind", "title", "description", "start_at", "end_at", "all_day", "location",
            "category", "color", "status", "notes", "reminder_minutes",
        )
        values = [item.get(field) for field in fields]
        with self.db.connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO calendar_items ({', '.join(fields)}, created_at, updated_at) "
                f"VALUES ({', '.join('?' for _ in fields)}, ?, ?)",
                [*values, now, now],
            )
            return cursor.lastrowid

    def update(self, item_id: int, item: dict) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fields = (
            "kind", "title", "description", "start_at", "end_at", "all_day", "location",
            "category", "color", "status", "notes", "reminder_minutes",
        )
        with self.db.connect() as conn:
            cursor = conn.execute(
                f"UPDATE calendar_items SET "
                f"{', '.join(f'{field} = ?' for field in fields)}, updated_at = ? WHERE id = ?",
                [*(item.get(field) for field in fields), now, item_id],
            )
            return cursor.rowcount > 0

    def update_status(self, item_id: int, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE calendar_items SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, item_id),
            )
            return cursor.rowcount > 0

    def delete(self, item_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM calendar_items WHERE id = ?", (item_id,))
            return cursor.rowcount > 0