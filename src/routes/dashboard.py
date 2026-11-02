from datetime import datetime, timedelta, timezone
from math import cos, pi, radians, sin
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import CATEGORY_META, category_color, category_details

bp = Blueprint("dashboard", __name__)


def _ordered_category_counts(raw_counts):
    counts = {}
    for category, count in sorted(raw_counts.items(), key=lambda item: (-item[1], item[0])):
        name = (category or "Uncategorized").strip() or "Uncategorized"
        counts[name] = counts.get(name, 0) + int(count or 0)
    return counts


def _category_total(category_counts):
    return sum(value for key, value in category_counts.items() if key != "Uncategorized")


def _chart_segments(category_counts, selected_name):
    ordered = [(name, count) for name, count in category_counts.items() if count > 0 and name != "Uncategorized"]
    if not ordered:
        return []
    total = sum(count for _, count in ordered)
    if total <= 0:
        return []
    radius = 86
    offset = 0.0
    segments = []
    for name, count in sorted(ordered, key=lambda item: (-item[1], item[0])):
        sweep = 360 * count / total
        gap = min(0.8, sweep / 4)
        start_angle = -90 + offset + gap / 2
        end_angle = -90 + offset + sweep - gap / 2
        start_x = 120 + radius * cos(radians(start_angle))
        start_y = 120 + radius * sin(radians(start_angle))
        end_x = 120 + radius * cos(radians(end_angle))
        end_y = 120 + radius * sin(radians(end_angle))
        large_arc = 1 if sweep - gap > 180 else 0
        segments.append({
            "name": name,
            "count": count,
            "percent": round((count / total * 100), 1) if total else 0,
            "color": category_color(name),
            "path": f"M {start_x:.3f} {start_y:.3f} A {radius} {radius} 0 {large_arc} 1 {end_x:.3f} {end_y:.3f}",
            "selected": name == selected_name,
        })
        offset += sweep
    return segments


@bp.get("/")
def index():
    articles = deps.articles()
    stats = articles.stats()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    runs = deps.runs()
    now = datetime.now().astimezone().replace(tzinfo=None).isoformat(timespec="minutes")
    category_counts = _ordered_category_counts(articles.category_counts())
    total_categorized = _category_total(category_counts)
    return render_template(
        "dashboard.html",
        stats=stats,
        awaiting_review=stats["by_status"].get("New", 0),
        recent_count=articles.count_collected_since(since),
        configured=deps.source_repo().count(),
        enabled=deps.source_repo().count(enabled_only=True),
        categories=category_counts,
        total_categorized=total_categorized,
        latest_articles=articles.search(sort_by="collected_at", limit=8),
        latest_run=runs.latest_run(),
        running=runs.running_run(),
        upcoming_items=deps.calendar().upcoming(now, limit=5),
    )


@bp.get("/category-intelligence")
def category_intelligence():
    referrer = request.referrer or ""
    is_dashboard_entry = request.args.get("source") == "dashboard"
    referrer_is_dashboard = bool(referrer) and urlparse(referrer).path == url_for("dashboard.index")
    if is_dashboard_entry:
        session["dashboard_category_intelligence_access"] = True
    elif not session.get("dashboard_category_intelligence_access") and not referrer_is_dashboard:
        flash("Open the category intelligence page from the Dashboard overview.", "error")
        return redirect(url_for("dashboard.index"))

    articles = deps.articles()
    category_counts = _ordered_category_counts(articles.category_counts())
    if not category_counts:
        selected_category = "Uncategorized"
        category_summary = []
        related_articles = []
        pie_segments = []
    else:
        active_categories = {name: count for name, count in category_counts.items() if name != "Uncategorized"}
        default_category = next(iter(active_categories), "Uncategorized")
        selected_category = request.args.get("category") or default_category
        if selected_category not in category_counts:
            selected_category = default_category
        category_summary = []
        for name in CATEGORY_META:
            count = category_counts.get(name, 0)
            category_total = _category_total(category_counts)
            percent = round((count / category_total * 100), 1) if category_total and name != "Uncategorized" else 0
            meta = category_details(name)
            category_summary.append({
                "name": name,
                "count": count,
                "percent": percent,
                "summary": meta["summary"],
                "detail": meta["detail"],
                "examples": meta["examples"],
                "selected": name == selected_category,
                "color": category_color(name),
            })
        related_articles = articles.search(category=selected_category, sort_by="published_at", limit=12)
        pie_segments = _chart_segments(category_counts, selected_category)

    selected_meta = category_details(selected_category)
    context = {
        "category_counts": category_counts,
        "category_summary": category_summary,
        "selected_category": selected_category,
        "selected_count": category_counts.get(selected_category, 0),
        "selected_percent": round((category_counts.get(selected_category, 0) / max(_category_total(category_counts), 1) * 100), 1) if category_counts and selected_category != "Uncategorized" else 0,
        "pie_segments": pie_segments,
        "related_articles": related_articles,
        "total_categorized": _category_total(category_counts),
        "latest_article": related_articles[0] if related_articles else None,
        "selected_meta": selected_meta,
    }
    if request.args.get("fragment") == "1":
        return render_template("category_intelligence_fragment.html", **context)
    return render_template("category_intelligence.html", **context)


@bp.post("/collect")
def collect():
    run_id, problem = deps.collection_manager().start()
    if problem:
        flash(problem, "error")
        return redirect(url_for("dashboard.index"))
    flash("Collection started.", "info")
    return redirect(url_for("activity.index"))
