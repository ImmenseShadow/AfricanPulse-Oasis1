"""Increment 2: Google Alerts RSS integration. Everything runs on local fixtures and mocks."""
import ipaddress
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import requests

from config.settings import FeedSource
from src.collectors.rss_collector import CollectorError, fetch_feed, parse_feed
from src.processors.article_processor import process_entries, process_entry, unwrap_google_redirect
from src.services.news_service import NewsService
from src.services.source_service import SourceService, ValidationError, validate_feed_url
from src.storage.collection_repository import CollectionRepository
from src.storage.source_repository import SourceRepository
from src.url_safety import UnsafeDestinationError, check_destination, mask_url
from tests.helpers import (
    ALERT_TOKEN, ALERT_URL, ATOM_SAMPLE, FIXED_TIME, GOOGLE_ALERT_SAMPLE, MALFORMED_XML, RSS_SAMPLE,
)
from tests.test_database import DatabaseTestCase
from tests.test_routes import WebTestCase

ALERT_TOPIC = "African education"
GA = "google_alert"


def fake_dns(host, port):
    """Stand-in resolver: IP literals resolve to themselves, rebind.example to a private address."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        return ["10.0.0.5"] if host == "rebind.example" else ["93.184.216.34"]


def response(status=200, content=b"", headers=None):
    res = Mock(content=content, status_code=status, headers=headers or {})
    res.raise_for_status = Mock()
    return res


class AlertEntryProcessingTests(unittest.TestCase):
    def setUp(self):
        self.raw = parse_feed(GOOGLE_ALERT_SAMPLE)

    def process(self, index):
        return process_entry(self.raw[index], "Alert: African education", FIXED_TIME, GA, ALERT_TOPIC)

    def test_feed_has_the_expected_entries(self):
        self.assertEqual(len(self.raw), 4)

    def test_redirect_link_is_unwrapped_and_metadata_extracted(self):
        article = self.process(0)
        self.assertEqual(article.url, "https://news.example.org/edu/scholarships")
        self.assertEqual(article.title, "African universities expand scholarships")
        self.assertEqual(article.publisher, "Example Daily")
        self.assertEqual(article.summary, "Universities across the continent announce new scholarship funds.")
        self.assertEqual(article.alert_topic, ALERT_TOPIC)
        self.assertEqual(article.published_at, "2026-03-02T08:00:00+00:00")
        self.assertEqual(article.collected_at, FIXED_TIME.isoformat(timespec="seconds"))

    def test_missing_fields_are_not_fabricated(self):
        article = self.process(1)
        self.assertEqual(article.url, "https://www.other.example/story/42")
        self.assertEqual(article.publisher, "other.example")  # taken from the link, never "Google"
        self.assertIsNone(article.published_at)
        self.assertIsNone(article.summary)

    def test_entry_without_link_is_skipped_not_stored(self):
        articles, skipped = process_entries(self.raw, "Alert", FIXED_TIME, GA, ALERT_TOPIC)
        self.assertEqual(len(articles), 3)
        self.assertEqual(skipped, ["missing or invalid link"])

    def test_google_is_never_assumed_to_be_the_publisher(self):
        article = process_entry({"title": "T", "link": "https://www.google.com/url?sa=t&ct=ga"}, "A", FIXED_TIME, GA, "x")
        self.assertIsNone(article.publisher)
        self.assertIn("google.com/url", article.url)  # no usable target, so the original link is kept

    def test_unwrap_only_returns_web_addresses(self):
        for target in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,hi"):
            link = f"https://www.google.com/url?sa=t&url={target}"
            self.assertEqual(unwrap_google_redirect(link), link)
        self.assertEqual(unwrap_google_redirect("https://www.google.co.uk/url?q=https://a.example/x&sa=U"), "https://a.example/x")
        self.assertEqual(unwrap_google_redirect("https://a.example/url?url=https://b.example/"), "https://a.example/url?url=https://b.example/")

    def test_plain_rss_entries_are_not_unwrapped(self):
        raw = {"title": "T", "link": "https://www.google.com/url?url=https://a.example/x"}
        self.assertTrue(process_entry(raw, "RSS", FIXED_TIME).url.startswith("https://www.google.com/url"))


class UrlSafetyTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("src.url_safety.resolve_ips", side_effect=fake_dns)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_public_destination_is_allowed(self):
        check_destination("https://news.example/feed")

    def test_unsafe_destinations_are_rejected(self):
        for bad in ("http://127.0.0.1/x", "http://localhost/x", "http://169.254.169.254/latest/meta-data/",
                    "http://metadata.google.internal/computeMetadata/v1/", "http://10.1.2.3/x",
                    "http://192.168.0.9/x", "http://[::1]/x", "http://rebind.example/feed",
                    "ftp://news.example/x", "file:///etc/passwd", "javascript:alert(1)"):
            with self.assertRaises(UnsafeDestinationError, msg=bad):
                check_destination(bad)

    def test_private_destinations_can_be_enabled_explicitly(self):
        check_destination("http://127.0.0.1:8000/feed", allow_private=True)

    def test_malformed_urls_are_rejected_safely(self):
        for bad in (
            "https://example.com:99999/feed",
            "https://user:pass@example.com/feed",
            "https://example.com:0/feed",
        ):
            with self.assertRaises(UnsafeDestinationError, msg=bad):
                check_destination(bad)

    def test_unresolvable_host_is_rejected(self):
        with patch("src.url_safety.resolve_ips", side_effect=OSError("nope")):
            with self.assertRaises(UnsafeDestinationError):
                check_destination("https://missing.example/x")

    def test_mask_url_hides_feed_tokens(self):
        masked = mask_url(ALERT_URL)
        self.assertNotIn(ALERT_TOKEN, masked)
        self.assertEqual(masked, "https://www.google.com/alerts/feeds/…")
        self.assertNotIn("secret", mask_url("https://x.example/feed?token=secret"))


class SafeFetchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("src.url_safety.resolve_ips", side_effect=fake_dns)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.session = Mock()

    def fetch(self, url=ALERT_URL):
        return fetch_feed(url, timeout=5, session=self.session)

    def test_valid_google_alert_feed_is_parsed(self):
        self.session.get.return_value = response(content=GOOGLE_ALERT_SAMPLE)
        self.assertEqual(len(self.fetch()), 4)
        kwargs = self.session.get.call_args.kwargs
        self.assertEqual((kwargs["timeout"], kwargs["allow_redirects"]), (5, False))

    def test_host_resolving_to_a_private_address_is_never_requested(self):
        with self.assertRaises(CollectorError) as ctx:
            self.fetch("https://rebind.example/feed")
        self.session.get.assert_not_called()
        self.assertIn("private", str(ctx.exception))

    def test_redirect_to_metadata_endpoint_is_blocked(self):
        self.session.get.return_value = response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        with self.assertRaises(CollectorError):
            self.fetch()
        self.assertEqual(self.session.get.call_count, 1)

    def test_redirect_to_unsupported_scheme_is_blocked(self):
        self.session.get.return_value = response(301, headers={"Location": "file:///etc/passwd"})
        with self.assertRaises(CollectorError):
            self.fetch()

    def test_safe_redirects_are_followed_and_revalidated(self):
        self.session.get.side_effect = [
            response(302, headers={"Location": "/alerts/moved"}),
            response(200, content=ATOM_SAMPLE),
        ]
        self.assertEqual(len(self.fetch()), 2)
        self.assertEqual(self.session.get.call_args_list[1].args[0], "https://www.google.com/alerts/moved")

    def test_redirect_loops_are_cut_off(self):
        self.session.get.return_value = response(302, headers={"Location": "https://news.example/again"})
        with self.assertRaises(CollectorError) as ctx:
            self.fetch()
        self.assertIn("too many redirects", str(ctx.exception))

    def test_unavailable_feeds_give_clear_errors_without_the_token(self):
        cases = [
            (requests.Timeout(ALERT_URL), "timed out"),
            (requests.ConnectionError(ALERT_URL), "unable to connect"),
            (requests.RequestException(ALERT_URL), "request failed"),
        ]
        for exc, text in cases:
            self.session.get.side_effect = exc
            with self.assertRaises(CollectorError) as ctx:
                self.fetch()
            self.assertIn(text, str(ctx.exception))
            self.assertNotIn(ALERT_TOKEN, str(ctx.exception))
        bad = response(503)
        bad.raise_for_status.side_effect = requests.HTTPError("503", response=Mock(status_code=503))
        self.session.get.side_effect = None
        self.session.get.return_value = bad
        with self.assertRaises(CollectorError) as ctx:
            self.fetch()
        self.assertIn("HTTP 503", str(ctx.exception))

    def test_malformed_and_non_feed_responses_are_rejected(self):
        for body in (MALFORMED_XML, b"<html><body>Sign in</body></html>", b""):
            self.session.get.return_value = response(content=body)
            with self.assertRaises(CollectorError, msg=body):
                self.fetch()


class AlertSourceServiceTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.repo_sources = SourceRepository(self.db)
        self.calls = []

        def fetch(url, timeout=15):
            self.calls.append(url)
            return parse_feed(GOOGLE_ALERT_SAMPLE if "alerts" in url else MALFORMED_XML)

        self.service = SourceService(self.repo_sources, fetch=fetch)

    def test_register_google_alert_source(self):
        sid = self.service.add("Alert: education", ALERT_URL, GA, "  African   education ")
        row = self.repo_sources.get(sid)
        self.assertEqual((row["source_type"], row["alert_topic"], row["enabled"]), (GA, "African education", 1))
        self.assertEqual(row["feed_url"], ALERT_URL)

    def test_topic_required_and_type_validated(self):
        with self.assertRaises(ValidationError):
            self.service.add("A", ALERT_URL, GA, "   ")
        with self.assertRaises(ValidationError):
            self.service.add("A", ALERT_URL, GA, "x" * 121)
        with self.assertRaises(ValidationError):
            self.service.add("A", ALERT_URL, "twitter", "topic")
        self.assertEqual(self.repo_sources.count(), 0)

    def test_plain_feeds_default_to_rss_and_ignore_topic(self):
        sid = self.service.add("Plain", "https://plain.example/rss", alert_topic="ignored")
        row = self.repo_sources.get(sid)
        self.assertEqual((row["source_type"], row["alert_topic"]), ("rss", None))

    def test_edit_enable_disable_remove(self):
        sid = self.service.add("Alert: education", ALERT_URL, GA, "education")
        self.service.update(sid, "Alert: schools", ALERT_URL, GA, "schools")
        row = self.repo_sources.get(sid)
        self.assertEqual((row["name"], row["alert_topic"]), ("Alert: schools", "schools"))
        self.service.update(sid, "Alert: schools", ALERT_URL)  # type and topic untouched
        self.assertEqual(self.repo_sources.get(sid)["alert_topic"], "schools")
        with self.assertRaises(ValidationError):
            self.service.update(sid, "Alert: schools", ALERT_URL, GA, "")
        self.service.set_enabled(sid, False)
        self.assertEqual(self.repo_sources.get(sid)["enabled"], 0)
        self.service.delete(sid)
        self.assertIsNone(self.repo_sources.get(sid))

    def test_unsafe_urls_are_rejected_before_any_request(self):
        for bad in ("http://169.254.169.254/latest/meta-data/", "http://localhost:5000/feed",
                    "http://metadata.google.internal/x", "http://192.168.1.1/x", "file:///etc/passwd",
                    "javascript:alert(1)", "ftp://x.example/feed", "not a url"):
            with self.assertRaises(ValidationError, msg=bad):
                self.service.add("Bad", bad, GA, "topic")
            with self.assertRaises(ValidationError, msg=bad):
                self.service.test(bad)
        self.assertEqual(self.calls, [])
        self.assertEqual(validate_feed_url(ALERT_URL), ALERT_URL)

    def test_feed_test_needs_a_real_parseable_response(self):
        self.assertEqual(self.service.test(ALERT_URL), 4)
        self.assertEqual(self.calls, [ALERT_URL])
        with self.assertRaises(ValidationError) as ctx:
            self.service.test("https://plain.example/not-a-feed")
        self.assertIn("not valid XML", str(ctx.exception))


class AlertCollectionTests(DatabaseTestCase):
    FEEDS = {
        "https://a.example/rss": RSS_SAMPLE,
        ALERT_URL: GOOGLE_ALERT_SAMPLE,
    }

    def setUp(self):
        super().setUp()
        self.fetches = []
        self.service = NewsService(self.db, fetch=self.fetch, now=lambda: FIXED_TIME)
        self.rss = FeedSource("Feed A", "https://a.example/rss")
        self.alert = FeedSource("Alert: education", ALERT_URL, True, GA, ALERT_TOPIC)
        self.rss_id = self.service.sources.add(self.rss.name, self.rss.feed_url, "2026-01-01T00:00:00+00:00")
        self.alert_id = self.service.sources.add(
            self.alert.name, self.alert.feed_url, "2026-01-01T00:00:00+00:00", True, GA, ALERT_TOPIC)
        self.rss = FeedSource(self.rss.name, self.rss.feed_url, True, "rss", None, self.rss_id)
        self.alert = FeedSource(self.alert.name, self.alert.feed_url, True, GA, ALERT_TOPIC, self.alert_id)

    def fetch(self, url):
        self.fetches.append(url)
        if url == "https://down.example/alert":
            raise CollectorError("Could not fetch feed: the server answered HTTP 503.")
        if url == "https://boom.example/alert":
            raise RuntimeError(f"unexpected failure for {ALERT_URL}")
        return parse_feed(self.FEEDS[url])

    def test_alert_entries_are_saved_through_the_existing_pipeline(self):
        result = self.service.collect([self.alert])[0]
        self.assertEqual((result.fetched, result.inserted, result.updated, result.invalid), (4, 3, 0, 1))
        stored = {a.url: a for a in self.repo.search()}
        self.assertEqual(set(stored), {"https://news.example.org/edu/scholarships",
                                       "https://www.other.example/story/42", "https://example.com/news/rainfall"})
        article = stored["https://news.example.org/edu/scholarships"]
        self.assertEqual((article.source, article.publisher, article.alert_topic),
                         ("Alert: education", "Example Daily", ALERT_TOPIC))
        self.assertEqual(article.category, "Education")

    def test_article_already_collected_from_rss_keeps_its_record(self):
        self.service.collect([self.rss])
        before = self.repo.search(query="Rainfall data released")[0]
        self.assertEqual(self.repo.count(), 2)
        result = self.service.collect([self.alert])[0]
        self.assertEqual((result.inserted, result.updated), (2, 1))
        self.assertEqual(self.repo.count(), 4)  # rainfall was not duplicated
        after = self.repo.get(before.id)
        self.assertEqual((after.title, after.summary, after.source, after.collected_at),
                         (before.title, before.summary, "Feed A", before.collected_at))
        refs = self.repo.sources_for(before.id)
        self.assertEqual([(r["source_name"], r["source_type"]) for r in refs],
                         [("Feed A", "rss"), ("Alert: education", GA)])
        self.assertEqual(refs[1]["alert_topic"], ALERT_TOPIC)
        self.assertEqual(refs[1]["source_id"], self.alert_id)

    def test_editorial_work_survives_alert_rediscovery(self):
        self.service.collect([self.rss])
        article = self.repo.search(query="Rainfall data released")[0]
        self.repo.update_editorial(article.id, "Selected for Content", "keep")
        self.service.collect([self.alert])
        kept = self.repo.get(article.id)
        self.assertEqual((kept.status, kept.notes), ("Selected for Content", "keep"))

    def test_alert_first_then_rss_still_creates_one_record(self):
        self.service.collect([self.alert])
        self.service.collect([self.rss])
        self.assertEqual(self.repo.count(), 4)
        rainfall = self.repo.search(query="Rainfall data released")[0]
        self.assertEqual(len(self.repo.sources_for(rainfall.id)), 2)

    def test_repeated_collection_creates_no_duplicates(self):
        self.service.collect([self.rss, self.alert])
        first = self.repo.count()
        second = self.service.collect([self.rss, self.alert])
        self.assertEqual(self.repo.count(), first)
        self.assertEqual(sum(r.inserted for r in second), 0)
        for article in self.repo.search(limit=50):
            names = [r["source_name"] for r in self.repo.sources_for(article.id)]
            self.assertEqual(len(names), len(set(names)))

    def test_distinct_articles_with_similar_titles_are_not_merged(self):
        feed = (b'<rss><channel><item><title>Rainfall data released</title>'
                b'<link>https://different.example/rainfall</link></item></channel></rss>')
        self.FEEDS = {**self.FEEDS, "https://similar.example/rss": feed}
        self.service.collect([self.rss, FeedSource("Similar", "https://similar.example/rss")])
        self.assertEqual(len(self.repo.search(query="Rainfall data released")), 2)

    def test_collection_activity_is_recorded_for_the_alert(self):
        self.service.collect([self.rss, self.alert])
        run = self.service.runs.recent_runs()[0]
        self.assertEqual(run["status"], "completed")
        by_name = {s["source_name"]: s for s in run["sources"]}
        alert = by_name["Alert: education"]
        self.assertEqual((alert["source_id"], alert["source_type"], alert["ok"]), (self.alert_id, GA, 1))
        self.assertEqual((alert["fetched"], alert["inserted"], alert["duplicates"], alert["invalid"]), (4, 2, 1, 1))
        stamp = FIXED_TIME.isoformat(timespec="seconds")
        self.assertEqual((alert["started_at"], alert["finished_at"]), (stamp, stamp))
        health = self.service.sources.get(self.alert_id)
        self.assertEqual((health["last_status"], health["last_error"]), ("ok", None))

    def test_failed_alert_is_recorded_safely_and_others_still_run(self):
        down = FeedSource("Alert: down", "https://down.example/alert", True, GA, "topic", None)
        boom = FeedSource("Alert: boom", "https://boom.example/alert", True, GA, "topic", None)
        with self.assertLogs("src.services.news_service", level="ERROR") as logs:
            results = {r.source_name: r for r in self.service.collect([down, boom, self.rss, self.alert])}
        self.assertFalse(results["Alert: down"].ok)
        self.assertIn("HTTP 503", results["Alert: down"].error)
        self.assertFalse(results["Alert: boom"].ok)
        self.assertTrue(results["Feed A"].ok and results["Alert: education"].ok)
        self.assertEqual(self.repo.count(), 4)  # 2 from the feed plus 2 new from the alert, rainfall shared
        self.assertNotIn(ALERT_TOKEN, "\n".join(logs.output))
        run = self.service.runs.recent_runs()[0]
        self.assertEqual((run["status"], run["sources_failed"]), ("completed_with_errors", 2))
        blob = str(run) + str([s["last_error"] for s in self.service.sources.list_sources()])
        self.assertNotIn(ALERT_TOKEN, blob)
        self.assertEqual(self.fetches.count("https://a.example/rss"), 1)

    def test_all_alerts_failing_marks_the_run_failed(self):
        self.service.collect([FeedSource("Alert: down", "https://down.example/alert", True, GA, "t")])
        self.assertEqual(self.service.runs.recent_runs()[0]["status"], "failed")

    def test_disabled_alert_is_skipped(self):
        off = FeedSource("Alert: off", ALERT_URL, False, GA, "t")
        self.assertEqual(self.service.collect([off, self.rss])[0].source_name, "Feed A")
        self.assertNotIn(ALERT_URL, self.fetches)


def alert_fetch(url, timeout=15):
    feeds = {ALERT_URL: GOOGLE_ALERT_SAMPLE, "https://a.example/rss": RSS_SAMPLE}
    if url in feeds:
        return parse_feed(feeds[url])
    raise CollectorError("Could not fetch feed: the server answered HTTP 404.")


BAD_ALERT_URL = "https://www.google.com/alerts/feeds/BADTOKEN999/1"


class AlertWebTests(WebTestCase):
    fetch_feed = staticmethod(alert_fetch)

    def add_alert(self, name="Alert: education", url=ALERT_URL, topic=ALERT_TOPIC):
        return self.post("/sources", {"name": name, "url": url, "source_type": GA, "alert_topic": topic},
                         follow_redirects=True)

    def test_register_and_view_a_google_alert_source(self):
        res = self.add_alert()
        self.assertIn(b"Source added", res.data)
        self.assertIn(b"Google Alerts feed", res.data)
        self.assertIn(b"Topic: African education", res.data)
        self.assertIn(b"https://www.google.com/alerts/feeds/", res.data)
        self.assertNotIn(ALERT_TOKEN.encode(), res.data)  # the token is masked in the list
        self.assertIn(b'name="alert_topic"', res.data)
        row = SourceRepository(self.db).list_sources()[0]
        self.assertEqual((row["source_type"], row["alert_topic"]), (GA, ALERT_TOPIC))

    def test_validation_errors_are_shown(self):
        res = self.post("/sources", {"name": "A", "url": ALERT_URL, "source_type": GA, "alert_topic": ""})
        self.assertEqual(res.status_code, 400)
        self.assertIn(b"alert topic", res.data)
        res = self.post("/sources", {"name": "A", "url": "http://169.254.169.254/latest", "source_type": GA,
                                     "alert_topic": "t"})
        self.assertEqual(res.status_code, 400)
        self.assertIn(b"private network", res.data)
        res = self.post("/sources", {"name": "A", "url": ALERT_URL, "source_type": "bogus", "alert_topic": "t"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(SourceRepository(self.db).count(), 0)

    def test_feed_tests_report_real_results(self):
        res = self.post("/sources/test", {"name": "N", "url": ALERT_URL, "source_type": GA, "alert_topic": "t"})
        self.assertIn(b"4 entries found", res.data)
        res = self.post("/sources/test", {"url": BAD_ALERT_URL, "source_type": GA, "alert_topic": "t"})
        self.assertIn(b"Feed test failed", res.data)
        self.add_alert("Bad alert", BAD_ALERT_URL)
        sid = [s for s in SourceRepository(self.db).list_sources() if s["name"] == "Bad alert"][0]["id"]
        res = self.post(f"/sources/{sid}/test", follow_redirects=True)
        self.assertIn(b"test failed", res.data)
        self.assertIn(b"HTTP 404", res.data)
        self.assertNotIn(b"BADTOKEN999", res.data)

    def test_edit_toggle_and_remove(self):
        self.add_alert()
        sid = SourceRepository(self.db).list_sources()[0]["id"]
        page = self.client.get(f"/sources/{sid}/edit").data
        self.assertIn(b"African education", page)
        res = self.post(f"/sources/{sid}/edit", {"name": "Alert: schools", "url": ALERT_URL,
                                                 "source_type": GA, "alert_topic": "schools"}, follow_redirects=True)
        self.assertIn(b"Topic: schools", res.data)
        res = self.post(f"/sources/{sid}/edit", {"name": "Alert: schools", "url": ALERT_URL,
                                                 "source_type": GA, "alert_topic": ""})
        self.assertEqual(res.status_code, 400)
        self.assertIn(b"Source disabled", self.post(f"/sources/{sid}/toggle", {"enabled": "0"}, follow_redirects=True).data)
        self.assertIn(b"No sources configured", self.post(f"/sources/{sid}/delete", follow_redirects=True).data)

    def test_collect_view_and_deduplicate_end_to_end(self):
        self.add_source("Feed A", "https://a.example/rss")
        self.add_alert()
        res = self.post("/collect", follow_redirects=True)
        self.assertIn(b"Completed", res.data)
        self.assertIn(b"Google Alert", res.data)  # activity page marks the alert source
        self.assertEqual(self.repo.count(), 4)  # 2 from RSS + 2 new from the alert, rainfall shared
        articles = self.client.get("/articles").data
        self.assertIn(b"African universities expand scholarships", articles)
        self.assertIn(b"Alert: African education", articles)
        self.assertIn(b"Example Daily", articles)
        self.assertIn(b"https://news.example.org/edu/scholarships", articles)
        self.assertNotIn(b"google.com/url", articles)
        rainfall = self.repo.search(query="Rainfall data released")[0]
        detail = self.client.get(f"/articles/{rainfall.id}").data
        self.assertIn(b"Found by", detail)
        self.assertIn(b"Feed A", detail)
        self.assertIn(b"Alert: education", detail)
        self.post("/collect")
        self.assertEqual(self.repo.count(), 4)
        runs = CollectionRepository(self.db).recent_runs()
        self.assertEqual((len(runs), runs[0]["new_articles"]), (2, 0))

    def test_alert_without_a_publisher_is_labelled_honestly(self):
        self.add_alert()
        self.post("/collect")
        item = self.repo.search(query="Entry without any link")  # dropped: no link
        self.assertEqual(item, [])
        direct = self.repo.search(query="Direct link entry")[0]
        self.assertEqual(direct.publisher, "other.example")

    def test_failed_alert_does_not_stop_other_sources_and_hides_the_token(self):
        self.add_source("Feed A", "https://a.example/rss")
        self.add_alert("Bad alert", BAD_ALERT_URL)
        res = self.post("/collect", follow_redirects=True)
        self.assertIn(b"Completed with errors", res.data)
        self.assertIn(b"HTTP 404", res.data)
        self.assertNotIn(b"BADTOKEN999", res.data)
        self.assertNotIn(b"BADTOKEN999", self.client.get("/sources").data)
        self.assertEqual(self.repo.count(), 2)
        row = [s for s in SourceRepository(self.db).list_sources() if s["name"] == "Bad alert"][0]
        self.assertEqual(row["last_status"], "error")

    def test_existing_rss_sources_still_work_unchanged(self):
        res = self.add_source("Feed A", "https://a.example/rss")
        self.assertIn(b"https://a.example/rss", res.data)  # plain feeds still show their full URL
        self.assertIn(b"RSS / Atom feed", res.data)
        self.post("/collect")
        self.assertEqual(self.repo.count(), 2)


if __name__ == "__main__":
    unittest.main()
