import tempfile
import threading
import time
import unittest
from pathlib import Path

from src.app import create_app
from src.collectors.rss_collector import CollectorError, parse_feed
from src.storage.article_repository import ArticleRepository
from src.storage.collection_repository import CollectionRepository
from tests.helpers import ATOM_SAMPLE, RSS_SAMPLE, make_article

FEEDS = {"https://a.example/rss": RSS_SAMPLE, "https://b.example/atom": ATOM_SAMPLE}


def fake_fetch(url, timeout=15):
    if url in FEEDS:
        return parse_feed(FEEDS[url])
    raise CollectorError("Could not fetch feed: the request timed out.")


class WebTestCase(unittest.TestCase):
    sync = True
    fetch_feed = staticmethod(fake_fetch)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = create_app({
            "DATABASE_PATH": str(Path(self._tmp.name) / "web.db"), "SECRET_KEY": "test-key",
            "COLLECT_SYNC": self.sync, "SEED_SOURCES": False, "FETCH_FEED": self.fetch_feed,
            "ALLOW_PRIVATE_FEEDS": False,
        })
        self.client = self.app.test_client()
        self.db = self.app.extensions["oasis_db"]
        self.repo = ArticleRepository(self.db)
        with self.client.session_transaction() as s:
            s["csrf_token"] = "tok"

    def post(self, url, data=None, **kw):
        return self.client.post(url, data={"csrf_token": "tok", **(data or {})}, **kw)

    def add_source(self, name, url):
        return self.post("/sources", {"name": name, "url": url}, follow_redirects=True)


class PageTests(WebTestCase):
    def test_every_page_renders_with_empty_state(self):
        expectations = {
            "/": b"Nothing collected yet", "/articles": b"No articles collected yet",
            "/sources": b"No sources configured", "/activity": b"No collection runs yet",
            "/settings": b"Default article sorting", "/calendar": b"Month",
        }
        for url, text in expectations.items():
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, url)
            self.assertIn(text, res.data, url)
            for label in (b"Dashboard", b"News", b"News Feed", b"Data Sources", b"Collection Activity", b"Calendar", b"Settings"):
                self.assertIn(label, res.data)

    def test_unknown_page_is_a_friendly_404(self):
        res = self.client.get("/nope")
        self.assertEqual(res.status_code, 404)
        self.assertNotIn(b"Traceback", res.data)

    def test_security_headers(self):
        res = self.client.get("/")
        self.assertIn("default-src 'self'", res.headers["Content-Security-Policy"])
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")

    def test_internal_files_are_not_served(self):
        for url in ("/static/../config/settings.py", "/config/settings.py", "/static/%2e%2e/run.py", "/run.py"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.get("/static/css/style.css").status_code, 200)

    def test_unhandled_errors_do_not_leak_details(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.app.add_url_rule("/boom", "boom", lambda: 1 / 0)
        res = self.client.get("/boom")
        self.assertEqual(res.status_code, 500)
        self.assertNotIn(b"ZeroDivisionError", res.data)
        self.assertNotIn(b"Traceback", res.data)


class CsrfTests(WebTestCase):
    def test_posts_without_valid_token_are_rejected(self):
        self.assertEqual(self.client.post("/collect").status_code, 400)
        self.assertEqual(self.client.post("/collect", data={"csrf_token": "wrong"}).status_code, 400)
        self.assertEqual(self.client.post("/sources", data={"name": "x", "url": "https://x.example/f"}).status_code, 400)
        self.assertEqual(self.client.post("/settings", data={"page_size": "10"}).status_code, 400)
        self.assertEqual(len(CollectionRepository(self.db).recent_runs()), 0)

    def test_forms_contain_a_token(self):
        self.assertIn(b'name="csrf_token"', self.client.get("/sources").data)


class SourceRouteTests(WebTestCase):
    def test_add_edit_toggle_test_delete(self):
        res = self.add_source("Feed A", "https://a.example/rss")
        self.assertIn(b"Source added", res.data)
        self.assertIn(b"https://a.example/rss", res.data)
        sid = self._first_source_id()
        self.assertIn(b"Edit source", self.client.get(f"/sources/{sid}/edit").data)
        res = self.post(f"/sources/{sid}/edit", {"name": "Feed Alpha", "url": "https://a.example/rss"}, follow_redirects=True)
        self.assertIn(b"Feed Alpha", res.data)
        res = self.post(f"/sources/{sid}/test", follow_redirects=True)
        self.assertIn(b"reachable and readable", res.data)
        res = self.post(f"/sources/{sid}/toggle", {"enabled": "0"}, follow_redirects=True)
        self.assertIn(b"Source disabled", res.data)
        res = self.post(f"/sources/{sid}/delete", follow_redirects=True)
        self.assertIn(b"No sources configured", res.data)

    def _first_source_id(self):
        from src.storage.source_repository import SourceRepository
        return SourceRepository(self.db).list_sources()[0]["id"]

    def test_unsafe_urls_are_rejected_and_not_stored(self):
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "http://localhost:8000/x", "ftp://x.example/f"):
            res = self.post("/sources", {"name": "Bad", "url": bad})
            self.assertEqual(res.status_code, 400, bad)
        from src.storage.source_repository import SourceRepository
        self.assertEqual(SourceRepository(self.db).count(), 0)

    def test_input_is_escaped_when_redisplayed(self):
        res = self.post("/sources", {"name": "<script>alert(1)</script>", "url": '"><img src=x>'})
        self.assertNotIn(b"<script>alert(1)</script>", res.data)
        self.assertNotIn(b"<img src=x>", res.data)

    def test_url_test_button_reports_failures_without_saving(self):
        res = self.post("/sources/test", {"name": "N", "url": "https://dead.example/rss"})
        self.assertIn(b"Feed test failed", res.data)
        res = self.post("/sources/test", {"name": "N", "url": "https://b.example/atom"})
        self.assertIn(b"2 entries found", res.data)
        self.assertNotIn(b"<td", self.client.get("/sources").data)

    def test_missing_source_is_404(self):
        self.assertEqual(self.client.get("/sources/999/edit").status_code, 404)
        self.assertEqual(self.post("/sources/999/test").status_code, 404)


