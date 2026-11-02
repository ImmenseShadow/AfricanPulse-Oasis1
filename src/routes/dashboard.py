from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, url_for

from src import deps

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    articles = deps.articles()
    stats = articles.stats()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    runs = deps.runs()
    now = datetime.now().astimezone().replace(tzinfo=None).isoformat(timespec="minutes")
    return render_template(
        "dashboard.html",
        stats=stats,
        awaiting_review=stats["by_status"].get("New", 0),
        recent_count=articles.count_collected_since(since),
        configured=deps.source_repo().count(),
        enabled=deps.source_repo().count(enabled_only=True),
        categories=articles.category_counts(),
        latest_articles=articles.search(sort_by="collected_at", limit=8),
        latest_run=runs.latest_run(),
        running=runs.running_run(),
        upcoming_items=deps.calendar().upcoming(now, limit=5),
    )


@bp.post("/collect")
def collect():
    run_id, problem = deps.collection_manager().start()
    if problem:
        flash(problem, "error")
        return redirect(url_for("dashboard.index"))
    flash("Collection started.", "info")
    return redirect(url_for("activity.index"))
