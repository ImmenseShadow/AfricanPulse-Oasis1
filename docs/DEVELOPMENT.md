# Development guide

## Setup and tests

Follow the README install steps, then `python -m unittest discover -s tests -t . -v`.

## Add a news source

In the website: Data Sources, then Add source. In code: nothing to change.
To change the starting list for brand new databases, edit `../config/news_sources.json`.

## Add a category rule

Add keywords to `RULES` in `src/processors/categorizer.py` (new categories also go in `CATEGORIES` in `src/models/article.py`), then add a test.

## Add a page

Create a blueprint in `src/routes/`, register it in `src/app.py`, add a template that extends `base.html`, and add forms with `{{ csrf_input() }}`. Do not add inline scripts or styles.

## Change the schema

Add the table or column to `SCHEMA` and a guarded step in `Database._migrate`, bump `SCHEMA_VERSION`, and add a migration test using an old style database.

## Git and GitHub

```powershell
git init
git add .
git commit -m "AfricanPulse Oasis website"
git branch -M main
```

Create an empty repository on github.com (no README or license), then:

```powershell
git remote add origin https://github.com/YOUR-ACCOUNT/AfricanPulse-Oasis.git
git push -u origin main
```

GitHub asks you to sign in through the browser the first time. The app needs no token.
Replace the copyright placeholder in `LICENSE` before publishing.

Daily flow: `git switch -c feature/short-name`, change, run tests, commit, push, open a pull request, merge when the Tests workflow is green.
