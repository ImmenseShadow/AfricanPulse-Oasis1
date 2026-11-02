from __future__ import annotations

import os
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, session, url_for

from src import deps
from src.models.article import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER

bp = Blueprint("exports", __name__)


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return deps.user_repo().get(user_id)


@bp.get("/exports")
def index():
    user = _current_user()
    if user is None and current_app.config.get("REQUIRE_LOGIN", False):
        flash("Please sign in to export content.", "error")
        return redirect(url_for("auth.login_page"))
    rows = deps.articles().search(sort_by="collected_at", limit=50, offset=0)
    return render_template("export.html", items=rows, user=user)


@bp.get("/exports/csv")
def csv_export():
    user = _current_user()
    if user is None and current_app.config.get("REQUIRE_LOGIN", False):
        flash("Please sign in to export content.", "error")
        return redirect(url_for("auth.login_page"))
    if user is not None and user["role"] not in (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER):
        flash("Your account is not permitted to export content.", "error")
        return redirect(url_for("dashboard.index"))
    rows = []
    for article in deps.articles().search(sort_by="collected_at", limit=200, offset=0):
        rows.append({
            "title": article.title,
            "source": article.source,
            "published_at": article.published_at or "",
            "url": article.url,
            "category": article.category,
            "tags": [],
            "status": article.status,
            "collection": "",
        })
    payload = deps.editorial_service().export_csv(rows, "africanpulse-export.csv")
    return send_file(__import__('io').BytesIO(payload), mimetype="text/csv", as_attachment=True, download_name="africanpulse-export.csv")


@bp.get("/exports/pdf")
def pdf_export():
    user = _current_user()
    if user is None and current_app.config.get("REQUIRE_LOGIN", False):
        flash("Please sign in to export content.", "error")
        return redirect(url_for("auth.login_page"))
    if user is not None and user["role"] not in (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER):
        flash("Your account is not permitted to export content.", "error")
        return redirect(url_for("dashboard.index"))
    rows = []
    for article in deps.articles().search(sort_by="collected_at", limit=200, offset=0):
        rows.append({
            "title": article.title,
            "source": article.source,
            "status": article.status,
            "category": article.category,
            "url": article.url,
        })
    payload = deps.editorial_service().export_pdf(rows, "AfricanPulse Oasis report")
    return send_file(__import__('io').BytesIO(payload), mimetype="application/pdf", as_attachment=True, download_name="africanpulse-report.pdf")
