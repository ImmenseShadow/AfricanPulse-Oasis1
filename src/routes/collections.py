from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER

bp = Blueprint("collections", __name__)


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return deps.user_repo().get(user_id)


@bp.get("/collections")
def index():
    user = _current_user()
    if user is None and deps.user_repo().list_users():
        return redirect(url_for("auth.login_page"))
    items = deps.editorial_service().list_collections(user["id"] if user else None)
    return render_template("collections.html", collections=items, user=user)


@bp.post("/collections")
def create_collection():
    user = _current_user()
    if user is None:
        flash("Please sign in to manage collections.", "error")
        return redirect(url_for("auth.login_page"))
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    if not name:
        flash("Collection name is required.", "error")
        return redirect(url_for("collections.index"))
    deps.editorial_service().create_collection(name, description, user["id"], bool(request.form.get("is_shared")))
    flash("Collection created.", "success")
    return redirect(url_for("collections.index"))


@bp.post("/collections/<int:collection_id>/articles/<int:article_id>")
def add_article(collection_id: int, article_id: int):
    user = _current_user()
    if user is None:
        flash("Please sign in to update collections.", "error")
        return redirect(url_for("auth.login_page"))
    deps.editorial_service().add_article_to_collection(collection_id, article_id)
    flash("Article added to the collection.", "success")
    return redirect(url_for("articles.detail", article_id=article_id))
