# Architecture

Pipeline: sources, collection, processing, validation and deduplication, storage, web interface.

## Layers

* `run.py` starts the Flask app from `src/app.py` (application factory).
* `src/routes/` has one blueprint per page: dashboard, articles, sources, activity, settings. Routes read forms, call services or repositories, and render templates. No SQL.
* `templates/` (Jinja2, autoescaped) and `static/` (CSS with variables, one small JS file).
* `src/services/`
  * `news_service.py` runs a collection and records the run
  * `collection_manager.py` starts a run in a background thread, one at a time
  * `source_service.py` validates and manages sources, tests feeds
  * `settings_service.py` validates preferences
* `src/collectors/rss_collector.py` downloads and parses RSS and Atom (unchanged from Phase 1 except safer error text).
* `src/processors/` cleans entries, builds the dedupe key, categorises by keyword (unchanged).
* `src/storage/` SQLite: `database.py` (schema and migration), plus article, source, collection and settings repositories.
* `src/security.py` CSRF tokens and response headers. `src/deps.py` builds services per request.
* `../config/settings.py` paths, limits, environment overrides, the starting source list.

## What changed from the Streamlit version

Kept: collector, processor, categorizer, article model, article repository, tests.
Replaced: `app.py` and `src/ui/` (Streamlit) with Flask routes and templates.
Extended: `sources` table gained `enabled` and `created_at`, and new tables `collection_runs`,
`collection_run_sources` and `app_settings` were added. `NewsService` now takes sources from the
database and records each run. Sources moved from a JSON file to the database so they can be managed in the browser.

## Database migration

`Database.initialize()` creates missing tables, then adds missing columns to old tables and sets
`PRAGMA user_version = 2`. It never drops or rewrites data. `news_sources.json` seeds the database
once (tracked by an `app_settings` flag) so a source the user deletes does not reappear.

## Key decisions to preserve

* Dedupe by SHA 256 of the normalised URL. Repeat sightings refresh metadata but keep first collection time, status and notes.
* Only links and short summaries are stored. Articles are not scraped.
* Collection runs off the request thread. A lock and the database allow one run at a time. Runs left as running at startup are closed as interrupted.
* Per source errors are contained and recorded. Error text is sanitised so feed URLs and tokens do not reach the UI or logs.
* Deleting a source never deletes its articles. Renaming one renames them.
* CSP forbids inline scripts and styles, so templates use classes and `static/js/app.js` only.
* Future modules (culture, holidays, events) should add their own collectors, processors and tables beside the news ones, not modify them.
