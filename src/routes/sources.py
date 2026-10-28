from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from src import deps
from src.services.source_service import ValidationError

bp = Blueprint("sources", __name__)


def _render(form=None):
    return render_template("sources.html", sources=deps.source_repo().list_sources(), form=form or {})


@bp.get("/sources")
def index():
    return _render()


@bp.post("/sources")
def add():
    name, url = request.form.get("name", ""), request.form.get("url", "")
    try:
        deps.source_service().add(name, url)
    except ValidationError as exc:
        flash(str(exc), "error")
        return _render({"name": name, "url": url}), 400
    flash("Source added.", "success")
    return redirect(url_for("sources.index"))


@bp.post("/sources/test")
def test_url():
    name, url = request.form.get("name", ""), request.form.get("url", "")
    try:
        count = deps.source_service().test(url)
        flash(f"Feed reachable and readable: {count} entries found. It has not been saved yet.", "success")
    except ValidationError as exc:
        flash(f"Feed test failed: {exc}", "error")
    return _render({"name": name, "url": url})


@bp.get("/sources/<int:source_id>/edit")
def edit(source_id: int):
    source = deps.source_repo().get(source_id)
    if source is None:
        abort(404, description="That source was not found.")
    return render_template("source_edit.html", source=source, form={})


@bp.post("/sources/<int:source_id>/edit")
def update(source_id: int):
    name, url = request.form.get("name", ""), request.form.get("url", "")
    source = deps.source_repo().get(source_id)
    if source is None:
        abort(404, description="That source was not found.")
    try:
        deps.source_service().update(source_id, name, url)
    except ValidationError as exc:
        flash(str(exc), "error")
        return render_template("source_edit.html", source=source, form={"name": name, "url": url}), 400
    flash("Source updated.", "success")
    return redirect(url_for("sources.index"))


def _simple_action(source_id: int, action, message: str):
    try:
        action()
        flash(message, "success")
    except ValidationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("sources.index"))


@bp.post("/sources/<int:source_id>/toggle")
def toggle(source_id: int):
    enable = request.form.get("enabled") == "1"
    return _simple_action(source_id, lambda: deps.source_service().set_enabled(source_id, enable),
                          "Source enabled." if enable else "Source disabled.")


@bp.post("/sources/<int:source_id>/delete")
def delete(source_id: int):
    return _simple_action(source_id, lambda: deps.source_service().delete(source_id),
                          "Source removed. Articles already collected were kept.")


@bp.post("/sources/<int:source_id>/test")
def test_saved(source_id: int):
    source = deps.source_repo().get(source_id)
    if source is None:
        abort(404, description="That source was not found.")
    try:
        count = deps.source_service().test(source["feed_url"])
        flash(f"{source['name']}: reachable and readable, {count} entries found.", "success")
    except ValidationError as exc:
        flash(f"{source['name']}: test failed. {exc}", "error")
    return redirect(url_for("sources.index"))
