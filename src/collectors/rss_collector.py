"""Fetch and parse RSS 2.0, RSS 1.0 and Atom feeds.

Only the public feed URL is requested; article pages are never scraped.
"""
from __future__ import annotations

from typing import Optional
from xml.etree.ElementTree import Element, ParseError

import requests
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from config.settings import MAX_FEED_BYTES, REQUEST_TIMEOUT_SECONDS, USER_AGENT

_FEED_ROOTS = {"rss", "feed", "RDF"}


class CollectorError(Exception):
    """A feed could not be fetched or understood."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _first(fields: dict, *names: str) -> Optional[str]:
    for name in names:
        if fields.get(name):
            return fields[name]
    return None


def _entry_to_dict(entry: Element) -> dict:
    fields: dict[str, str] = {}
    link: Optional[str] = None
    for child in entry:
        name = _local(child.tag)
        if name == "link":
            href = child.get("href")
            if href:  # Atom style
                if child.get("rel", "alternate") == "alternate" and link is None:
                    link = href.strip()
            elif child.text and link is None:  # RSS style
                link = child.text.strip()
        elif name not in fields:
            fields[name] = (child.text or "").strip()
    guid = fields.get("guid") or fields.get("id") or ""
    if not link and guid.lower().startswith(("http://", "https://")):
        link = guid
    return {
        "title": fields.get("title"),
        "link": link,
        "published": _first(fields, "pubDate", "published", "date", "updated"),
        "summary": _first(fields, "description", "summary", "content", "encoded"),
    }


def parse_feed(content: bytes) -> list[dict]:
    """Parse feed bytes into raw entry dicts (title, link, published, summary)."""
    try:
        root = SafeET.fromstring(content)
    except (ParseError, DefusedXmlException) as exc:
        raise CollectorError(f"Feed is not valid XML: {exc}")
    if _local(root.tag) not in _FEED_ROOTS:
        raise CollectorError("Response is not an RSS or Atom feed.")
    return [
        _entry_to_dict(el) for el in root.iter() if _local(el.tag) in ("item", "entry")
    ]


def fetch_feed(
    url: str,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Download and parse one feed. Raises CollectorError on any failure."""
    client = session or requests
    try:
        response = client.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
        )
        response.raise_for_status()
    except requests.Timeout:
        raise CollectorError("Could not fetch feed: the request timed out.")
    except requests.ConnectionError:
        raise CollectorError("Could not fetch feed: unable to connect to the server.")
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "error"
        raise CollectorError(f"Could not fetch feed: the server answered HTTP {code}.")
    except requests.RequestException as exc:
        # Exception text can contain the full URL (and any token in it), so omit it.
        raise CollectorError(f"Could not fetch feed: request failed ({type(exc).__name__}).")
    if len(response.content) > MAX_FEED_BYTES:
        raise CollectorError("Feed is larger than the allowed size.")
    return parse_feed(response.content)
