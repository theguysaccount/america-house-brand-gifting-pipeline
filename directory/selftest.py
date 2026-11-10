"""Self-test of the live site. Exit 1 if anything a visitor would notice is broken or stale.

  python3 -m directory.selftest [--site-url URL] [--max-age-days 16]

Checks that every page in the live sitemap answers 200 and carries its as-of date, that the search
data loads and is recent, and that the share image, feed, downloads and key file resolve. It only
reads this project's own site: it never touches a listed brand's page (the weekly crawl does that).
Prints `stale=true` on its own line when the listings are older than the limit, so the workflow can
start a refresh.
"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import timedelta

from .common import ROOT, load_config, now_utc, parse_iso, site_url


def fetch(url, ua):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code, b""
        except Exception:
            pass
    return 0, b""


def main(argv=None):
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default=site_url(cfg))
    ap.add_argument("--max-age-days", type=float, default=16)
    a = ap.parse_args(argv)
    base, ua = a.site_url.rstrip("/"), cfg["crawler"]["user_agent"]
    indexable = cfg.get("indexable", True) and os.environ.get("SITE_INDEXABLE", "").lower() != "false"
    problems, stale = [], False

    code, home = fetch(base + "/", ua)
    if code != 200:
        print(f"FAIL home page answered {code}")
        return 1
    code, body = fetch(base + "/assets/programs.json", ua)
    try:
        data = json.loads(body)
        asof = parse_iso(data["asof"])
        n = len(data["programs"])
    except Exception:
        data, asof, n = None, None, 0
        problems.append(f"assets/programs.json did not load (status {code})")
    if data is not None:
        if n < cfg["min_listings_to_publish"]:
            problems.append(f"only {n} listings on the live site")
        age = now_utc() - asof if asof else None
        if age is None or age > timedelta(days=a.max_age_days):
            stale = True
            problems.append(f"listings were last checked {data.get('asof')} (limit {a.max_age_days:g} days)")
    code, urls_txt = fetch(base + "/urls.txt", ua)
    urls = [u for u in urls_txt.decode("utf-8", "replace").split() if u.startswith("http")] if code == 200 else []
    if indexable:
        code, sm = fetch(base + "/sitemap.xml", ua)
        sm_urls = re.findall(r"<loc>([^<]+)</loc>", sm.decode("utf-8", "replace")) if code == 200 else []
        if not sm_urls:
            problems.append(f"sitemap.xml missing or empty (status {code})")
        urls = sm_urls or urls
        code, robots = fetch(base + "/robots.txt", ua)
        if code != 200 or b"Sitemap:" not in robots:
            problems.append("robots.txt missing or without a Sitemap line")
    else:
        if b'content="noindex' not in home:
            problems.append("staged site is missing its noindex tag")
    with open(os.path.join(ROOT, "config", "indexnow-key.txt"), encoding="utf-8") as f:
        key = f.read().strip()
    extra = [base + p for p in ("/feed.xml", "/og/home.png", "/data/programs.csv", "/data/programs.json", "/static/style.css",
                                "/static/app.js", "/embed/widget/", f"/{key}.txt", "/guides/", "/methodology/")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda u: (u, fetch(u, ua)), list(dict.fromkeys(urls + extra))))
    for u, (c, body) in results:
        if c != 200:
            problems.append(f"{u} answered {c}")
        elif u in urls and b"<time datetime=" not in body:
            problems.append(f"{u} carries no as-of date")
    for p in problems[:40]:
        print("FAIL", p)
    print(f"selftest: {len(results)} URLs checked, {n} listings, {len(problems)} problems")
    print(f"stale={'true' if stale else 'false'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
