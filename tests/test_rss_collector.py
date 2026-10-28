import unittest
from unittest.mock import Mock

import requests

from src.collectors.rss_collector import CollectorError, fetch_feed, parse_feed
from tests.helpers import ATOM_SAMPLE, MALFORMED_XML, NOT_A_FEED, RSS_SAMPLE


class ParseTests(unittest.TestCase):
    def test_rss(self):
        entries = parse_feed(RSS_SAMPLE)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["link"], "https://Example.com/news/scholarship/?utm_source=rss#top")
        self.assertIsNone(entries[1]["link"])
        self.assertIsNone(entries[2]["published"])

    def test_atom(self):
        entries = parse_feed(ATOM_SAMPLE)
        self.assertEqual([e["link"] for e in entries], ["https://atom.example.org/a1", "https://atom.example.org/a2"])
        self.assertEqual(entries[0]["published"], "2026-03-01T08:30:00Z")
        self.assertEqual(entries[1]["published"], "2026-03-01T09:00:00+00:00")

    def test_malformed_and_non_feed(self):
        with self.assertRaises(CollectorError):
            parse_feed(MALFORMED_XML)
        with self.assertRaises(CollectorError):
            parse_feed(NOT_A_FEED)

    def test_entity_bomb_is_rejected(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss><channel><item><title>&b;</title></item></channel></rss>'
        with self.assertRaises(CollectorError):
            parse_feed(bomb)


class FetchTests(unittest.TestCase):
    def test_fetch_uses_timeout_and_parses(self):
        session = Mock()
        session.get.return_value = Mock(content=ATOM_SAMPLE, raise_for_status=Mock())
        entries = fetch_feed("https://feed.example/atom", timeout=7, session=session)
        self.assertEqual(len(entries), 2)
        self.assertEqual(session.get.call_args.kwargs["timeout"], 7)

    def test_network_and_http_errors_become_collector_errors(self):
        session = Mock()
        session.get.side_effect = requests.ConnectionError("boom")
        with self.assertRaises(CollectorError):
            fetch_feed("https://feed.example/x", session=session)
        bad = Mock(content=b"")
        bad.raise_for_status.side_effect = requests.HTTPError("404")
        session.get.side_effect = None
        session.get.return_value = bad
        with self.assertRaises(CollectorError):
            fetch_feed("https://feed.example/x", session=session)


if __name__ == "__main__":
    unittest.main()
