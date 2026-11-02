# Developer handoff

## Implemented
Flask website with Overview, Collected News, Data Sources, Collection Activity and Settings, over the Phase 1 collector, processor and storage code.
Increment 2 added Google Alerts RSS feeds as a source type on the same pipeline (see `ARCHITECTURE.md`, "Increment 2: Google Alerts").
Increment 3 groups Dashboard and News navigation and adds the database-backed Calendar for one-time events and schedules (month/week/day/agenda, editing, deletion and schedule status).

## Where things are
See the layer list in `ARCHITECTURE.md`. Calendar storage lives in `src/storage/calendar_repository.py`; calendar input validation and views are in `src/routes/calendar.py`.

## Data flow
Sources table, then `CollectionManager.start` (background thread), then `NewsService.collect`, then `fetch_feed` (address checks in `url_safety.py`), `process_entries` (Google link unwrapping for alert sources), `ArticleRepository.upsert` (also records the source reference in `article_sources`), with each source result written to `collection_run_sources` and the run summary to `collection_runs`. Pages read through repositories.

## Test
`python -m unittest discover -s tests -t . -v` (offline). `tests/test_routes.py` uses Flask's test client with a fake feed fetcher; `tests/test_google_alerts.py` covers Increment 2; `tests/test_calendar.py` covers calendar workflows.

## Add a source
Data Sources page, or a row in the `sources` table.

## Preserve
Layer separation, URL based deduplication, sanitised error text (no feed URLs or tokens in messages, history or logs), address checks on every request and redirect, CSRF on every POST, no inline scripts or styles, deleting sources keeps articles, never auto publish, never imply collected items are verified.

## Next increment
Reminder delivery infrastructure and recurring schedules remain future work; continue with category rules, tags and selected-article export. Extend this codebase rather than replacing it.
