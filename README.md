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
* **Data Sources:** add, edit, enable or disable, test and remove RSS, Atom or Google Alerts feeds
* **Collection Activity:** history of every collection attempt with per source results and errors
* **Settings:** default sort, default category, articles per page, feed timeout
* Editorial status (New, Under Review, Selected for Content, Archived) and BOS notes per article
* Collection runs in a background thread; one failing feed never stops the others
* Duplicates are prevented, so collecting twice never creates second copies
* **Increment 2: Google Alerts.** A Google Alerts RSS feed is a new source type that uses the same
  collector, processor, database and activity history as every other source (see below)

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

## Google Alerts (Increment 2)

Google Alerts helps BOS Communications discover articles about topics it follows. This increment
reads an alert's **RSS feed**. It does not read alert emails, and it never signs in to Google.

**1. Create an alert.** Go to https://www.google.com/alerts, sign in with a Google account, type the
search terms (for example `African education scholarships`) and press **Show options**.

**2. Choose RSS delivery, when it is offered.** Under **Deliver to**, pick **RSS feed** if the option
appears, then **Create Alert**. Google does not offer RSS for every account or configuration, and
it may change or withdraw the feature. If you do not see it, this increment cannot collect that alert.

**3. Get the feed URL.** Open the alert list (the pencil icon, "Manage your alerts"). Next to an alert
with RSS delivery there is an RSS icon. Right click it and choose **Copy link address**. Do not rely on a
fixed URL pattern: copy whatever address Google gives you.

**4. Register it.** In AfricanPulse Oasis open **Data Sources** and fill in:

* **Name:** a description such as `Alert: African education`
* **Source type:** `Google Alerts feed`
* **Alert topic:** the search terms the alert follows (required for this type)
* **Feed URL:** the copied address

**5. Test it.** Press **Test URL first** before saving, or **Test** on a saved source. The test makes a real
request and reports success only when the address answered and the response was a readable feed.

**6. Collect and view.** Press **Collect news now**. Entries appear under **Collected News** (with an
`Alert: topic` label) and the run appears under **Collection Activity**, with the source type, start and
finish time, entries found, new articles and duplicates for that alert.

You can edit, disable (Disable / Enable) or remove an alert source at any time. Removing a source keeps
the articles already collected.

### What is stored for each alert entry

Title, original article link, publisher (only when the alert names one or the original link shows a site
name; Google is never assumed to be the publisher), publication date and summary when the feed gives
them, the alert topic, the source and the collection time. Missing values are left empty, never invented.
Google wraps links as `google.com/url?...&url=<article>`. The article address is read from that link
without requesting it, so the original link is kept. Full articles are never downloaded.

### How deduplication works

Every entry is reduced to a normalised article URL (tracking parameters, fragments and trailing slashes
removed) and hashed. If an alert finds an article that another feed already collected, the existing record
is kept (its title, summary, category, status and notes are not overwritten) and the alert is added to the
article's **Found by** list on the article page. If an alert finds an article first and an RSS feed finds it
later, there is still one record. Titles are never used to merge articles, so two different articles with
similar headlines stay separate. Collecting repeatedly never creates duplicates.

### Safety of feed URLs

Only `http` and `https` are accepted. Before every request, including every redirect, the host name is resolved
and the request is refused if any address is localhost, a private network, link-local or a cloud metadata
address. Requests have a timeout and a size limit. Feed content is parsed as data and never executed. Alert
URLs often contain a private token, so the Data Sources list shows a shortened form, and URLs are left out of
error messages, collection history and logs. The edit page does show the full address because you must be
able to change it.

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
* **Google Alert: "server answered HTTP 404" or "403".** The copied address is wrong, incomplete or the alert
  was deleted. Copy the RSS link again from the alert list and edit the source.
* **Google Alert: "Response is not an RSS or Atom feed" or "not valid XML".** The address returned a web page,
  often a Google sign in page. Use the RSS icon link from the alert list, not the browser address bar.
* **Google Alert: "Alert topic" is required.** Enter the search terms the alert follows.
* **"Feeds on localhost or private network addresses are not allowed".** The address, or a redirect it
  followed, points at your own computer or a private network. This protection is deliberate.
* **"The feed host name could not be resolved".** No internet or a mistyped host name.
* **An alert produced no new articles.** Alerts only list items Google has found since it last updated the
  feed; check Collection Activity for the entries found and duplicates skipped counts.

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
* Feed URLs are checked when saved (literal addresses and internal host names) and again at request time
  (host name resolution and every redirect). This is a safeguard for a local application, not a complete
  protection
* Google Alerts: RSS delivery is not available for every alert or account, Google can change or remove it,
  and feeds only contain recent items. Alert email delivery (Gmail) is **not** supported and is a possible
  future enhancement. Publisher names come from the alert text or the link's site name, so they can be rough
* The private network check resolves the host name before connecting; a host that changes its answer
  between the check and the connection (DNS rebinding) is not fully covered by this local application
* Collection is manual. Closing the site during a run marks that run as interrupted
* Tested against local sample feeds and a local test server. Not tested against live publisher
  feeds or on a real Windows 11 machine by the generator of this project

More in `docs` (architecture, development, roadmap and handoff notes).
