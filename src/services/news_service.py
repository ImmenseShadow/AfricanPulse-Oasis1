"""Runs a collection: fetch each enabled source, process, store, and record the run."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from config.settings import FeedSource
from src.collectors.rss_collector import CollectorError, fetch_feed
from src.processors.article_processor import process_entries
from src.storage.article_repository import ArticleRepository
from src.storage.collection_repository import CollectionRepository
from src.storage.database import Database
from src.storage.source_repository import SourceRepository

log = logging.getLogger(__name__)


@dataclass
class SourceResult:
    source_name: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0     # already stored, metadata refreshed
    duplicates: int = 0  # repeated inside the same feed
    invalid: int = 0     # missing title or usable link
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class NewsService:
    def __init__(
        self,
        db: Database,
        fetch: Callable[[str], list[dict]] = fetch_feed,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.articles = ArticleRepository(db)
        self.sources = SourceRepository(db)
        self.runs = CollectionRepository(db)
        self._fetch = fetch
        self._now = now

    def _stamp(self) -> str:
        return self._now().isoformat(timespec="seconds")

    def collect(
        self, sources: Iterable[FeedSource], run_id: Optional[int] = None, trigger: str = "manual"
    ) -> list[SourceResult]:
        """Collect every enabled source. One failing feed never stops the others."""
        enabled = [s for s in sources if s.enabled]
        if run_id is None:
            run_id = self.runs.start_run(self._stamp(), trigger, len(enabled))
        results: list[SourceResult] = []
        for source in enabled:
            result = self._collect_one(source)
            self.runs.add_source_result(run_id, result)
            results.append(result)
        self.runs.finish_run(run_id, self._stamp(), results)
        return results

    def _collect_one(self, source: FeedSource) -> SourceResult:
        when = self._now()
        result = SourceResult(source.name)
        try:
            raw_entries = self._fetch(source.feed_url)
            result.fetched = len(raw_entries)
            articles, skipped = process_entries(raw_entries, source.name, when)
            result.duplicates = sum(1 for r in skipped if r.startswith("duplicate"))
            result.invalid = len(skipped) - result.duplicates
            for article in articles:
                if self.articles.upsert(article) == "inserted":
                    result.inserted += 1
                else:
                    result.updated += 1
        except CollectorError as exc:
            result.error = str(exc)
        except Exception:  # keep the run alive; details go to the server log only
            log.exception("Unexpected error while collecting %s", source.name)
            result.error = "Unexpected error while processing this feed."
        self.sources.record_result(source.feed_url, when.isoformat(timespec="seconds"), result.error)
        return result
