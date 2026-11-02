from __future__ import annotations

import sqlite3

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import STATUSES

bp = Blueprint("editorial", __name__)
STATUS_ALIASES = {"Review": "Under Review"}


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return deps.user_repo().get(user_id)


@bp.get("/editorial")
def index():
    user = _current_user()
    if user is None and not current_app.config.get("REQUIRE_LOGIN", False):
        return render_template("editorial.html", articles=[], statuses=STATUSES, user=None, current_status="")
    if user is None:
        flash("Please sign in to access the editorial review workspace.", "error")
        return redirect(url_for("auth.login_page"))
    requested_status = request.args.get("status", "")
    status = STATUS_ALIASES.get(requested_status, requested_status)
    if status and status not in STATUSES:
        return render_template(
            "editorial.html", articles=[], statuses=STATUSES, user=user,
            current_status="", error_message="That editorial stage is not available.",
        ), 404
    filters = {"status": status or None, "query": request.args.get("q", "") or None}
    try:
        repo = deps.articles()
        items = repo.search(
            category=None,
            source=None,
            status=filters["status"],
            query=filters["query"],
            sort_by="collected_at",
            limit=50,
            offset=0,
        )
    except sqlite3.Error:
        current_app.logger.exception("Editorial stage query failed for status %s", status or "all")
        return render_template(
            "editorial.html", articles=[], statuses=STATUSES, user=user,
            current_status=status, error_message="Editorial stages are temporarily unavailable. Please try again.",
        ), 503
    return render_template(
        "editorial.html", articles=items, statuses=STATUSES,
        user=user, current_status=status,
    )
