from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from src import deps
from src.models.article import CATEGORIES, STATUSES
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
    article = deps.articles().get(article_id)
    if article is None:
        abort(404, description="That article was not found.")
    found_by = deps.articles().sources_for(article_id)
    only_alerts = bool(found_by) and all(s["source_type"] == "google_alert" for s in found_by)
    return render_template("article_detail.html", article=article, statuses=STATUSES,
                           found_by=found_by, only_alerts=only_alerts)


@bp.post("/articles/<int:article_id>/editorial")
def save_editorial(article_id: int):
    status = request.form.get("status", "")
    notes = request.form.get("notes", "")
    if status not in STATUSES:
        flash("Choose a valid editorial status.", "error")
    elif len(notes) > MAX_NOTES:
        flash(f"Notes can have at most {MAX_NOTES} characters.", "error")
    elif not deps.articles().update_editorial(article_id, status, notes):
        abort(404, description="That article was not found.")
    else:
        flash("Editorial details saved.", "success")
    return redirect(url_for("articles.detail", article_id=article_id))
