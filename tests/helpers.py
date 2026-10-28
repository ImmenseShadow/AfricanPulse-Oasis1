"""Shared fixtures: sample feeds and a small article factory."""
from datetime import datetime, timezone

from src.processors.article_processor import process_entry

FIXED_TIME = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Sample</title>
<item>
  <title>  Ghana universities launch   scholarship for students </title>
  <link>https://Example.com/news/scholarship/?utm_source=rss#top</link>
  <pubDate>Mon, 02 Mar 2026 12:00:00 +0200</pubDate>
  <description>&lt;p&gt;Applications &amp;amp; details open now.&lt;/p&gt;</description>
</item>
<item>
  <title>Item without a link</title>
  <description>Cannot be stored.</description>
</item>
<item>
  <title>Rainfall data released</title>
  <link>https://example.com/news/rainfall</link>
</item>
</channel></rss>"""

ATOM_SAMPLE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom sample</title>
<entry>
  <title>Fintech startup raises funds</title>
  <link rel="alternate" href="https://atom.example.org/a1"/>
  <published>2026-03-01T08:30:00Z</published>
  <summary>New mobile app for payments.</summary>
</entry>
<entry>
  <title>Second entry</title>
  <link href="https://atom.example.org/a2"/>
  <updated>2026-03-01T09:00:00+00:00</updated>
</entry>
</feed>"""

MALFORMED_XML = b"<rss><channel><item><title>Broken"
NOT_A_FEED = b"<html><body>Hello</body></html>"


def make_article(**overrides):
    raw = {
        "title": "Health ministry confirms cholera outbreak",
        "link": "https://example.com/news/cholera",
        "published": "2026-03-01T10:00:00Z",
        "summary": "Hospitals are treating patients.",
    }
    raw.update(overrides)
    return process_entry(raw, "Example News", FIXED_TIME)
