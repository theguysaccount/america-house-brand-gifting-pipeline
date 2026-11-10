# Creator Program Directory

**Live:** https://theguysaccount.github.io/america-house-brand-gifting-pipeline/

A free, public directory of the ambassador, creator, affiliate and gifting application pages that brands publish on their
own websites. Every listing links to the brand's own page and shows the date a crawler last read it. Creators apply
themselves, on the brand's site. This project never submits, fills in or automates an application.

No server, no accounts, no dependencies: Python's standard library builds a static site from one JSON file, and GitHub
Actions re-checks every listing each week.

## How it works

```
data/programs.json  --build-->  _site/  --GitHub Pages-->  the live site
        ^
        |  weekly: directory.verify re-reads each listed page (robots.txt first) and updates the file
```

| Path | What it is |
|---|---|
| `directory/fetch.py`, `robots.py` | The polite HTTP client: robots.txt (RFC 9309) and Crawl-delay, per-site and overall pacing, public addresses only, no retries of refusals |
| `directory/classify.py` | Reads a page and decides whether it is an open program page, how you apply, and what it mentions |
| `directory/verify.py` | The weekly check: updates `data/programs.json`, `dropped.json`, `changes.json`, `status.json` |
| `directory/build.py`, `og.py` | Static site, downloads, sitemap, feed, share cards |
| `directory/guard.py`, `e2e.py`, `selftest.py` | Pre-deploy checks, headless-Chrome check of the search, live-site check |
| `content/guides/` | The guides, in Markdown |
| `config/site.json` | Name, crawler settings, safety thresholds |
| `config/exclude.txt` | Sites never to list or fetch (create it when needed: one domain per line) |
| `data/candidates.txt` | Queue of new pages to try at the next check |

## Run it

```sh
python3 -m unittest discover -s tests -t .      # tests (Python 3.9+; no installs)
python3 -m directory.build --site _site         # build the site from data/
python3 -m directory.og --site _site            # share cards (needs Chrome; falls back to a default card)
python3 -m directory.guard _site                # the checks every deploy must pass
python3 -m directory.e2e _site                  # search, filters and embed in headless Chrome
python3 -m directory.verify                     # re-check listings that are due (talks to the public web)
python3 -m directory.verify --candidates urls.txt   # also try new pages
python3 scripts/screens.py                      # screenshots into docs/screens/
```

To preview locally, serve a folder that contains `_site` under the name `america-house-brand-gifting-pipeline`
(links use the same base path as GitHub Pages), or build with `SITE_URL=http://localhost:8000`.

## Deploy

Pushing to `main` runs **Verify and deploy** (`.github/workflows/refresh.yml`): tests, build, guard, browser check, then
GitHub Pages. Scheduled runs also re-check the listings first. See [OPERATIONS.md](OPERATIONS.md) for every job, how each
fails safely, and the settings a human can change.

## About the crawler (for site owners)

- User-Agent: `CreatorProgramDirectoryBot/1.0 (+https://github.com/theguysaccount/america-house-brand-gifting-pipeline)`
- It reads your `robots.txt` first and obeys it, including `Crawl-delay`.
- It requests one page per listing about once a week (plus, on Shopify stores, the public `/meta.json` summary about once
  a month), with plain `GET` requests. No cookies, no form posts, no scripts, no logins.
- It stops at any bot check, `401`, `403` or `429` and does not try again in that run.
- It lists a page only if the page itself names a creator, ambassador, affiliate or gifting program and shows a way to
  apply. It skips pages marked `noindex`.

**To remove your page,** add this to your `robots.txt`. The listing disappears at the next weekly check:

```
User-agent: CreatorProgramDirectoryBot
Disallow: /
```

A `noindex` robots meta tag on the page works too. You can also
[open an issue](https://github.com/theguysaccount/america-house-brand-gifting-pipeline/issues/new/choose).

## Licence

Code: MIT. Data (`data/`, and the CSV/JSON downloads): CC0 1.0. Brand names belong to their owners; a listing is not an
endorsement by or of any brand. More: [PRODUCT.md](PRODUCT.md), [DECISIONS.md](DECISIONS.md), [STATE.md](STATE.md),
[LAUNCH.md](LAUNCH.md).
