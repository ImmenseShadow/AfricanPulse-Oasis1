# Architecture

Pipeline: sources, collection, processing, validation and deduplication, storage, web interface.

## Layers

* `run.py` starts the Flask app from `src/app.py` (application factory).
* `src/routes/` has blueprints for dashboard, articles, sources, activity, calendar and settings. Routes read forms, call services or repositories, and render templates. No SQL.
* `templates/` (Jinja2, autoescaped) and `static/` (CSS with variables, one small JS file).
* `src/services/`
  * `news_service.py` runs a collection and records the run
  * `collection_manager.py` starts a run in a background thread, one at a time
  * `source_service.py` validates and manages sources, tests feeds
  * `settings_service.py` validates preferences
* `src/collectors/rss_collector.py` downloads and parses RSS and Atom. Redirects are followed by hand so every hop is checked by `src/url_safety.py`. Google Alerts feeds use this same collector.
* `src/url_safety.py` public address check (DNS aware), blocked host names, and `mask_url` for showing feed URLs without tokens.
* `src/processors/` cleans entries, builds the dedupe key, categorises by keyword. For `google_alert` sources `article_processor.py` also unwraps `google.com/url` links, reads the publisher and keeps only the snippet.
* `src/storage/` SQLite: `database.py` (schema and migration), plus article, source, collection, calendar and settings repositories.
* `src/security.py` CSRF tokens and response headers. `src/deps.py` builds services per request.
* `../config/settings.py` paths, limits, environment overrides, the starting source list.

## What changed from the Streamlit version

Kept: collector, processor, categorizer, article model, article repository, tests.
Replaced: `app.py` and `src/ui/` (Streamlit) with Flask routes and templates.
Extended: `sources` table gained `enabled` and `created_at`, and new tables `collection_runs`,
`collection_run_sources` and `app_settings` were added. `NewsService` now takes sources from the
database and records each run. Sources moved from a JSON file to the database so they can be managed in the browser.

## Increment 2: Google Alerts

Google Alerts is a **source type** (`sources.source_type`: `rss` or `google_alert`, plus `alert_topic`), not a second
collector. `CollectionManager` passes type, topic and id in `FeedSource`; `NewsService` hands them to the
processor and repository. Schema additions (version 3): `articles.publisher`, `articles.alert_topic`,
`article_sources` (every source that found an article, with type, topic, first and last seen times) and
`collection_run_sources.source_id, source_type, started_at, finished_at`.

Decisions:

* One dedupe key (hash of the normalised original URL) for every source. Google redirect wrappers are unwrapped by
  parsing the link, never by requesting it.
* When an alert finds a stored article the record is preserved; only a source reference, last seen time and a missing
  publisher or topic are added. A normal RSS rediscovery still refreshes metadata as before.
* `articles.source` stays the name of the source that first stored the article; `article_sources` holds the full list.
* SSRF: save time checks literal addresses and blocked names; fetch time resolves the host and checks every address
  on the first request and on each redirect (at most 5). Responses are size limited and parsed with defusedxml.
* Tokens: feed URLs are never put in collector errors, run history or log lines (only exception type names are logged),
  and the sources list shows `mask_url` output.
* Email delivery of alerts (Gmail OAuth, inbox processing) is deliberately not implemented.

## Database migration

`Database.initialize()` creates missing tables, then adds missing columns to old tables and sets
`PRAGMA user_version = 4` (existing articles get a first `article_sources` row; calendar events and schedules use the additive `calendar_items` table). It never drops or rewrites data. `news_sources.json` seeds the database
once (tracked by an `app_settings` flag) so a source the user deletes does not reappear.

`calendar_items` stores both `event` and `schedule` kinds with local start/end times, all-day flag,
category, colour label, schedule status, notes, optional reminder interval and creation/update times.
Reminder intervals are preferences only; there is no delivery worker. Recurrence is not implemented.

## Key decisions to preserve

* Dedupe by SHA 256 of the normalised URL. Repeat sightings refresh metadata but keep first collection time, status and notes.
* Only links and short summaries are stored. Articles are not scraped.
* Collection runs off the request thread. A lock and the database allow one run at a time. Runs left as running at startup are closed as interrupted.
* Per source errors are contained and recorded. Error text is sanitised so feed URLs and tokens do not reach the UI or logs.
* Deleting a source never deletes its articles. Renaming one renames them.
* CSP forbids inline scripts and styles, so templates use classes and `static/js/app.js` only.
* Future modules (culture, holidays, events) should add their own collectors, processors and tables beside the news ones, not modify them.
