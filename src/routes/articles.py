from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import CATEGORIES, ROLE_ADMIN, ROLE_EDITOR, STATUSES
from src.services.settings_service import SORT_CHOICES

bp = Blueprint("articles", __name__)
MAX_NOTES = 2000


@bp.get("/articles")
def list_articles():
    prefs = deps.settings_service().get()
    repo = deps.articles()
    args = request.args
    category = args["category"] if "category" in args else prefs["default_category"]
    category = category if category in CATEGORIES else ""
    sort = args.get("sort", prefs["default_sort"])
    sort = sort if sort in SORT_CHOICES else prefs["default_sort"]
    source = args.get("source", "")
    status = args.get("status", "")
    status = status if status in STATUSES else ""
    query = args.get("q", "").strip()[:200]
    try:
        page = max(1, int(args.get("page", 1)))
    except ValueError:
        page = 1

    filters = {"category": category or None, "source": source or None,
               "status": status or None, "query": query or None}
    total = repo.count(**filters)
    size = prefs["page_size"]
    pages = max(1, -(-total // size))
    page = min(page, pages)
    items = repo.search(**filters, sort_by=sort, limit=size, offset=(page - 1) * size)
    return render_template(
        "articles.html", items=items, total=total, page=page, pages=pages,
        category=category, source=source, status=status, q=query, sort=sort,
        categories=CATEGORIES, statuses=STATUSES, sources=repo.distinct_sources(),
        sort_choices=SORT_CHOICES, has_any=repo.count() > 0,
    )


@bp.get("/articles/<int:article_id>")
def detail(article_id: int):
    article_repo = deps.articles()
    article = article_repo.get(article_id)
    if article is None:
        abort(404, description="That article was not found.")
    found_by = article_repo.sources_for(article_id)
    only_alerts = bool(found_by) and all(s["source_type"] == "google_alert" for s in found_by)
    user_id = session.get("user_id")
    user = deps.user_repo().get(user_id) if user_id else None
    can_assign = bool(user and user["role"] in (ROLE_ADMIN, ROLE_EDITOR))
    editorial = deps.editorial_service()
    accessible_collections = editorial.list_collections(user["id"]) if user else []
    accessible_ids = {collection["id"] for collection in accessible_collections}
    article_collections = [
        collection for collection in editorial.list_article_collections(article_id)
        if collection["id"] in accessible_ids
    ]
    assigned_ids = {collection["id"] for collection in article_collections}
    available_collections = [
        collection for collection in accessible_collections
        if can_assign and collection["id"] not in assigned_ids
    ] if can_assign else []
    return render_template("article_detail.html", article=article, statuses=STATUSES,
                           found_by=found_by, only_alerts=only_alerts,
                           can_assign=can_assign, article_collections=article_collections,
                           available_collections=available_collections,
                           selected_collection_id=request.args.get("collection_id", type=int))


@bp.post("/articles/<int:article_id>/editorial")
def save_editorial(article_id: int):
    user_id = session.get("user_id")
    user = deps.user_repo().get(user_id) if user_id else None
    if user is None and current_app.config.get("REQUIRE_LOGIN", False):
        flash("Please sign in to update editorial status.", "error")
        return redirect(url_for("auth.login_page"))
    if user is not None and user["role"] not in (ROLE_ADMIN, ROLE_EDITOR):
        flash("You do not have permission to update editorial status.", "error")
        return redirect(url_for("articles.detail", article_id=article_id))

    status = request.form.get("status", "")
    notes = request.form.get("notes", "")
    article_repo = deps.articles()
    article = article_repo.get(article_id)
    if article is None:
        abort(404, description="That article was not found.")
    note_history_failed = False
    if status not in STATUSES:
        flash("Choose a valid editorial status.", "error")
    elif len(notes) > MAX_NOTES:
        flash(f"Notes can have at most {MAX_NOTES} characters.", "error")
    elif not article_repo.update_editorial(article_id, status, notes):
        abort(404, description="That article was not found.")
    else:
        if notes.strip() and user is not None:
            try:
                deps.editorial_service().add_note(article_id, user["id"], notes)
            except ValueError:
                pass
            except Exception:
                current_app.logger.exception("Failed to save note history for article %s", article_id)
                note_history_failed = True
        try:
            deps.editorial_repo().log(user["id"] if user else None, "status_update", "article", article_id, f"{article.status} -> {status}")
        except Exception:
            current_app.logger.exception("Failed to log editorial status update for article %s", article_id)
        if note_history_failed:
            flash("Editorial details were saved, but note history could not be updated.", "info")
        else:
            flash("Editorial details saved.", "success")
    return redirect(url_for("articles.detail", article_id=article_id))
