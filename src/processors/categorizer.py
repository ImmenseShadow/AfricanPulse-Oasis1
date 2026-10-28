"""Keyword based categorisation, kept separate from the UI.

Extend RULES to add keywords. A category is only assigned when the evidence is
clear; otherwise the article stays "Uncategorized" instead of guessing.
"""
from __future__ import annotations

import re
from typing import Mapping, Optional, Sequence

RULES: dict[str, tuple[str, ...]] = {
    "Technology": (
        "technology", "tech", "software", "startup", "startups", "fintech", "app",
        "apps", "ai", "artificial intelligence", "internet", "mobile", "cybersecurity",
        "digital", "blockchain", "robotics", "5g", "telecom", "broadband",
    ),
    "Education": (
        "school", "schools", "university", "universities", "student", "students",
        "teacher", "teachers", "education", "scholarship", "exam", "exams",
        "literacy", "curriculum", "college",
    ),
    "Science": (
        "scientist", "scientists", "research", "researchers", "space", "satellite",
        "astronomy", "physics", "fossil", "laboratory", "discovery", "genome",
    ),
    "Business and Economy": (
        "economy", "economic", "inflation", "trade", "bank", "banks", "market",
        "markets", "investment", "investors", "currency", "gdp", "tariff", "tariffs",
        "business", "exports", "imports", "shares", "oil prices",
    ),
    "Politics and Governance": (
        "election", "elections", "president", "parliament", "minister", "government",
        "opposition", "vote", "voters", "senate", "coup", "constitution", "sanctions",
        "ruling party",
    ),
    "Society": (
        "community", "protest", "protests", "crime", "police", "culture", "festival",
        "religion", "migrants", "migration", "women", "youth", "family", "court",
    ),
    "Environment": (
        "climate", "flood", "floods", "drought", "wildlife", "pollution",
        "conservation", "deforestation", "emissions", "renewable", "solar",
        "rainfall", "environment",
    ),
    "Health": (
        "health", "hospital", "hospitals", "disease", "vaccine", "vaccines",
        "malaria", "cholera", "outbreak", "doctors", "medical", "patients",
        "ebola", "hiv",
    ),
}

TITLE_WEIGHT = 2
SUMMARY_WEIGHT = 1
MIN_SCORE = 2  # one title hit, or two summary hits


def _count(keyword: str, text: str) -> int:
    return len(re.findall(rf"\b{re.escape(keyword)}\b", text))


def categorize(
    title: str,
    summary: Optional[str] = None,
    rules: Mapping[str, Sequence[str]] = RULES,
) -> str:
    title_text = (title or "").lower()
    summary_text = (summary or "").lower()
    scores: dict[str, int] = {}
    for category, keywords in rules.items():
        score = sum(
            _count(k.lower(), title_text) * TITLE_WEIGHT
            + _count(k.lower(), summary_text) * SUMMARY_WEIGHT
            for k in keywords
        )
        if score:
            scores[category] = score
    if not scores:
        return "Uncategorized"
    ranked = sorted(scores.values(), reverse=True)
    best = ranked[0]
    if best < MIN_SCORE or (len(ranked) > 1 and ranked[1] == best):
        return "Uncategorized"
    return next(c for c, s in scores.items() if s == best)
