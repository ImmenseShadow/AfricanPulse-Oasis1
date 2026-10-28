"""Validated application preferences, persisted in the database."""
from __future__ import annotations

from src.models.article import CATEGORIES
from src.storage.settings_repository import SettingsRepository

SORT_CHOICES = {"published_at": "Publication date", "collected_at": "Collection date"}
PAGE_SIZES = (10, 25, 50)
TIMEOUT_RANGE = (3, 60)

DEFAULTS = {
    "default_sort": "published_at",
    "default_category": "",  # empty means all categories
    "request_timeout": 15,
    "page_size": 25,
}


class SettingsError(ValueError):
    pass


class SettingsService:
    def __init__(self, repo: SettingsRepository):
        self.repo = repo

    def get(self) -> dict:
        """Current settings. Anything stored but invalid falls back to its default."""
        stored = self.repo.get_all()
        try:
            return self._validate({**DEFAULTS, **stored})
        except SettingsError:
            result = dict(DEFAULTS)
            for key in DEFAULTS:
                try:
                    result.update(self._validate({**DEFAULTS, key: stored.get(key, DEFAULTS[key])}, only=key))
                except SettingsError:
                    pass
            return result

    def save(self, form: dict) -> dict:
        values = self._validate({**DEFAULTS, **form})
        self.repo.set_many({k: str(v) for k, v in values.items()})
        return values

    @staticmethod
    def _validate(raw: dict, only: str | None = None) -> dict:
        out: dict = {}
        sort = str(raw["default_sort"])
        if sort not in SORT_CHOICES:
            raise SettingsError("Choose a valid default sort order.")
        out["default_sort"] = sort
        category = str(raw["default_category"])
        if category and category not in CATEGORIES:
            raise SettingsError("Choose a valid default category.")
        out["default_category"] = category
        try:
            timeout = int(raw["request_timeout"])
            size = int(raw["page_size"])
        except (TypeError, ValueError):
            raise SettingsError("Timeout and page size must be whole numbers.")
        if not TIMEOUT_RANGE[0] <= timeout <= TIMEOUT_RANGE[1]:
            raise SettingsError(f"Timeout must be between {TIMEOUT_RANGE[0]} and {TIMEOUT_RANGE[1]} seconds.")
        if size not in PAGE_SIZES:
            raise SettingsError("Choose a valid page size.")
        out["request_timeout"], out["page_size"] = timeout, size
        return {only: out[only]} if only else out
