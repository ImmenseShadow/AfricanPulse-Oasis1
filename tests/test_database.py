import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.storage.article_repository import ArticleRepository
from src.storage.database import Database
from tests.helpers import make_article


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Database(Path(self._tmp.name) / "sub" / "test.db")
        self.db.initialize()
        self.repo = ArticleRepository(self.db)


class InitTests(DatabaseTestCase):
    def test_creates_file_and_tables(self):
        self.assertTrue(self.db.path.exists())
        with self.db.connect() as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"articles", "sources"} <= names)

    def test_initialize_is_idempotent(self):
        self.repo.upsert(make_article())
        self.db.initialize()
        self.assertEqual(self.repo.count(), 1)


class RepositoryTests(DatabaseTestCase):
    def test_save_and_retrieve(self):
        self.assertEqual(self.repo.upsert(make_article()), "inserted")
        stored = self.repo.search()[0]
        self.assertEqual(stored.title, "Health ministry confirms cholera outbreak")
        self.assertEqual(stored.category, "Health")
        self.assertEqual(self.repo.get(stored.id).url, "https://example.com/news/cholera")

    def test_update_keeps_editorial_fields_and_first_collection_time(self):
        self.repo.upsert(make_article())
        stored = self.repo.search()[0]
        self.repo.update_editorial(stored.id, "Under Review", "check with desk")
        newer = make_article(title="Updated headline on cholera outbreak")
        newer.collected_at = newer.last_seen_at = "2026-04-01T00:00:00+00:00"
        self.assertEqual(self.repo.upsert(newer), "updated")
        after = self.repo.get(stored.id)
        self.assertEqual(after.title, "Updated headline on cholera outbreak")
        self.assertEqual(after.status, "Under Review")
        self.assertEqual(after.notes, "check with desk")
        self.assertEqual(after.collected_at, stored.collected_at)
        self.assertEqual(after.last_seen_at, "2026-04-01T00:00:00+00:00")

    def test_invalid_status_rejected(self):
        self.repo.upsert(make_article())
        article_id = self.repo.search()[0].id
        with self.assertRaises(ValueError):
            self.repo.update_editorial(article_id, "Published", "")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect() as conn:
                conn.execute("UPDATE articles SET status='Published' WHERE id=?", (article_id,))

    def test_filters_search_and_sort(self):
        self.repo.upsert(make_article())
        self.repo.upsert(make_article(
            title="New fintech app", link="https://example.com/news/fintech",
            published=None, summary="100% mobile_payments"))
        self.assertEqual(self.repo.count(category="Health"), 1)
        self.assertEqual(self.repo.count(source="Example News"), 2)
        self.assertEqual(self.repo.count(query="mobile_pay"), 1)
        self.assertEqual(self.repo.count(query="100%"), 1)
        self.assertEqual(self.repo.count(query="%"), 1)  # literal percent, not a wildcard
        by_pub = self.repo.search(sort_by="published_at")
        self.assertIsNotNone(by_pub[0].published_at)  # missing dates sort last
        self.assertIsNone(by_pub[-1].published_at)
        with self.assertRaises(ValueError):
            self.repo.search(sort_by="title; DROP TABLE articles")

    def test_stats(self):
        self.assertEqual(self.repo.stats()["total"], 0)
        self.repo.upsert(make_article())
        stats = self.repo.stats()
        self.assertEqual((stats["total"], stats["sources"]), (1, 1))
        self.assertEqual(stats["by_status"], {"New": 1})


if __name__ == "__main__":
    unittest.main()


class MigrationTests(unittest.TestCase):
    def test_phase1_database_is_upgraded_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """CREATE TABLE sources (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                       feed_url TEXT NOT NULL UNIQUE, last_fetched_at TEXT, last_status TEXT, last_error TEXT);
                   INSERT INTO sources (name, feed_url, last_status) VALUES ('Old Feed', 'https://old.example/rss', 'ok');
                   CREATE TABLE articles (id INTEGER PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                       source TEXT NOT NULL, url TEXT NOT NULL, published_at TEXT, collected_at TEXT NOT NULL,
                       last_seen_at TEXT NOT NULL, summary TEXT, category TEXT NOT NULL DEFAULT 'Uncategorized',
                       status TEXT NOT NULL DEFAULT 'New', notes TEXT NOT NULL DEFAULT '');
                   INSERT INTO articles (dedupe_key, title, source, url, collected_at, last_seen_at)
                       VALUES ('k', 'Kept', 'Old Feed', 'https://old.example/a', 't', 't');"""
            )
            conn.commit()
            conn.close()
            db = Database(path)
            db.initialize()
            db.initialize()
            with db.connect() as c:
                source = dict(c.execute("SELECT * FROM sources").fetchone())
                self.assertEqual((source["name"], source["enabled"], source["last_status"]), ("Old Feed", 1, "ok"))
                self.assertEqual(c.execute("SELECT title FROM articles").fetchone()[0], "Kept")
                self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 3)
                # Increment 2 additions: defaults for old rows and a source reference per article
                self.assertEqual((source["source_type"], source["alert_topic"]), ("rss", None))
                ref = dict(c.execute("SELECT * FROM article_sources").fetchone())
                self.assertEqual((ref["source_name"], ref["source_type"], ref["source_id"]), ("Old Feed", "rss", source["id"]))
                self.assertEqual(c.execute("SELECT COUNT(*) FROM article_sources").fetchone()[0], 1)
