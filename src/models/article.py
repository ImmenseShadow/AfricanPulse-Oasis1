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

CATEGORY_COLORS = {
    "Politics and Governance": "#1e5f7a",
    "Technology and Innovation": "#2d7a6d",
    "Business and Economy": "#d79a2a",
    "Education": "#6c8ec5",
    "Environment": "#3b8d64",
    "Security": "#8b4a6d",
    "Health": "#b85b51",
    "International Affairs": "#4c6f9f",
    "Culture and Society": "#bb7c3a",
    "Science and Research": "#7d6cc6",
    "Technology": "#2b7a7d",
    "Science": "#5591a3",
    "Society": "#a96b57",
    "General News": "#7c8a84",
    "Uncategorized": "#8e8e8e",
}

CATEGORY_META = {
    "Politics and Governance": {
        "summary": "Political developments, government institutions, public policy, elections and diplomacy.",
        "detail": "Covers elections, government policy, parliamentary decisions, and international relations.",
        "examples": ["Elections", "Government policy", "Parliamentary decisions", "International relations"],
    },
    "Technology and Innovation": {
        "summary": "Technological advancements, digital transformation and emerging innovation.",
        "detail": "Tracks AI, cybersecurity, robotics, software development and digital infrastructure.",
        "examples": ["Artificial intelligence", "Cybersecurity", "Robotics", "Software development", "Digital infrastructure"],
    },
    "Business and Economy": {
        "summary": "Economic activity, financial developments, business operations and trade.",
        "detail": "Highlights startups, inflation, trade, investments and policy decisions affecting markets.",
        "examples": ["Startups", "Inflation", "International trade", "Business investments"],
    },
    "Education": {
        "summary": "Learning, academic institutions and education policy.",
        "detail": "Considers university admissions, scholarships, reforms and digital learning.",
        "examples": ["University admissions", "Scholarships", "Educational reforms", "Academic research", "Digital learning"],
    },
    "Environment": {
        "summary": "Environmental protection, climate and sustainability issues.",
        "detail": "Covers climate impacts, deforestation, renewable energy and waste management.",
        "examples": ["Climate change", "Deforestation", "Renewable energy", "Waste management"],
    },
    "Security": {
        "summary": "Security, public safety, defence and digital threat monitoring.",
        "detail": "Tracks cybersecurity incidents, public safety initiatives and national security policy.",
        "examples": ["Cybersecurity incidents", "National security policy", "Digital threats", "Public safety initiatives"],
    },
    "Health": {
        "summary": "Healthcare, public health and medical research.",
        "detail": "Covers medical discoveries, disease prevention, healthcare access and public health campaigns.",
        "examples": ["Medical discoveries", "Public health campaigns", "Healthcare access", "Disease prevention"],
    },
    "International Affairs": {
        "summary": "Foreign policy, global institutions and international cooperation.",
        "detail": "Reviews diplomatic developments, cross-border events and international agreements.",
        "examples": ["United Nations developments", "International agreements", "Diplomatic relations", "Global conflicts"],
    },
    "Culture and Society": {
        "summary": "Cultural identity, communities and social change.",
        "detail": "Explores heritage, festivals, social inclusion, community development and societal change.",
        "examples": ["African cultural heritage", "Cultural festivals", "Community development", "Social inclusion", "Traditional practices"],
    },
    "Science and Research": {
        "summary": "Scientific discoveries, research and technical investigation.",
        "detail": "Tracks physics, biology, space exploration and new scientific findings across disciplines.",
        "examples": ["Physics discoveries", "Biological research", "Space exploration", "Scientific publications"],
    },
    "Technology": {
        "summary": "Legacy technology coverage retained for historical data consistency.",
        "detail": "This category is kept as part of the application’s existing taxonomy and maps to technology-focused coverage.",
        "examples": ["Digital systems", "Hardware", "Software updates"],
    },
    "Science": {
        "summary": "Legacy science coverage retained for historical data consistency.",
        "detail": "This category remains in the app’s historical taxonomy and is shown here for compatibility.",
        "examples": ["Research updates", "Scientific analysis", "Field reports"],
    },
    "Society": {
        "summary": "Legacy society coverage retained for historical data consistency.",
        "detail": "This is kept to maintain continuity for older article records and community-focused news.",
        "examples": ["Community development", "Social trends", "Public dialogue"],
    },
    "General News": {
        "summary": "Broad current affairs and general spot coverage.",
        "detail": "Used for stories that are relevant to the public agenda but do not fit a narrower category.",
        "examples": ["Daily briefings", "Regional stories", "General current affairs"],
    },
    "Uncategorized": {
        "summary": "Articles that do not yet match the active category rules.",
        "detail": "This bucket remains separate so uncategorized items are not misrepresented as another category.",
        "examples": ["Unclear or weak signals", "Insufficient category evidence"],
    },
}


def category_details(category: Optional[str]) -> dict:
    name = (category or "Uncategorized").strip() or "Uncategorized"
    return CATEGORY_META.get(name, {
        "summary": "Category details are maintained separately from article records.",
        "detail": "This entry stays available in case the database includes a category label not yet described in the active metadata.",
        "examples": [],
    })


def category_color(category: Optional[str]) -> str:
    name = (category or "Uncategorized").strip() or "Uncategorized"
    return CATEGORY_COLORS.get(name, "#7c8a84")


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
