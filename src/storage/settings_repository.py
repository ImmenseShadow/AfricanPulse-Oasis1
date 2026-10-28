"""Key value application settings stored in SQLite."""
from __future__ import annotations

from typing import Optional

from src.storage.database import Database


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def get_all(self) -> dict[str, str]:
        with self.db.connect() as conn:
            return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM app_settings")}

    def set_many(self, values: dict[str, str]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(values.items()),
            )
