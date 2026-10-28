"""Accessors that build repositories and services for the current request."""
from __future__ import annotations

from flask import current_app

from src.services.settings_service import SettingsService
from src.services.source_service import SourceService
from src.storage.article_repository import ArticleRepository
from src.storage.collection_repository import CollectionRepository
from src.storage.settings_repository import SettingsRepository
from src.storage.source_repository import SourceRepository


def db():
    return current_app.extensions["oasis_db"]


def articles() -> ArticleRepository:
    return ArticleRepository(db())


def runs() -> CollectionRepository:
    return CollectionRepository(db())


def source_repo() -> SourceRepository:
    return SourceRepository(db())


def settings_service() -> SettingsService:
    return SettingsService(SettingsRepository(db()))


def source_service() -> SourceService:
    return SourceService(
        source_repo(),
        fetch=current_app.config["FETCH_FEED"],
        allow_private=current_app.config["ALLOW_PRIVATE_FEEDS"],
        timeout=settings_service().get()["request_timeout"],
    )


def collection_manager():
    return current_app.extensions["collection_manager"]
