"""Starts collection runs in a background thread so the website stays responsive."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from functools import partial
from typing import Callable, Optional

from config.settings import FeedSource
from src.services.news_service import NewsService
from src.storage.collection_repository import CollectionRepository
from src.storage.database import Database
from src.storage.source_repository import SourceRepository

log = logging.getLogger(__name__)


class CollectionManager:
    """Allows one run at a time. With sync=True (used by tests) the run finishes before start() returns."""

    def __init__(self, db: Database, fetch: Callable[..., list[dict]], timeout_getter: Callable[[], int], sync: bool = False):
        self.db = db
        self._fetch = fetch
        self._timeout = timeout_getter
        self.sync = sync
        self.runs = CollectionRepository(db)
        self._lock = threading.Lock()

    def start(self, trigger: str = "manual") -> tuple[Optional[int], Optional[str]]:
        """Returns (run_id, None) on success or (None, reason) when nothing was started."""
        with self._lock:
            if self.runs.running_run():
                return None, "A collection run is already in progress."
            rows = [r for r in SourceRepository(self.db).list_sources() if r["enabled"]]
            if not rows:
                return None, "There are no enabled sources. Add or enable one on the Data Sources page."
            sources = [FeedSource(r["name"], r["feed_url"], True) for r in rows]
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            run_id = self.runs.start_run(now, trigger, len(sources))
            fetch = partial(self._fetch, timeout=self._timeout())
            if self.sync:
                self._execute(run_id, sources, fetch)
            else:
                threading.Thread(target=self._execute, args=(run_id, sources, fetch), daemon=True).start()
        return run_id, None

    def _execute(self, run_id: int, sources: list[FeedSource], fetch: Callable[[str], list[dict]]) -> None:
        try:
            NewsService(self.db, fetch=fetch).collect(sources, run_id=run_id)
        except Exception:
            log.exception("Collection run %s failed", run_id)
            self.runs.fail_run(
                run_id, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "Unexpected internal error. See the server log.",
            )
