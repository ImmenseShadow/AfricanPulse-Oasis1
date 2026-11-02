"""Article data model and the controlled vocabularies used across the app."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CATEGORIES = (
    "Politics and Governance",
    "Technology and Innovation",
    "Business and Economy",
    "Education",
    "Environment",
    "Security",
    "Health",
    "International Affairs",
    "Culture and Society",
    "Science and Research",
    "Technology",
    "Science",
    "Society",
    "General News",
    "Uncategorized",
)

EDITORIAL_STATUSES = ("New", "Under Review", "Approved", "Rejected", "Archived", "Used")
LEGACY_STATUSES = ("Selected for Content",)
STATUSES = EDITORIAL_STATUSES + LEGACY_STATUSES

ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER)

SOURCE_RSS = "rss"
SOURCE_GOOGLE_ALERT = "google_alert"
SOURCE_TYPES = {SOURCE_RSS: "RSS / Atom feed", SOURCE_GOOGLE_ALERT: "Google Alerts feed"}


@dataclass
class Article:
    """One collected article. Only links and short feed summaries are stored."""

    title: str
    source: str
    url: str
    dedupe_key: str
    collected_at: str
    published_at: Optional[str] = None
    summary: Optional[str] = None
    category: str = "Uncategorized"
    status: str = "New"
    notes: str = ""
    last_seen_at: Optional[str] = None
    id: Optional[int] = None
    publisher: Optional[str] = None     # only set when the feed or link identifies one
    alert_topic: Optional[str] = None   # Google Alert topic that discovered the article
