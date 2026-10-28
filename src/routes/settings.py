from flask import Blueprint, flash, redirect, render_template, request, url_for

from src import deps
from src.models.article import CATEGORIES
from src.services.settings_service import (
    PAGE_SIZES, SORT_CHOICES, TIMEOUT_RANGE, SettingsError,
)

bp = Blueprint("settings", __name__)


def _render(values, status=200):
    return render_template(
        "settings.html", values=values, categories=CATEGORIES, sort_choices=SORT_CHOICES,
        page_sizes=PAGE_SIZES, timeout_range=TIMEOUT_RANGE,
    ), status


@bp.get("/settings")
def index():
    return _render(deps.settings_service().get())


@bp.post("/settings")
def save():
    form = {k: request.form.get(k, "") for k in ("default_sort", "default_category", "request_timeout", "page_size")}
    try:
        deps.settings_service().save(form)
    except SettingsError as exc:
        flash(str(exc), "error")
        return _render(form, 400)
    flash("Settings saved.", "success")
    return redirect(url_for("settings.index"))
