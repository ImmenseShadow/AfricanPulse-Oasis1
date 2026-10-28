import unittest

from src.processors.article_processor import make_dedupe_key, normalize_url
from tests.test_database import DatabaseTestCase
from tests.helpers import make_article


class KeyTests(unittest.TestCase):
    def test_equivalent_urls_share_a_key(self):
        variants = [
            "https://example.com/a",
            "https://example.com/a/",
            "HTTPS://EXAMPLE.COM/a?utm_campaign=z",
            "https://example.com/a#section",
        ]
        keys = {make_dedupe_key(normalize_url(u)) for u in variants}
        self.assertEqual(len(keys), 1)

    def test_different_urls_differ(self):
        self.assertNotEqual(
            make_dedupe_key(normalize_url("https://example.com/a")),
            make_dedupe_key(normalize_url("https://example.com/b")),
        )


class RepeatedCollectionTests(DatabaseTestCase):
    def test_same_article_saved_repeatedly_is_one_row(self):
        for link in ("https://example.com/x", "https://example.com/x/?utm_source=a", "https://EXAMPLE.com/x#c"):
            self.repo.upsert(make_article(link=link))
        self.assertEqual(self.repo.count(), 1)


if __name__ == "__main__":
    unittest.main()
