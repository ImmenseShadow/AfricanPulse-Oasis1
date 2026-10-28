import unittest

from config.settings import ConfigError, FeedSource, load_sources
from src.collectors.rss_collector import CollectorError, parse_feed
from src.services.news_service import NewsService
from tests.helpers import ATOM_SAMPLE, FIXED_TIME, RSS_SAMPLE
from tests.test_database import DatabaseTestCase

FEEDS = {
    "https://a.example/rss": RSS_SAMPLE,
    "https://b.example/atom": ATOM_SAMPLE,
}


def fake_fetch(url):
    if url == "https://down.example/rss":
        raise CollectorError("Could not fetch feed: simulated outage")
    if url == "https://crash.example/rss":
        raise RuntimeError("secret internal detail")
    return parse_feed(FEEDS[url])


class NewsServiceTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.service = NewsService(self.db, fetch=fake_fetch, now=lambda: FIXED_TIME)
        self.sources = [
            FeedSource("Feed A", "https://a.example/rss"),
            FeedSource("Down Feed", "https://down.example/rss"),
            FeedSource("Feed B", "https://b.example/atom"),
            FeedSource("Disabled", "https://never.example/rss", enabled=False),
        ]
        for s in self.sources:
            self.service.sources.add(s.name, s.feed_url, "2026-01-01T00:00:00+00:00", s.enabled)

    def test_failure_does_not_stop_other_sources(self):
        results = {r.source_name: r for r in self.service.collect(self.sources)}
        self.assertEqual(set(results), {"Feed A", "Down Feed", "Feed B"})
        self.assertFalse(results["Down Feed"].ok)
        self.assertEqual((results["Feed A"].inserted, results["Feed A"].invalid), (2, 1))
        self.assertEqual(results["Feed B"].inserted, 2)
        self.assertEqual(self.repo.count(), 4)

    def test_unexpected_error_is_contained_and_not_leaked(self):
        src = [FeedSource("Crash", "https://crash.example/rss"), FeedSource("Feed B", "https://b.example/atom")]
        results = {r.source_name: r for r in self.service.collect(src)}
        self.assertFalse(results["Crash"].ok)
        self.assertNotIn("secret internal detail", results["Crash"].error)
        self.assertTrue(results["Feed B"].ok)

    def test_repeated_collection_creates_no_duplicates(self):
        self.service.collect(self.sources)
        second = self.service.collect(self.sources)
        self.assertEqual(sum(r.inserted for r in second), 0)
        self.assertEqual(sum(r.updated for r in second), 4)
        self.assertEqual(self.repo.count(), 4)

    def test_source_health_is_recorded(self):
        self.service.collect(self.sources)
        health = {s["name"]: s for s in self.service.sources.list_sources()}
        self.assertEqual(health["Feed A"]["last_status"], "ok")
        self.assertEqual(health["Down Feed"]["last_status"], "error")
        self.assertIn("simulated outage", health["Down Feed"]["last_error"])
        self.assertIsNone(health["Disabled"]["last_status"])

    def test_runs_are_recorded_honestly(self):
        self.service.collect(self.sources)
        run = self.service.runs.recent_runs()[0]
        self.assertEqual(run["status"], "completed_with_errors")
        self.assertEqual((run["sources_attempted"], run["sources_failed"]), (3, 1))
        self.assertEqual((run["articles_discovered"], run["new_articles"]), (5, 4))
        self.assertIn("Down Feed", run["error_summary"])
        self.assertEqual(len(run["sources"]), 3)
        self.service.collect(self.sources)
        second = self.service.runs.recent_runs()[0]
        self.assertEqual(second["new_articles"], 0)
        self.assertEqual(second["duplicates_skipped"], 4)

    def test_all_sources_failing_marks_run_failed(self):
        self.service.collect([FeedSource("Down Feed", "https://down.example/rss")])
        self.assertEqual(self.service.runs.recent_runs()[0]["status"], "failed")


class ConfigTests(unittest.TestCase):
    def test_default_sources_file_loads(self):
        sources = load_sources()
        self.assertTrue(sources)
        self.assertTrue(all(s.feed_url.startswith("http") for s in sources))

    def test_invalid_config_raises(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "s.json"
            bad.write_text(json.dumps({"sources": [{"name": "x", "url": "ftp://x"}]}))
            with self.assertRaises(ConfigError):
                load_sources(bad)
            bad.write_text("{not json")
            with self.assertRaises(ConfigError):
                load_sources(bad)
            with self.assertRaises(ConfigError):
                load_sources(Path(tmp) / "missing.json")


if __name__ == "__main__":
    unittest.main()