class CollectionRouteTests(WebTestCase):
    def test_collect_without_sources_explains_why(self):
        res = self.post("/collect", follow_redirects=True)
        self.assertIn(b"no enabled sources", res.data)
        self.assertEqual(CollectionRepository(self.db).recent_runs(), [])

    def test_collection_stores_real_feed_data_and_never_duplicates(self):
        self.add_source("Feed A", "https://a.example/rss")
        self.add_source("Feed B", "https://b.example/atom")
        self.add_source("Dead", "https://dead.example/rss")
        res = self.post("/collect", follow_redirects=True)
        self.assertIn(b"Completed with errors", res.data)
        self.assertIn(b"timed out", res.data)
        self.assertEqual(self.repo.count(), 4)
        first_total = self.repo.count()
        self.post("/collect")
        self.assertEqual(self.repo.count(), first_total)
        runs = CollectionRepository(self.db).recent_runs()
        self.assertEqual((len(runs), runs[0]["new_articles"], runs[0]["duplicates_skipped"]), (2, 0, 4))
        page = self.client.get("/").data
        self.assertIn(b"Ghana universities launch scholarship for students", page)
        self.assertIn(b"https://example.com/news/scholarship", page)  # original link kept, tracking removed

    def test_disabled_sources_are_not_collected(self):
        self.add_source("Feed A", "https://a.example/rss")
        self.post("/sources/1/toggle", {"enabled": "0"})
        res = self.post("/collect", follow_redirects=True)
        self.assertIn(b"no enabled sources", res.data)

    def test_status_endpoint(self):
        self.assertEqual(self.client.get("/collect/status").get_json(), {"running": False})
        CollectionRepository(self.db).start_run("2026-03-02T12:00:00+00:00", "manual", 3)
        data = self.client.get("/collect/status").get_json()
        self.assertEqual((data["running"], data["sources_total"]), (True, 3))
        self.assertIn(b"Collection in progress", self.client.get("/activity").data)

    def test_second_run_is_refused_while_one_is_running(self):
        self.add_source("Feed A", "https://a.example/rss")
        CollectionRepository(self.db).start_run("2026-03-02T12:00:00+00:00", "manual", 1)
        res = self.post("/collect", follow_redirects=True)
        self.assertIn(b"already in progress", res.data)

    def test_interrupted_runs_are_closed_on_startup(self):
        CollectionRepository(self.db).start_run("2026-03-02T12:00:00+00:00", "manual", 1)
        create_app({"DATABASE_PATH": str(self.db.path), "SECRET_KEY": "k", "SEED_SOURCES": False})
        run = CollectionRepository(self.db).recent_runs()[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("Interrupted", run["error_summary"])


class BackgroundCollectionTests(WebTestCase):
    sync = False

    def test_collection_runs_in_a_background_thread(self):
        self.add_source("Feed A", "https://a.example/rss")
        res = self.post("/collect")
        self.assertEqual(res.status_code, 302)
        deadline = time.time() + 5
        runs = CollectionRepository(self.db)
        while runs.running_run() and time.time() < deadline:
            time.sleep(0.05)
        self.assertIsNone(runs.running_run())
        self.assertEqual(runs.recent_runs()[0]["status"], "completed")
        self.assertEqual(self.repo.count(), 2)


class ArticleRouteTests(WebTestCase):
    def setUp(self):
        super().setUp()
        for i in range(12):
            self.repo.upsert(make_article(
                title=f"Fintech startup story {i}" if i < 6 else f"Cholera outbreak report {i}",
                link=f"https://example.com/n/{i}", published=f"2026-03-{i + 1:02d}T10:00:00Z",
                summary=f"Details number {i}"))
        self.repo.upsert(make_article(title="Undated item", link="https://other.example/u", published=None, summary=None))

    def titles(self, query=""):
        html = self.client.get(f"/articles{query}").data.decode()
        return [t for t in ("Fintech startup story 5", "Cholera outbreak report 11", "Undated item") if t in html]

    def test_pagination_and_default_sort(self):
        self.assertNotIn("Next", self.client.get("/articles").data.decode())  # 13 items fit one page of 25
        self.post("/settings", {"default_sort": "published_at", "default_category": "", "request_timeout": "15", "page_size": "10"})
        page1 = self.client.get("/articles").data.decode()
        self.assertIn("Page 1 of 2", page1)
        self.assertIn("Next", page1)
        self.assertLess(page1.index("Cholera outbreak report 11"), page1.index("Cholera outbreak report 10"))
        self.assertNotIn("Undated item", page1)  # missing dates sort last
        self.assertIn("Undated item", self.client.get("/articles?page=2").data.decode())
        self.assertIn("Page 2 of 2", self.client.get("/articles?page=99").data.decode())
        self.assertEqual(self.client.get("/articles?page=abc").status_code, 200)

    def test_search_filters_and_sorting(self):
        self.assertEqual(self.titles("?q=fintech&category="), ["Fintech startup story 5"])
        self.assertEqual(self.titles("?q=Details number 11"), ["Cholera outbreak report 11"])  # summary search
        self.assertEqual(self.titles("?category=Health"), ["Cholera outbreak report 11"])
        self.assertEqual(self.titles("?source=Example News&q=undated"), ["Undated item"])
        self.assertIn(b"No articles match", self.client.get("/articles?q=zzzz").data)
        self.assertEqual(self.client.get("/articles?sort=drop table&category=bogus").status_code, 200)
        self.assertEqual(self.client.get("/articles?sort=collected_at").status_code, 200)

    def test_default_category_setting_and_explicit_all(self):
        self.post("/settings", {"default_sort": "published_at", "default_category": "Technology", "request_timeout": "15", "page_size": "25"})
        self.assertEqual(self.titles(), ["Fintech startup story 5"])
        self.assertIn("Cholera outbreak report 11", self.client.get("/articles?category=").data.decode())

    def test_detail_editorial_and_missing_fields(self):
        item = self.repo.search(query="Undated item")[0]
        page = self.client.get(f"/articles/{item.id}").data
        self.assertIn(b"Not provided by the source", page)
        self.assertIn(b"provided no summary", page)
        res = self.post(f"/articles/{item.id}/editorial", {"status": "Under Review", "notes": "check with desk"}, follow_redirects=True)
        self.assertIn(b"Editorial details saved", res.data)
        self.assertIn(b"check with desk", res.data)
        self.assertEqual(self.repo.get(item.id).status, "Under Review")
        res = self.post(f"/articles/{item.id}/editorial", {"status": "Published", "notes": ""}, follow_redirects=True)
        self.assertIn(b"valid editorial status", res.data)
        self.assertEqual(self.repo.get(item.id).status, "Under Review")
        self.assertEqual(self.client.get("/articles/99999").status_code, 404)
        self.assertEqual(self.post("/articles/99999/editorial", {"status": "New"}).status_code, 404)

    def test_feed_content_is_escaped(self):
        self.repo.upsert(make_article(title="<script>alert('x')</script>", link="https://evil.example/1",
                                      summary="<img src=x onerror=alert(1)>"))
        for url in ("/articles", "/", f"/articles/{self.repo.search(query='alert')[0].id}"):
            html = self.client.get(url).data
            self.assertNotIn(b"<script>alert", html, url)
            self.assertNotIn(b"<img src=x", html, url)

    def test_overview_statistics_come_from_the_database(self):
        html = self.client.get("/").data.decode()
        self.assertIn(">13<", html)  # total articles
        self.assertIn("Health", html)
        self.assertIn("Technology", html)


class SettingsRouteTests(WebTestCase):
    def test_save_and_reload(self):
        res = self.post("/settings", {"default_sort": "collected_at", "default_category": "Health",
                                      "request_timeout": "20", "page_size": "50"}, follow_redirects=True)
        self.assertIn(b"Settings saved", res.data)
        self.assertIn(b'value="20"', res.data)

    def test_invalid_values_rejected(self):
        good = {"default_sort": "published_at", "default_category": "", "request_timeout": "15", "page_size": "25"}
        for change in ({"default_sort": "title"}, {"default_category": "Nonsense"}, {"request_timeout": "0"},
                       {"request_timeout": "9999"}, {"request_timeout": "abc"}, {"page_size": "1000"}):
            self.assertEqual(self.post("/settings", {**good, **change}).status_code, 400, change)


if __name__ == "__main__":
    unittest.main()
