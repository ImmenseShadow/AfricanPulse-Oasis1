from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import STATUSES

bp = Blueprint("editorial", __name__)


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
    status = request.args.get("status", "")
    filters = {"status": status if status in STATUSES else None, "query": request.args.get("q", "") or None}
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
    return render_template("editorial.html", articles=items, statuses=STATUSES, user=user, current_status=status)
