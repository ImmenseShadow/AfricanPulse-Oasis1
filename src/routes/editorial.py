from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import ROLE_ADMIN, ROLE_EDITOR, STATUSES

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


@bp.post("/articles/<int:article_id>/editorial")
def save_editorial(article_id: int):
    user = _current_user()
    if user is None:
        flash("Please sign in to update editorial status.", "error")
        return redirect(url_for("auth.login_page"))
    if user["role"] not in (ROLE_ADMIN, ROLE_EDITOR):
        flash("You do not have permission to update editorial status.", "error")
        return redirect(url_for("articles.detail", article_id=article_id))
    status = request.form.get("status", "")
    notes = request.form.get("notes", "")
    if status not in STATUSES:
        flash("Choose a valid editorial status.", "error")
        return redirect(url_for("articles.detail", article_id=article_id))
    if len(notes) > 2000:
        flash("Notes can have at most 2000 characters.", "error")
        return redirect(url_for("articles.detail", article_id=article_id))
    article = deps.articles().get(article_id)
    if article is None:
        abort(404, description="That article was not found.")
    deps.articles().update_editorial(article_id, status, notes)
    if notes.strip():
        try:
            deps.editorial_service().add_note(article_id, user["id"], notes)
        except ValueError:
            pass
    deps.editorial_repo().log(user["id"], "status_update", "article", article_id, f"{article.status} -> {status}")
    flash("Editorial details saved.", "success")
    return redirect(url_for("articles.detail", article_id=article_id))
