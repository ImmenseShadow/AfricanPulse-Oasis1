from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from src.storage.database import Database


class EditorialRepository:
    def __init__(self, db: Database):
        self.db = db

    def add_note(self, article_id: int, author_id: int, body: str) -> dict:
        cleaned = (body or "").strip()
        if not cleaned:
            raise ValueError("Note content is required.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO article_notes (article_id, author_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (article_id, author_id, cleaned, now, now),
            )
            note_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM article_notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row)

    def list_notes(self, article_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT n.*, u.username FROM article_notes n JOIN users u ON u.id = n.author_id WHERE n.article_id = ? ORDER BY n.created_at DESC",
                (article_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_collection(self, name: str, description: str = "", owner_id: Optional[int] = None, is_shared: bool = False) -> dict:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("Collection name is required.")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO collections (name, description, owner_id, is_shared, created_at) VALUES (?, ?, ?, ?, ?)",
                (cleaned, description or "", owner_id, int(bool(is_shared)), now),
            )
            row = conn.execute("SELECT * FROM collections WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
        return dict(row)

    def list_collections(self, user_id: Optional[int] = None) -> list[dict]:
        with self.db.connect() as conn:
            if user_id is None:
                rows = conn.execute("SELECT * FROM collections ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM collections WHERE owner_id = ? OR is_shared = 1 ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def bookmark(self, user_id: int, article_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO bookmarks (user_id, article_id, created_at) VALUES (?, ?, ?)",
                (user_id, article_id, now),
            )
            return cursor.rowcount > 0

    def unbookmark(self, user_id: int, article_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM bookmarks WHERE user_id = ? AND article_id = ?", (user_id, article_id))
            return cursor.rowcount > 0

    def add_article_to_collection(self, collection_id: int, article_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO collection_articles (collection_id, article_id, created_at) VALUES (?, ?, ?)",
                (collection_id, article_id, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            return cursor.rowcount > 0

    def remove_article_from_collection(self, collection_id: int, article_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM collection_articles WHERE collection_id = ? AND article_id = ?", (collection_id, article_id))
            return cursor.rowcount > 0

    def add_tag(self, name: str) -> dict:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("Tag name is required.")
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO editorial_tags (name, created_at) VALUES (?, ?)",
                (cleaned, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            if cursor.rowcount == 0:
                row = conn.execute("SELECT * FROM editorial_tags WHERE name = ?", (cleaned,)).fetchone()
                return dict(row)
            row = conn.execute("SELECT * FROM editorial_tags WHERE name = ?", (cleaned,)).fetchone()
        return dict(row)

    def list_tags(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM editorial_tags ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def set_article_tags(self, article_id: int, tag_names: Iterable[str]) -> list[dict]:
        names = {str(name).strip() for name in tag_names if str(name).strip()}
        with self.db.connect() as conn:
            conn.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))
            for name in sorted(names):
                tag = conn.execute("SELECT id FROM editorial_tags WHERE name = ?", (name,)).fetchone()
                if tag is None:
                    cursor = conn.execute(
                        "INSERT INTO editorial_tags (name, created_at) VALUES (?, ?)",
                        (name, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                    )
                    tag_id = int(cursor.lastrowid)
                else:
                    tag_id = int(tag["id"])
                conn.execute("INSERT INTO article_tags (article_id, tag_id) VALUES (?, ?)", (article_id, tag_id))
        return self.list_article_tags(article_id)

    def list_article_tags(self, article_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT t.* FROM article_tags a JOIN editorial_tags t ON t.id = a.tag_id WHERE a.article_id = ? ORDER BY t.name",
                (article_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_audit_logs(self, limit: int = 50) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT l.*, u.username FROM audit_logs l LEFT JOIN users u ON u.id = l.user_id ORDER BY l.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def log(self, user_id: Optional[int], action: str, resource: str, resource_id: Optional[int] = None, details: Optional[str] = None) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, resource, resource_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, action, resource, resource_id, details, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
