from __future__ import annotations

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

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
    service = deps.editorial_service()
    items = service.list_collections(user["id"] if user else None)
    for collection in items:
        collection["articles"] = service.list_collection_articles(collection["id"])
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
    return _assign_article(collection_id, article_id)


@bp.post("/articles/<int:article_id>/collections")
def add_article_from_form(article_id: int):
    try:
        collection_id = int(request.form.get("collection_id", ""))
    except (TypeError, ValueError):
        collection_id = 0
    return _assign_article(collection_id, article_id)


def _assignment_response(article_id: int, collection_id: int, message: str, *, ok: bool, status: int = 200, added: bool = False, collection_name: str = ""):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": ok, "added": added, "message": message, "collection_id": collection_id, "collection_name": collection_name}), status
    flash(message, "success" if ok and added else "info" if ok else "error")
    return redirect(url_for("articles.detail", article_id=article_id, collection_id=collection_id or None))


def _assign_article(collection_id: int, article_id: int):
    user = _current_user()
    if user is None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Please sign in to assign articles."}), 401
        flash("Please sign in to update collections.", "error")
        return redirect(url_for("auth.login_page"))
    if user["role"] not in (ROLE_ADMIN, ROLE_EDITOR):
        return _assignment_response(article_id, collection_id, "You do not have permission to assign articles.", ok=False, status=403)

    article = deps.articles().get(article_id)
    if article is None:
        return _assignment_response(article_id, collection_id, "That article was not found.", ok=False, status=404)

    service = deps.editorial_service()
    collection = next((item for item in service.list_collections(user["id"]) if item["id"] == collection_id), None)
    if collection is None:
        return _assignment_response(article_id, collection_id, "Choose an available editorial section.", ok=False, status=400)

    try:
        added = service.add_article_to_collection(collection_id, article_id)
    except Exception:
        current_app.logger.exception("Failed to assign article %s to collection %s", article_id, collection_id)
        return _assignment_response(article_id, collection_id, "The assignment could not be saved. Your selection is still available to retry.", ok=False, status=500)

    if added:
        message = f"Article assigned to {collection['name']}."
        try:
            deps.editorial_repo().log(user["id"], "article_assigned", "collection", collection_id, f"article_id={article_id}")
        except Exception:
            current_app.logger.exception("Failed to log article assignment for article %s", article_id)
    else:
        message = f"Article is already assigned to {collection['name']}."
    return _assignment_response(article_id, collection_id, message, ok=True, added=added, collection_name=collection["name"])
