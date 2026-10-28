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
from src.storage.settings_repository import SettingsRepository
from src.storage.source_repository import SourceRepository

MAX_NAME_LENGTH = 80
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
        parts.port  # raises ValueError for a bad port
    except ValueError:
        raise ValidationError("The feed URL is not valid.")
    if parts.scheme.lower() not in ("http", "https"):
        raise ValidationError("Only http:// and https:// feed URLs are supported.")
    if not host:
        raise ValidationError("The feed URL needs a host name.")
    if parts.username or parts.password:
        raise ValidationError("Do not put a username or password in the feed URL.")
    if not allow_private:
        lowered = host.lower()
        blocked = lowered == "localhost" or lowered.endswith(".localhost") or lowered.isdigit()
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

    def _clean(self, name: str, url: str, exclude_id: Optional[int] = None) -> tuple[str, str]:
        name = validate_name(name)
        url = validate_feed_url(url, self.allow_private)
        if self.repo.name_exists(name, exclude_id):
            raise ValidationError("A source with that name already exists.")
        return name, url

    def add(self, name: str, url: str) -> int:
        name, url = self._clean(name, url)
        try:
            return self.repo.add(name, url, _now())
        except sqlite3.IntegrityError:
            raise ValidationError("That feed URL is already configured.")

    def update(self, source_id: int, name: str, url: str) -> None:
        if self.repo.get(source_id) is None:
            raise ValidationError("That source no longer exists.")
        name, url = self._clean(name, url, exclude_id=source_id)
        try:
            self.repo.update(source_id, name, url)
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
