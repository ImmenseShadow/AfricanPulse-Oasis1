"""All SQL for articles lives here; the UI and collectors never write SQL."""
from __future__ import annotations

from typing import Optional

from config.settings import FeedSource
from src.models.article import SOURCE_GOOGLE_ALERT, STATUSES, Article
from src.storage.database import Database

SORT_COLUMNS = {"published_at", "collected_at"}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_article(row) -> Article:
    return Article(
        id=row["id"],
        dedupe_key=row["dedupe_key"],
        title=row["title"],
        source=row["source"],
        url=row["url"],
        published_at=row["published_at"],
        collected_at=row["collected_at"],
        last_seen_at=row["last_seen_at"],
        summary=row["summary"],
        category=row["category"],
        status=row["status"],
        notes=row["notes"],
        publisher=row["publisher"],
        alert_topic=row["alert_topic"],
    )


class ArticleRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, article: Article, source: Optional[FeedSource] = None) -> str:
        """Insert a new article or refresh an existing one.

        Returns "inserted" or "updated". Updates keep the first collection time
        and never touch the editorial status or notes. When a Google Alert finds an article that
        is already stored, the stored record is preserved (only last-seen time and missing
        publisher or topic are filled in) and the alert is added as another source reference.
        """
        seen_at = article.last_seen_at or article.collected_at
        ref = source or FeedSource(article.source, "")
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM articles WHERE dedupe_key = ?", (article.dedupe_key,)
            ).fetchone()
            if existing is None:
                article_id = conn.execute(
                    """INSERT INTO articles
                       (dedupe_key, title, source, url, published_at, collected_at,
                        last_seen_at, summary, category, status, notes, publisher, alert_topic)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        article.dedupe_key, article.title, article.source, article.url,
                        article.published_at, article.collected_at, seen_at, article.summary,
                        article.category, article.status, article.notes,
                        article.publisher, article.alert_topic,
                    ),
                ).lastrowid
                outcome = "inserted"
            else:
                article_id = existing["id"]
                if ref.source_type == SOURCE_GOOGLE_ALERT:
                    conn.execute(
                        """UPDATE articles SET last_seen_at = ?,
                               publisher = COALESCE(publisher, ?),
                               alert_topic = COALESCE(alert_topic, ?)
                           WHERE id = ?""",
                        (seen_at, article.publisher, article.alert_topic, article_id),
                    )
                else:
                    conn.execute(
                        """UPDATE articles SET
                               title = ?,
                               published_at = COALESCE(?, published_at),
                               summary = COALESCE(?, summary),
                               category = ?,
                               last_seen_at = ?
                           WHERE id = ?""",
                        (article.title, article.published_at, article.summary,
                         article.category, seen_at, article_id),
                    )
                outcome = "updated"
            conn.execute(
                """INSERT INTO article_sources
                       (article_id, source_id, source_name, source_type, alert_topic,
                        first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (article_id, source_name) DO UPDATE SET
                       source_id = COALESCE(excluded.source_id, source_id),
                       source_type = excluded.source_type,
                       alert_topic = COALESCE(excluded.alert_topic, alert_topic),
                       last_seen_at = excluded.last_seen_at""",
                (article_id, ref.source_id, ref.name, ref.source_type,
                 ref.alert_topic if ref.source_type == SOURCE_GOOGLE_ALERT else None,
                 seen_at, seen_at),
            )
            return outcome

    def sources_for(self, article_id: int) -> list[dict]:
        """Every source that has found this article, oldest first."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM article_sources WHERE article_id = ? ORDER BY first_seen_at, id",
                (article_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _filters(category, source, status, query) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if query and query.strip():
            like = f"%{_escape_like(query.strip())}%"
            clauses.append(
                "(title LIKE ? ESCAPE '\\' OR COALESCE(summary, '') LIKE ? ESCAPE '\\')"
            )
            params += [like, like]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    def search(
        self,
        category: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        query: Optional[str] = None,
        sort_by: str = "published_at",
        limit: int = 25,
        offset: int = 0,
    ) -> list[Article]:
        if sort_by not in SORT_COLUMNS:
            raise ValueError(f"Unsupported sort column: {sort_by}")
        where, params = self._filters(category, source, status, query)
        sql = (
            f"SELECT * FROM articles {where} "
            f"ORDER BY {sort_by} IS NULL, {sort_by} DESC, id DESC LIMIT ? OFFSET ?"
        )
        with self.db.connect() as conn:
            rows = conn.execute(sql, [*params, limit, offset]).fetchall()
        return [_row_to_article(r) for r in rows]

    def count(self, category=None, source=None, status=None, query=None) -> int:
        where, params = self._filters(category, source, status, query)
        with self.db.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM articles {where}", params).fetchone()[0]

    def get(self, article_id: int) -> Optional[Article]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return _row_to_article(row) if row else None

    def distinct_sources(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT source FROM articles ORDER BY source").fetchall()
        return [r["source"] for r in rows]

    def update_editorial(self, article_id: int, status: str, notes: str) -> bool:
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status}")
        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE articles SET status = ?, notes = ? WHERE id = ?",
                (status, notes.strip(), article_id),
            )
            return cursor.rowcount > 0

    def category_counts(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS n FROM articles GROUP BY category ORDER BY n DESC, category"
            ).fetchall()
        return {r["category"]: r["n"] for r in rows}

    def count_collected_since(self, since_iso: str) -> int:
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM articles WHERE collected_at >= ?", (since_iso,)
            ).fetchone()[0]

    def stats(self) -> dict:
        with self.db.connect() as conn:
            total, sources, last = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT source), MAX(collected_at) FROM articles"
            ).fetchone()
            by_status = {
                r["status"]: r["n"]
                for r in conn.execute("SELECT status, COUNT(*) AS n FROM articles GROUP BY status")
            }
        return {"total": total, "sources": sources, "last_collected": last, "by_status": by_status}
