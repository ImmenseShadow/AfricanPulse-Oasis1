import tempfile
import threading
import time
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from src.app import create_app
from src.collectors.rss_collector import CollectorError, parse_feed
from src.models.article import ROLE_EDITOR, ROLE_VIEWER, STATUSES
from src.routes.dashboard import _chart_segments
from src.storage.article_repository import ArticleRepository
from src.storage.collection_repository import CollectionRepository
from src.storage.editorial_repository import EditorialRepository
from src.storage.user_repository import UserRepository
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

    def test_activity_page_does_not_auto_open_news_dropdown(self):
        response = self.client.get("/activity")
        html = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('<summary aria-current="page">News</summary>', html)
        self.assertNotIn('<details class="nav-group" open', html)

    def test_collection_error_does_not_auto_open_news_dropdown(self):
        response = self.post("/collect", follow_redirects=True)
        html = response.data.decode()

        self.assertIn("There are no enabled sources", html)
        self.assertNotIn('<details class="nav-group" open', html)

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

    def test_login_and_collection_forms_include_csrf_tokens(self):
        self.assertIn(b'name="csrf_token"', self.client.get("/login").data)
        self.assertIn(b'name="csrf_token"', self.client.get("/collections").data)

    def test_login_form_can_authenticate_with_csrf(self):
        user_id = UserRepository(self.db).create_user("login-editor", "test-password", ROLE_EDITOR)

        response = self.post("/login", {"username": "login-editor", "password": "test-password"})

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], user_id)


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


class CategoryIntelligenceRouteTests(WebTestCase):
    def setUp(self):
        super().setUp()
        self.repo.upsert(make_article(
            title="Election reform briefing",
            link="https://example.com/election/1",
            published="2026-04-01T10:00:00Z",
            summary="Parliament debates election rules.",
            category="Politics and Governance",
        ))
        self.repo.upsert(make_article(
            title="New health initiative",
            link="https://example.com/health/1",
            published="2026-04-02T10:00:00Z",
            summary="Hospital network expands access.",
            category="Health",
        ))
        self.repo.upsert(make_article(
            title="Medicine research update",
            link="https://example.com/health/2",
            published="2026-04-03T10:00:00Z",
            summary="Clinical trial results published.",
            category="Health",
        ))

    def test_dashboard_category_component_links_to_the_intelligence_page(self):
        html = self.client.get("/").data.decode()
        self.assertIn("View Category Insights", html)
        self.assertIn('/category-intelligence?source=dashboard', html)

    def test_category_intelligence_requires_dashboard_navigation_context(self):
        self.assertEqual(self.client.get("/category-intelligence").status_code, 302)
        res = self.client.get("/category-intelligence?source=dashboard")
        self.assertEqual(res.status_code, 200)
        body = res.data.decode()
        self.assertIn("News Category Intelligence", body)
        self.assertIn("Politics and Governance", body)
        self.assertIn("Health", body)

    def test_donut_segments_exclude_uncategorized_from_proportions(self):
        counts = {
            "Uncategorized": 47,
            "Politics and Governance": 9,
            "Business and Economy": 8,
            "Technology": 6,
            "Health": 4,
        }

        self.app.config["SERVER_NAME"] = "example.com"
        with self.app.app_context():
            segments = _chart_segments(counts, "Health")

        self.assertNotIn("Uncategorized", [segment["name"] for segment in segments])
        self.assertEqual([segment["name"] for segment in segments[:4]], [
            "Politics and Governance",
            "Business and Economy",
            "Technology",
            "Health",
        ])
        self.assertEqual(sum(segment["count"] for segment in segments), 27)
        self.assertAlmostEqual(sum(segment["percent"] for segment in segments), 100.0, delta=0.1)
        with self.app.app_context():
            empty_segments = _chart_segments({"Uncategorized": 4, "Health": 0}, "Health")
        self.assertEqual(empty_segments, [])

    def test_category_intelligence_defaults_to_categorized_data(self):
        response = self.client.get("/category-intelligence?source=dashboard")
        body = response.data.decode()

        self.assertIn('data-category="Politics and Governance" role="button"', body)
        self.assertNotIn('data-category="Uncategorized" role="button"', body)
        self.assertIn('<span>Uncategorized</span>', body)
        self.assertIn("Politics and Governance", body)

    def test_category_reference_omits_distribution_statistics(self):
        response = self.client.get("/category-intelligence?source=dashboard")
        body = response.data.decode()
        reference = body.split("Understanding the Categories", 1)[1].split(
            '<section class="card" id="selected-category-panel">', 1
        )[0]

        for category in (
            "Politics and Governance", "Technology and Innovation", "Business and Economy",
            "Education", "Environment", "Security", "Health", "International Affairs",
            "Culture and Society", "Science and Research",
        ):
            self.assertIn(category, reference)
        self.assertIn('fill="#1e5f7a"', reference)
        self.assertNotIn("Articles:", reference)
        self.assertNotIn("% of categorized articles", reference)


