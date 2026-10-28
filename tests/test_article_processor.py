import unittest

from config.settings import MAX_SUMMARY_CHARS
from src.processors.article_processor import (
    InvalidArticleError, clean_text, normalize_url, parse_date,
    process_entries, process_entry, truncate,
)
from tests.helpers import FIXED_TIME


class CleanTextTests(unittest.TestCase):
    def test_strips_tags_entities_and_whitespace(self):
        self.assertEqual(clean_text("<p>Hello &amp;\n  world</p>"), "Hello & world")

    def test_none_and_empty(self):
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text("   "), "")

    def test_truncate_keeps_short_text_and_shortens_long_text(self):
        self.assertEqual(truncate("short"), "short")
        long_text = "word " * 400
        self.assertLessEqual(len(truncate(long_text)), MAX_SUMMARY_CHARS + 3)
        self.assertTrue(truncate(long_text).endswith("..."))


class UrlAndDateTests(unittest.TestCase):
    def test_normalize_url(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.com/a/b/?utm_source=x&id=7#frag"),
            "https://example.com/a/b?id=7",
        )

    def test_rejects_non_web_urls(self):
        for bad in (None, "", "javascript:alert(1)", "ftp://x.org/a", "/relative"):
            self.assertIsNone(normalize_url(bad), bad)

    def test_parse_date_rfc822_converts_to_utc(self):
        self.assertEqual(parse_date("Mon, 02 Mar 2026 12:00:00 +0200"), "2026-03-02T10:00:00+00:00")

    def test_parse_date_iso_and_invalid(self):
        self.assertEqual(parse_date("2026-03-01T08:30:00Z"), "2026-03-01T08:30:00+00:00")
        self.assertIsNone(parse_date("yesterday-ish"))
        self.assertIsNone(parse_date(None))


class ProcessEntryTests(unittest.TestCase):
    def test_valid_entry(self):
        a = process_entry(
            {"title": " Big  news ", "link": "https://x.org/1", "published": "2026-03-01T08:30:00Z",
             "summary": "<b>Text</b>"},
            "Src", FIXED_TIME,
        )
        self.assertEqual(a.title, "Big news")
        self.assertEqual(a.summary, "Text")
        self.assertEqual(a.source, "Src")
        self.assertEqual(a.status, "New")
        self.assertEqual(a.collected_at, "2026-03-02T12:00:00+00:00")

    def test_missing_fields_are_not_invented(self):
        a = process_entry({"title": "T", "link": "https://x.org/1"}, "Src", FIXED_TIME)
        self.assertIsNone(a.summary)
        self.assertIsNone(a.published_at)

    def test_missing_title_or_link_rejected(self):
        with self.assertRaises(InvalidArticleError):
            process_entry({"title": "", "link": "https://x.org/1"}, "Src")
        with self.assertRaises(InvalidArticleError):
            process_entry({"title": "T", "link": None}, "Src")
        with self.assertRaises(InvalidArticleError):
            process_entry({"title": "T", "link": "not a url"}, "Src")

    def test_process_entries_reports_skips(self):
        raws = [
            {"title": "A", "link": "https://x.org/1"},
            {"title": "No link"},
            {"title": "A again", "link": "https://x.org/1/?utm_medium=y"},
        ]
        articles, skipped = process_entries(raws, "Src", FIXED_TIME)
        self.assertEqual(len(articles), 1)
        self.assertEqual(len(skipped), 2)


if __name__ == "__main__":
    unittest.main()
