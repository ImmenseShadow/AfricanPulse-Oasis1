import unittest

from config.settings import FeedSource
from src.collectors.rss_collector import CollectorError
from src.services.source_service import SourceService, ValidationError, validate_feed_url, validate_name
from src.storage.settings_repository import SettingsRepository
from src.storage.source_repository import SourceRepository
from tests.helpers import make_article
from tests.test_database import DatabaseTestCase


def fake_fetch(url, timeout=15):
    if "broken" in url:
        raise CollectorError("Could not fetch feed: simulated problem")
    return [{"title": "x", "link": "https://x.example/1"}] * 3


class UrlValidationTests(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertEqual(validate_feed_url(" https://news.example/feed.xml "), "https://news.example/feed.xml")
        validate_feed_url("http://news.example/rss")

    def test_rejects_unsafe_schemes_and_malformed_urls(self):
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.example/f", "data:text/html,hi",
                    "//no-scheme.example/f", "https://", "not a url", "", "   ",
                    "https://user:pw@news.example/f", "https://news.example:notaport/f",
                    "https://news.example/\nfeed", "https://x.example/" + "a" * 3000):
            with self.assertRaises(ValidationError, msg=bad):
                validate_feed_url(bad)

    def test_rejects_local_and_private_hosts_by_default(self):
        for bad in ("http://localhost/rss", "http://127.0.0.1/rss", "http://192.168.1.5/rss",
                    "http://10.0.0.2/rss", "http://[::1]/rss", "http://169.254.169.254/latest",
                    "http://2130706433/rss", "http://app.localhost/rss"):
            with self.assertRaises(ValidationError, msg=bad):
                validate_feed_url(bad)
        self.assertEqual(validate_feed_url("http://127.0.0.1:8000/rss", allow_private=True), "http://127.0.0.1:8000/rss")

    def test_name_validation(self):
        self.assertEqual(validate_name("  BBC \n Africa "), "BBC Africa")
        for bad in ("", "   ", "x" * 81):
            with self.assertRaises(ValidationError):
                validate_name(bad)


class SourceServiceTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.sources = SourceRepository(self.db)
        self.service = SourceService(self.sources, fetch=fake_fetch)

    def test_add_edit_toggle_delete(self):
        sid = self.service.add("Feed One", "https://one.example/rss")
        row = self.sources.get(sid)
        self.assertEqual((row["name"], row["enabled"]), ("Feed One", 1))
        self.service.update(sid, "Feed Uno", "https://uno.example/rss")
        self.assertEqual(self.sources.get(sid)["feed_url"], "https://uno.example/rss")
        self.service.set_enabled(sid, False)
        self.assertEqual(self.sources.get(sid)["enabled"], 0)
        self.service.delete(sid)
        self.assertIsNone(self.sources.get(sid))
        with self.assertRaises(ValidationError):
            self.service.delete(sid)

    def test_duplicates_rejected(self):
        self.service.add("Feed One", "https://one.example/rss")
        with self.assertRaises(ValidationError):
            self.service.add("feed one", "https://other.example/rss")
        with self.assertRaises(ValidationError):
            self.service.add("Another", "https://one.example/rss")

    def test_rename_moves_stored_articles_and_delete_keeps_them(self):
        self.repo.upsert(make_article())  # source "Example News"
        sid = self.service.add("Example News", "https://example.com/feed")
        self.service.update(sid, "Renamed News", "https://example.com/feed")
        self.assertEqual(self.repo.search()[0].source, "Renamed News")
        self.service.delete(sid)
        self.assertEqual(self.repo.count(), 1)

    def test_feed_test(self):
        self.assertEqual(self.service.test("https://ok.example/rss"), 3)
        with self.assertRaises(ValidationError) as ctx:
            self.service.test("https://broken.example/rss")
        self.assertIn("simulated problem", str(ctx.exception))
        with self.assertRaises(ValidationError):
            self.service.test("javascript:alert(1)")

    def test_seeding_happens_once(self):
        settings = SettingsRepository(self.db)
        cfg = [FeedSource("Seeded", "https://seed.example/rss"), FeedSource("Bad", "ftp://bad.example")]
        self.assertEqual(self.service.seed_from_config(cfg, settings), 1)
        self.service.delete(self.sources.list_sources()[0]["id"])
        self.assertEqual(self.service.seed_from_config(cfg, settings), 0)
        self.assertEqual(self.sources.count(), 0)


if __name__ == "__main__":
    unittest.main()