class EditorialAssignmentTests(WebTestCase):
    def setUp(self):
        super().setUp()
        article = make_article(
            title="Editorial assignment story",
            link="https://example.com/editorial/assignment",
            published="2026-04-04T10:00:00Z",
            category="Health",
        )
        self.repo.upsert(article)
        self.article = self.repo.search(query=article.title)[0]
        self.user_id = UserRepository(self.db).create_user("editor", "test-password", ROLE_EDITOR)
        self.editorial = EditorialRepository(self.db)
        self.collection = self.editorial.create_collection("Health desk", "Health stories", self.user_id)
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_assignment_persists_and_appears_after_returning_to_collections(self):
        detail = self.client.get(f"/articles/{self.article.id}").data
        self.assertIn(b'data-collection-assignment', detail)
        self.assertIn(b'name="csrf_token"', detail)
        self.assertIn(b"Health desk", detail)

        response = self.post(
            f"/articles/{self.article.id}/collections",
            {"collection_id": self.collection["id"]},
            follow_redirects=True,
        )

        self.assertIn(b"Article assigned to Health desk", response.data)
        self.assertEqual(len(self.editorial.list_collection_articles(self.collection["id"])), 1)
        self.assertIn(b"Editorial assignment story", self.client.get("/collections").data)
        self.assertEqual(self.editorial.list_audit_logs()[0]["action"], "article_assigned")
        stored = self.repo.get(self.article.id)
        self.assertEqual(stored.url, "https://example.com/editorial/assignment")
        self.assertEqual(stored.category, "Health")
        self.assertEqual(stored.published_at, self.article.published_at)
        self.assertEqual(stored.status, "Under Review")

    def test_editorial_status_confirmation_persists_note_and_audit(self):
        response = self.post(
            f"/articles/{self.article.id}/editorial",
            {"status": "Under Review", "notes": "Check the source details."},
            follow_redirects=True,
        )

        self.assertIn(b"Editorial details saved", response.data)
        self.assertEqual(self.repo.get(self.article.id).status, "Under Review")
        self.assertEqual(self.repo.get(self.article.id).notes, "Check the source details.")
        self.assertEqual(self.editorial.list_notes(self.article.id)[0]["body"], "Check the source details.")
        self.assertEqual(self.editorial.list_audit_logs()[0]["action"], "status_update")

    def test_note_history_failure_is_reported_without_hiding_saved_status(self):
        with patch("src.routes.articles.deps.editorial_service", side_effect=RuntimeError("private db detail")):
            response = self.post(
                f"/articles/{self.article.id}/editorial",
                {"status": "Under Review", "notes": "Keep this note."},
            )

        self.assertEqual(response.status_code, 302)
        page = self.client.get(f"/articles/{self.article.id}").data
        self.assertIn(b"Editorial details were saved, but note history could not be updated", page)
        self.assertNotIn(b"private db detail", page)
        self.assertEqual(self.repo.get(self.article.id).status, "Under Review")
        self.assertEqual(self.repo.get(self.article.id).notes, "Keep this note.")

    def test_ajax_confirmation_returns_saved_assignment(self):
        response = self.post(
            f"/articles/{self.article.id}/collections",
            {"collection_id": self.collection["id"]},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        self.assertTrue(response.json["added"])
        self.assertEqual(response.json["collection_name"], "Health desk")
        self.assertEqual(len(self.editorial.list_collection_articles(self.collection["id"])), 1)

    def test_storage_failure_is_logged_and_returns_retryable_error(self):
        with patch.object(EditorialRepository, "add_article_to_collection", side_effect=RuntimeError("private db detail")):
            response = self.post(
                f"/articles/{self.article.id}/collections",
                {"collection_id": self.collection["id"]},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json["ok"])
        self.assertIn("could not be saved", response.json["message"])
        self.assertNotIn("private db detail", response.data.decode())

    def test_repeated_assignment_does_not_create_duplicates(self):
        url = f"/articles/{self.article.id}/collections"
        data = {"collection_id": self.collection["id"]}

        self.post(url, data)
        response = self.post(url, data, follow_redirects=True)

        self.assertIn(b"already assigned", response.data)
        self.assertEqual(len(self.editorial.list_collection_articles(self.collection["id"])), 1)

    def test_assignment_preserves_existing_editorial_status(self):
        self.repo.update_editorial(self.article.id, "Approved", "Already reviewed")

        self.post(
            f"/articles/{self.article.id}/collections",
            {"collection_id": self.collection["id"]},
        )

        self.assertEqual(self.repo.get(self.article.id).status, "Approved")

    def test_invalid_assignment_targets_are_rejected(self):
        response = self.post(
            f"/articles/{self.article.id}/collections",
            {"collection_id": 9999},
            follow_redirects=True,
        )
        self.assertIn(b"Choose an available editorial section", response.data)
        missing_article = self.post(
            "/articles/9999/collections",
            {"collection_id": self.collection["id"]},
            follow_redirects=True,
        )
        self.assertIn(b"That article was not found", missing_article.data)

    def test_viewers_cannot_assign_articles(self):
        viewer_id = UserRepository(self.db).create_user("viewer", "test-password", ROLE_VIEWER)
        with self.client.session_transaction() as session:
            session["user_id"] = viewer_id

        response = self.post(
            f"/articles/{self.article.id}/collections",
            {"collection_id": self.collection["id"]},
            follow_redirects=True,
        )

        self.assertIn(b"permission to assign articles", response.data)
        self.assertEqual(self.editorial.list_collection_articles(self.collection["id"]), [])

    def test_viewers_cannot_confirm_editorial_status(self):
        viewer_id = UserRepository(self.db).create_user("status-viewer", "test-password", ROLE_VIEWER)
        with self.client.session_transaction() as session:
            session["user_id"] = viewer_id

        response = self.post(
            f"/articles/{self.article.id}/editorial",
            {"status": "Approved", "notes": "not allowed"},
            follow_redirects=True,
        )

        self.assertIn(b"permission to update editorial status", response.data)
        self.assertEqual(self.repo.get(self.article.id).status, "New")
        matching_routes = [
            rule for rule in self.app.url_map.iter_rules()
            if rule.rule == "/articles/<int:article_id>/editorial" and "POST" in rule.methods
        ]
        self.assertEqual(len(matching_routes), 1)


class EditorialStageRouteTests(WebTestCase):
    def setUp(self):
        super().setUp()
        user_id = UserRepository(self.db).create_user("stage-editor", "test-password", ROLE_EDITOR)
        with self.client.session_transaction() as session:
            session["user_id"] = user_id
        for index, status in enumerate(STATUSES[:-1]):
            article = make_article(
                title=f"Article for {status}",
                link=f"https://example.com/stages/{index}",
            )
            self.repo.upsert(article)
            stored = self.repo.search(query=article.title)[0]
            self.repo.update_editorial(stored.id, status, "")

    def test_every_configured_stage_opens_and_filters_its_articles(self):
        for status in STATUSES[:-1]:
            response = self.client.get("/editorial?" + urlencode({"status": status}))
            self.assertEqual(response.status_code, 200, status)
            self.assertIn(f"Article for {status}".encode(), response.data, status)

    def test_review_shorthand_opens_under_review_stage(self):
        response = self.client.get("/editorial?status=Review")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Article for Under Review", response.data)
        self.assertNotIn(b"Article for New", response.data)

    def test_empty_configured_stage_has_an_empty_state(self):
        response = self.client.get("/editorial?status=Selected+for+Content")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No articles currently assigned to this stage.", response.data)

    def test_unknown_stage_returns_controlled_not_found(self):
        response = self.client.get("/editorial?status=not-a-stage")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"Traceback", response.data)

    def test_database_query_failure_returns_safe_service_error(self):
        with patch("src.routes.editorial.deps.articles", side_effect=sqlite3.OperationalError("private query detail")):
            response = self.client.get("/editorial?status=New")

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"Editorial stages are temporarily unavailable", response.data)
        self.assertNotIn(b"private query detail", response.data)


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
