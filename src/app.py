"""Flask application factory."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from config.settings import (
    PROJECT_ROOT, allow_private_feeds, get_database_path, load_or_create_secret_key, load_sources, ConfigError,
)
from src.collectors.rss_collector import fetch_feed
from src.security import init_security
from src.services.collection_manager import CollectionManager
from src.storage.collection_repository import CollectionRepository
from src.storage.database import Database
from src.storage.settings_repository import SettingsRepository

log = logging.getLogger(__name__)

STATUS_LABELS = {
    "running": "Running",
    "completed": "Completed",
    "completed_with_errors": "Completed with errors",
    "failed": "Failed",
}


def fmt_dt(value: Optional[str], missing: str = "Not provided") -> str:
    if not value:
        return missing
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return value


def create_app(config: Optional[dict] = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.update(
        DATABASE_PATH=str(get_database_path()),
        SECRET_KEY=None,
        COLLECT_SYNC=False,
        SEED_SOURCES=True,
        FETCH_FEED=fetch_feed,
        ALLOW_PRIVATE_FEEDS=allow_private_feeds(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    app.config.update(config or {})
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = load_or_create_secret_key()

    db = Database(app.config["DATABASE_PATH"])
    db.initialize()
    app.extensions["oasis_db"] = db
    _startup_housekeeping(app, db)

    from src.services.settings_service import SettingsService

    manager = CollectionManager(
        db,
        fetch=app.config["FETCH_FEED"],
        timeout_getter=lambda: SettingsService(SettingsRepository(db)).get()["request_timeout"],
        sync=app.config["COLLECT_SYNC"],
    )
    app.extensions["collection_manager"] = manager

    init_security(app)
    app.jinja_env.globals["page_url"] = lambda page: url_for(
        request.endpoint, **{**request.args.to_dict(), "page": page}
    )
    app.jinja_env.filters["dt"] = fmt_dt
    app.jinja_env.filters["run_status"] = lambda s: STATUS_LABELS.get(s, s)

    from src.routes import activity, articles, dashboard, settings, sources

    for module in (dashboard, articles, sources, activity, settings):
        app.register_blueprint(module.bp)

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return render_template("error.html", code=error.code, title=error.name,
                               message=error.description if error.code in (400, 404) else None), error.code

    @app.errorhandler(Exception)
    def server_error(error: Exception):
        log.exception("Unhandled error")  # full detail stays in the server log
        return render_template("error.html", code=500, title="Something went wrong",
                               message="The error was logged. Please try again."), 500

    return app


def _startup_housekeeping(app: Flask, db: Database) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    CollectionRepository(db).mark_interrupted(now)
    if not app.config["SEED_SOURCES"]:
        return
    from src.services.source_service import SourceService
    from src.storage.source_repository import SourceRepository

    try:
        config_sources = load_sources()
    except ConfigError as exc:
        log.warning("Skipping source seeding: %s", exc)
        return
    SourceService(SourceRepository(db), fetch=app.config["FETCH_FEED"],
                  allow_private=app.config["ALLOW_PRIVATE_FEEDS"]).seed_from_config(
        config_sources, SettingsRepository(db))
