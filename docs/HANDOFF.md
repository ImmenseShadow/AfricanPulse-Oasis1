# Developer handoff

## Implemented
Flask website with Overview, Collected News, Data Sources, Collection Activity and Settings, over the Phase 1 collector, processor and storage code.

## Where things are
See the layer list in `ARCHITECTURE.md`.

## Data flow
Sources table, then `CollectionManager.start` (background thread), then `NewsService.collect`, then `fetch_feed`, `process_entries`, `ArticleRepository.upsert`, with each source result written to `collection_run_sources` and the run summary to `collection_runs`. Pages read through repositories.

## Test
`python -m unittest discover -s tests -t . -v` (79 tests, offline). `tests/test_routes.py` uses Flask's test client with a fake feed fetcher.

## Add a source
Data Sources page, or a row in the `sources` table.

## Preserve
Layer separation, URL based deduplication, sanitised error text, CSRF on every POST, no inline scripts or styles, deleting sources keeps articles, never auto publish, never imply collected items are verified.

## Next increment
Category rule improvements and tags, export of selected articles, optional scheduled collection. Extend this codebase rather than replacing it.
