"""Source management: validation, CRUD and feed testing."""
from __future__ import annotations

import ipaddress
import re
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit

from config.settings import FeedSource
from src.collectors.rss_collector import CollectorError
from src.models.article import SOURCE_GOOGLE_ALERT, SOURCE_RSS, SOURCE_TYPES
from src.storage.settings_repository import SettingsRepository
from src.storage.source_repository import SourceRepository
from src.url_safety import is_blocked_host_name

MAX_NAME_LENGTH = 80
MAX_TOPIC_LENGTH = 120
MAX_URL_LENGTH = 2048
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class ValidationError(ValueError):
    """User supplied input was rejected. The message is safe to show."""


def validate_name(name: str) -> str:
    cleaned = " ".join(_CONTROL_CHARS.sub(" ", name or "").split())
    if not cleaned:
        raise ValidationError("Enter a source name.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationError(f"Source names can have at most {MAX_NAME_LENGTH} characters.")
    return cleaned


def validate_source_type(source_type: Optional[str]) -> str:
    cleaned = (source_type or SOURCE_RSS).strip()
    if cleaned not in SOURCE_TYPES:
        raise ValidationError("Choose a valid source type.")
    return cleaned


def validate_alert_topic(topic: Optional[str], source_type: str) -> Optional[str]:
    """The topic is required for Google Alerts and ignored for other source types."""
    if source_type != SOURCE_GOOGLE_ALERT:
        return None
    cleaned = " ".join(_CONTROL_CHARS.sub(" ", topic or "").split())
    if not cleaned:
        raise ValidationError("Enter the alert topic, the search terms this Google Alert follows.")
    if len(cleaned) > MAX_TOPIC_LENGTH:
        raise ValidationError(f"Alert topics can have at most {MAX_TOPIC_LENGTH} characters.")
    return cleaned


def validate_feed_url(url: str, allow_private: bool = False) -> str:
    """Accept only plain http(s) feed URLs. Rejects javascript:, file:, credentials in the URL,
    and (by default) localhost or private network addresses."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValidationError("Enter a feed URL.")
    if len(cleaned) > MAX_URL_LENGTH or _CONTROL_CHARS.search(cleaned):
        raise ValidationError("The feed URL is not valid.")
    try:
        parts = urlsplit(cleaned)
        host = parts.hostname
        port = parts.port  # raises ValueError for a bad port
    except ValueError:
        raise ValidationError("The feed URL is not valid.")
    if parts.scheme.lower() not in ("http", "https"):
        raise ValidationError("Only http:// and https:// feed URLs are supported.")
    if not host:
        raise ValidationError("The feed URL needs a host name.")
    if parts.username or parts.password:
        raise ValidationError("Do not put a username or password in the feed URL.")
    if port is not None and (port <= 0 or port > 65535):
        raise ValidationError("The feed URL is not valid.")
    if not allow_private:
        lowered = host.lower()
        blocked = is_blocked_host_name(lowered) or lowered.isdigit()
        try:
            ip = ipaddress.ip_address(host)
            blocked = blocked or not ip.is_global
        except ValueError:
            pass
        if blocked:
            raise ValidationError("Feeds on localhost or private network addresses are not allowed.")
    return cleaned


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SourceService:
    def __init__(
        self,
        repo: SourceRepository,
        fetch: Callable[..., list[dict]],
        allow_private: bool = False,
        timeout: int = 15,
    ):
        self.repo = repo
        self._fetch = fetch
        self.allow_private = allow_private
        self.timeout = timeout

    def _clean(
        self, name: str, url: str, source_type: Optional[str] = None,
        alert_topic: Optional[str] = None, exclude_id: Optional[int] = None,
    ) -> tuple[str, str, str, Optional[str]]:
        name = validate_name(name)
        source_type = validate_source_type(source_type)
        topic = validate_alert_topic(alert_topic, source_type)
        url = validate_feed_url(url, self.allow_private)
        if self.repo.name_exists(name, exclude_id):
            raise ValidationError("A source with that name already exists.")
        return name, url, source_type, topic

    def add(
        self, name: str, url: str, source_type: str = SOURCE_RSS, alert_topic: Optional[str] = None
    ) -> int:
        name, url, source_type, topic = self._clean(name, url, source_type, alert_topic)
        try:
            return self.repo.add(name, url, _now(), True, source_type, topic)
        except sqlite3.IntegrityError:
            raise ValidationError("That feed URL is already configured.")

    def update(
        self, source_id: int, name: str, url: str,
        source_type: Optional[str] = None, alert_topic: Optional[str] = None,
    ) -> None:
        """Edit a source. Leaving source_type or alert_topic as None keeps the stored value."""
        current = self.repo.get(source_id)
        if current is None:
            raise ValidationError("That source no longer exists.")
        if source_type is None:
            source_type = current["source_type"]
        if alert_topic is None:
            alert_topic = current["alert_topic"]
        name, url, source_type, topic = self._clean(name, url, source_type, alert_topic, exclude_id=source_id)
        try:
            self.repo.update(source_id, name, url, source_type, topic)
        except sqlite3.IntegrityError:
            raise ValidationError("That feed URL is already configured.")

    def set_enabled(self, source_id: int, enabled: bool) -> None:
        if not self.repo.set_enabled(source_id, enabled):
            raise ValidationError("That source no longer exists.")

    def delete(self, source_id: int) -> None:
        if not self.repo.delete(source_id):
            raise ValidationError("That source no longer exists.")

    def test(self, url: str) -> int:
        """Fetch and parse a feed. Returns the entry count or raises ValidationError with the problem."""
        url = validate_feed_url(url, self.allow_private)
        try:
            return len(self._fetch(url, timeout=self.timeout))
        except CollectorError as exc:
            raise ValidationError(str(exc))

    def seed_from_config(self, config_sources: list[FeedSource], settings: SettingsRepository) -> int:
        """Copy the Phase 1 news_sources.json feeds into the database exactly once, so sources
        a user later deletes do not come back."""
        if settings.get("sources_seeded") == "1":
            return 0
        added = 0
        for source in config_sources:
            try:
                name = validate_name(source.name)
                url = validate_feed_url(source.feed_url, self.allow_private)
            except ValidationError:
                continue
            if not self.repo.name_exists(name) and self.repo.add_if_missing(name, url, _now(), source.enabled):
                added += 1
        settings.set_many({"sources_seeded": "1"})
        return added
