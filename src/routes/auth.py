from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from src import deps
from src.models.article import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER

bp = Blueprint("auth", __name__)


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return deps.user_repo().get(user_id)


@bp.get("/login")
def login_page():
    return render_template("login.html")


@bp.post("/login")
def login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = deps.auth_service().login(username, password)
    if user is None:
        flash("Invalid username or password.", "error")
        return render_template("login.html", username=username), 401
    session["user_id"] = user["id"]
    session["user_role"] = user["role"]
    flash("Signed in successfully.", "success")
    return redirect(url_for("dashboard.index"))


@bp.post("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("dashboard.index"))


@bp.get("/admin/users")
def admin_users():
    if not current_app.config.get("REQUIRE_LOGIN", False):
        return redirect(url_for("dashboard.index"))
    user = _current_user()
    if user is None or user["role"] != ROLE_ADMIN:
        flash("You do not have access to user administration.", "error")
        return redirect(url_for("dashboard.index"))
    return render_template("admin_users.html", users=deps.user_repo().list_users(), current_user=user)


@bp.post("/admin/users/<int:user_id>/role")
def set_role(user_id: int):
    if not current_app.config.get("REQUIRE_LOGIN", False):
        abort(403)
    user = _current_user()
    if user is None or user["role"] != ROLE_ADMIN:
        flash("Only administrators may change roles.", "error")
        return redirect(url_for("dashboard.index"))
    new_role = request.form.get("role", ROLE_VIEWER)
    if new_role not in (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER):
        flash("Choose a valid role.", "error")
        return redirect(url_for("auth.admin_users"))
    if user_id == user["id"] and new_role != ROLE_ADMIN:
        flash("You cannot remove your own administrator role.", "error")
        return redirect(url_for("auth.admin_users"))
    deps.user_repo().update_role(user_id, new_role)
    flash("User role updated.", "success")
    return redirect(url_for("auth.admin_users"))


@bp.post("/admin/users/<int:user_id>/toggle")
def toggle_user(user_id: int):
    if not current_app.config.get("REQUIRE_LOGIN", False):
        abort(403)
    user = _current_user()
    if user is None or user["role"] != ROLE_ADMIN:
        flash("Only administrators may change user status.", "error")
        return redirect(url_for("dashboard.index"))
    active = (request.form.get("active") == "1")
    deps.user_repo().set_active(user_id, active)
    flash("User account updated.", "success")
    return redirect(url_for("auth.admin_users"))
