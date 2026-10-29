"""Normalise raw feed entries into validated Article objects."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config.settings import MAX_SUMMARY_CHARS
from src.models.article import SOURCE_GOOGLE_ALERT, SOURCE_RSS, Article
from src.processors.categorizer import categorize

_TAG_RE = re.compile(r"<[^>]+>")
_GOOGLE_HOST_RE = re.compile(r"(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$")
_ALERT_PUBLISHER_RE = re.compile(r'<font[^>]*color=["\']?#6f6f6f["\']?[^>]*>(.*?)</font>', re.I | re.S)
_ALERT_LINK_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.I | re.S)
MAX_PUBLISHER_CHARS = 120
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}


class InvalidArticleError(ValueError):
    """Raised when a feed entry lacks a required field."""


def clean_text(value: Optional[str]) -> str:
    """Strip HTML tags and entities, then collapse whitespace."""
    if not value:
        return ""
    return " ".join(html.unescape(_TAG_RE.sub(" ", value)).split())


def truncate(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip() + "..."


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Canonical form used for duplicate detection. None if not a web URL."""
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def is_google_host(host: Optional[str]) -> bool:
    return bool(host) and bool(_GOOGLE_HOST_RE.search(host.lower().rstrip(".")))


def unwrap_google_redirect(url: Optional[str]) -> Optional[str]:
    """Google Alerts links look like https://www.google.com/url?...&url=<article>&... Return the
    article address from the query string. Nothing is requested: the link is only parsed. When no
    usable web address is found the original link is kept."""
    parts = urlsplit((url or "").strip())
    if not is_google_host(parts.hostname) or parts.path.rstrip("/") != "/url":
        return url
    params = dict(parse_qsl(parts.query))
    for key in ("url", "q"):
        target = params.get(key)
        if target and normalize_url(target):
            inner = urlsplit(target)
            if not (is_google_host(inner.hostname) and inner.path.rstrip("/") == "/url"):
                return target.strip()
    return url


def _alert_publisher(raw_summary: Optional[str], final_url: str) -> Optional[str]:
    """Publisher named in the alert text, else the web site of the original link. Never Google."""
    match = _ALERT_PUBLISHER_RE.search(raw_summary or "")
    if match:
        named = clean_text(match.group(1))
        if named:
            return named[:MAX_PUBLISHER_CHARS]
    host = (urlsplit(final_url).hostname or "").lower()
    if not host or is_google_host(host):
        return None
    return host[4:] if host.startswith("www.") else host


def _alert_summary(raw_summary: Optional[str]) -> str:
    """The alert body repeats the title link and publisher; keep only the snippet."""
    text = _ALERT_PUBLISHER_RE.sub(" ", raw_summary or "")
    return clean_text(_ALERT_LINK_RE.sub(" ", text))


def make_dedupe_key(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def parse_date(value: Optional[str]) -> Optional[str]:
    """Return an ISO 8601 UTC string, or None when the date is missing or unreadable."""
    text = (value or "").strip()
    if not text:
        return None
    parsed: Optional[datetime] = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def process_entry(
    raw: dict,
    source_name: str,
    collected_at: Optional[datetime] = None,
    source_type: str = SOURCE_RSS,
    alert_topic: Optional[str] = None,
) -> Article:
    """Build an Article from one raw entry or raise InvalidArticleError."""
    is_alert = source_type == SOURCE_GOOGLE_ALERT
    title = clean_text(raw.get("title"))
    if not title:
        raise InvalidArticleError("missing title")
    link = unwrap_google_redirect(raw.get("link")) if is_alert else raw.get("link")
    url = normalize_url(link)
    if not url:
        raise InvalidArticleError("missing or invalid link")
    publisher = None
    if is_alert:
        publisher = _alert_publisher(raw.get("summary"), url)
        summary = truncate(_alert_summary(raw.get("summary"))) or None
    else:
        summary = truncate(clean_text(raw.get("summary"))) or None
    stamp = (collected_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp_text = stamp.isoformat(timespec="seconds")
    return Article(
        title=title,
        source=clean_text(source_name) or "Unknown source",
        url=url,
        dedupe_key=make_dedupe_key(url),
        collected_at=stamp_text,
        last_seen_at=stamp_text,
        published_at=parse_date(raw.get("published")),
        summary=summary,
        category=categorize(title, summary),
        publisher=publisher,
        alert_topic=(alert_topic or None) if is_alert else None,
    )


def process_entries(
    raw_entries: Iterable[dict],
    source_name: str,
    collected_at: Optional[datetime] = None,
    source_type: str = SOURCE_RSS,
    alert_topic: Optional[str] = None,
) -> tuple[list[Article], list[str]]:
    """Process a batch. Returns (articles, reasons for skipped entries)."""
    articles: list[Article] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for raw in raw_entries:
        try:
            article = process_entry(raw, source_name, collected_at, source_type, alert_topic)
        except InvalidArticleError as exc:
            skipped.append(str(exc))
            continue
        if article.dedupe_key in seen:
            skipped.append("duplicate within feed")
            continue
        seen.add(article.dedupe_key)
        articles.append(article)
    return articles, skipped
