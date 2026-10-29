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

ALERT_TOKEN = "SECRETTOKEN123"
ALERT_URL = f"https://www.google.com/alerts/feeds/{ALERT_TOKEN}/987654321"

# Shaped like a real Google Alerts Atom feed: redirect links, HTML titles, publisher inside the content.
GOOGLE_ALERT_SAMPLE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><id>tag:google.com,2005:reader/user/1/state/com.google/alert/1</id>
<title>Google Alert - African education</title><updated>2026-03-02T10:00:00Z</updated>
<entry>
  <id>tag:google.com,2013:googlealerts/feed:1</id>
  <title type="html">&lt;b&gt;African&lt;/b&gt; universities expand &lt;b&gt;scholarships&lt;/b&gt;</title>
  <link href="https://www.google.com/url?rct=j&amp;sa=t&amp;url=https://news.example.org/edu/scholarships%3Futm_source%3Dga&amp;ct=ga&amp;cd=CAEY&amp;usg=AOvVaw1"/>
  <published>2026-03-02T08:00:00Z</published><updated>2026-03-02T08:00:00Z</updated>
  <content type="html">&lt;div&gt;&lt;a href="https://www.google.com/url?x=1"&gt;African universities&lt;/a&gt;&lt;/div&gt;&lt;div&gt;&lt;font size="-1"&gt;&lt;font color="#6f6f6f"&gt;Example Daily&lt;/font&gt;&lt;/font&gt;&lt;/div&gt;&lt;div&gt;&lt;font size="-1"&gt;Universities across the continent announce new &lt;b&gt;scholarship&lt;/b&gt; funds.&lt;/font&gt;&lt;/div&gt;</content>
</entry>
<entry>
  <id>tag:google.com,2013:googlealerts/feed:2</id>
  <title type="html">Direct link entry without a publisher or date</title>
  <link href="https://www.other.example/story/42"/>
</entry>
<entry>
  <id>tag:google.com,2013:googlealerts/feed:3</id>
  <title type="html">Entry without any link</title>
</entry>
<entry>
  <id>tag:google.com,2013:googlealerts/feed:4</id>
  <title type="html">Rainfall data released (found by alert)</title>
  <link href="https://www.google.com/url?sa=t&amp;url=https%3A%2F%2Fexample.com%2Fnews%2Frainfall%2F&amp;ct=ga"/>
  <published>2026-03-02T09:00:00Z</published>
  <content type="html">&lt;div&gt;&lt;font color="#6f6f6f"&gt;Met Service&lt;/font&gt;&lt;/div&gt;&lt;div&gt;Alert snippet about rainfall.&lt;/div&gt;</content>
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
