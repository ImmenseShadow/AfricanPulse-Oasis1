from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from werkzeug.security import generate_password_hash, check_password_hash

from src.storage.database import Database


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_user(self, username: str, password: str, role: str = "viewer", active: bool = True) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?)",
                (username.strip(), generate_password_hash(password), role, int(active), datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            return int(cursor.lastrowid)

    def get_by_username(self, username: str) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return dict(row) if row else None

    def get(self, user_id: int) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [dict(r) for r in rows]

    def verify_password(self, username: str, password: str) -> Optional[dict]:
        user = self.get_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            return user
        return None

    def update_role(self, user_id: int, role: str) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            return cursor.rowcount > 0

    def set_active(self, user_id: int, active: bool) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
            return cursor.rowcount > 0

    def update_last_login(self, user_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), user_id),
            )
