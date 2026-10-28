# AfricanPulse Oasis

A website for the Black Oasis (BOS) Communications Department. It collects headlines from
public RSS and Atom feeds, stores them in a local database, and lets the team search, filter,
review and mark articles for follow up. It never publishes anything.

Collected items are third party material. They are not fact checked and are not BOS writing.
Always open the original source before using any information.

## What works in this version

* **Overview:** real statistics from the database, latest articles, a Collect news now button
* **Collected News:** search titles and summaries, filter by category, source and status, sort by
  publication or collection date, pagination, article detail page with original link
* **Data Sources:** add, edit, enable or disable, test and remove RSS or Atom feeds
* **Collection Activity:** history of every collection attempt with per source results and errors
* **Settings:** default sort, default category, articles per page, feed timeout
* Editorial status (New, Under Review, Selected for Content, Archived) and BOS notes per article
* Collection runs in a background thread; one failing feed never stops the others
* Duplicates are prevented, so collecting twice never creates second copies

## Install and run on Windows 11 (PowerShell)

1. Extract `AfricanPulse-Oasis.zip`.
2. Open PowerShell inside the extracted `AfricanPulse-Oasis` folder.
3. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

4. Open http://127.0.0.1:5000 in your browser. Stop the site with Ctrl+C.

The database is created automatically on first start. Next time, activate the environment
and run `python run.py`. To use another port: `$env:APOASIS_PORT = "5050"; python run.py`.

If you used the earlier Streamlit version, your existing database is upgraded in place and
nothing is deleted. Its feeds from `config` are copied into the Data Sources
page once.

## Configure news sources

Open **Data Sources**. Add a name and feed URL, press **Test URL first** if you like, then
**Add source**. Use Edit, Disable or Remove to manage existing ones. Saving a feed does not prove
it works, so check the Latest collection column after collecting. Only http and https URLs are
accepted. Feeds on localhost or private networks are refused.

`config` only provides the starting list for a new database. The bundled URLs
were not verified when this project was generated, so replace any that fail.

## Collect news

Press **Collect news now** on Overview or Collection Activity. The page shows progress and
refreshes when the run ends. Results appear under Collected News and Collection Activity.

## Where data is stored

`%LOCALAPPDATA%\AfricanPulseOasis\africanpulse.db`, plus a generated `secret_key` file in the same
folder used to sign sessions. Neither belongs in Git. Override the database with `APOASIS_DB_PATH`
(see `.env.example`). Delete the database file to start fresh.

## Run the tests

```powershell
python -m unittest discover -s tests -t . -v
```

Tests use local sample feeds and need no internet.

## Contribute changes

See `docs` for the branch and pull request workflow. Run the tests before every commit.

## Troubleshooting

* **Python is not recognized.** Try `py --version`. If that fails, install Python 3.10 or newer from
  python.org with "Add python.exe to PATH" ticked, then reopen PowerShell.
* **Activation is blocked.** Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
  and activate again. It affects only that window and needs no administrator rights.
* **Dependency install fails.** Upgrade pip, confirm `(.venv)` shows in the prompt, check your connection.
* **Port in use.** Set another port as shown above.
* **Database errors.** Close other copies of the site, then delete the database file or point
  `APOASIS_DB_PATH` at a folder you can write to.
* **Feeds fail.** Read the error on Data Sources or Collection Activity. Typical causes are no
  internet, a changed feed URL, or a publisher blocking automated requests.

## Security notes

The site listens on 127.0.0.1 only, uses CSRF tokens on every form, escapes all feed content,
uses parameterised SQL, sends a strict Content Security Policy and never shows stack traces.
It has no login, so it is meant for one trusted computer. Before exposing it to a network you
would need authentication, HTTPS, a production server and a security review. This project has
not had an independent security assessment.

## Current limitations

* No login or multiple users
* Categories come from simple keyword rules, not AI, so some articles are Uncategorized or wrong
* Only feed summaries are stored, never full articles
* Feed URL checks block localhost and private IP addresses written directly in the URL, but do
  not resolve DNS names, so they are a safeguard rather than a complete protection
* Collection is manual. Closing the site during a run marks that run as interrupted
* Tested against local sample feeds and a local test server. Not tested against live publisher
  feeds or on a real Windows 11 machine by the generator of this project

More in `docs`, `../docs` and `../docs`.
