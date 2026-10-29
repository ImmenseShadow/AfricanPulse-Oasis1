# Developer handoff

## Implemented
Flask website with Overview, Collected News, Data Sources, Collection Activity and Settings, over the Phase 1 collector, processor and storage code.
Increment 2 added Google Alerts RSS feeds as a source type on the same pipeline (see `ARCHITECTURE.md`, "Increment 2: Google Alerts").

## Where things are
See the layer list in `ARCHITECTURE.md`.

## Data flow
Sources table, then `CollectionManager.start` (background thread), then `NewsService.collect`, then `fetch_feed` (address checks in `url_safety.py`), `process_entries` (Google link unwrapping for alert sources), `ArticleRepository.upsert` (also records the source reference in `article_sources`), with each source result written to `collection_run_sources` and the run summary to `collection_runs`. Pages read through repositories.

## Test
`python -m unittest discover -s tests -t . -v` (123 tests, offline). `tests/test_routes.py` uses Flask's test client with a fake feed fetcher; `tests/test_google_alerts.py` covers Increment 2.

## Add a source
Data Sources page, or a row in the `sources` table.

## Preserve
Layer separation, URL based deduplication, sanitised error text (no feed URLs or tokens in messages, history or logs), address checks on every request and redirect, CSRF on every POST, no inline scripts or styles, deleting sources keeps articles, never auto publish, never imply collected items are verified.

## Next increment
Category rule improvements and tags, export of selected articles, optional scheduled collection. Extend this codebase rather than replacing it.
