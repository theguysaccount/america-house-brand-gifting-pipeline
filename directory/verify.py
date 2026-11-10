"""Re-check every listed program page on the public web and update data/programs.json.

  python3 -m directory.verify                      # weekly job: re-check listings not checked recently
  python3 -m directory.verify --all                # re-check everything now
  python3 -m directory.verify --candidates FILE    # also try new public URLs (one per line)
  python3 -m directory.verify --check-fresh        # exit 1 if the data has not been refreshed in time

What a check does, per page: read the site's robots.txt and obey it; fetch the page once with an
honest User-Agent; read what the page says (directory.classify); record the result. Nothing is
submitted anywhere and no form is filled in.

Fail-safe rules:
- A page that is gone, no longer describes a program, says applications are closed, asks not to
  be indexed, or is disallowed by robots.txt leaves the directory in this run.
- A page that could not be read (bot check, 403, 429, timeout, server error) stays listed with its
  older "last verified" date for one more run, then leaves until it can be read again.
- If a run would remove an implausibly large share of the directory (a broken runner network, a
  bad rule), nothing is written and the job fails, so the last good data and site stay in place.
"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from . import classify
from .common import DATA, iso, load_config, now_utc, parse_iso, read_json, site_key, slugify, write_json
from .fetch import Client, FetchError

PROGRAMS = os.path.join(DATA, "programs.json")
QUEUE = os.path.join(DATA, "candidates.txt")          # public queue of new pages to try, one URL per line
DROPPED = os.path.join(DATA, "dropped.json")
CHANGES = os.path.join(DATA, "changes.json")
STATUS = os.path.join(DATA, "status.json")
EXCLUDE = os.path.join(os.path.dirname(DATA), "config", "exclude.txt")

# Markets shown in the "store ships to" filter. A store's full list can run past 200 countries.
MARKETS = ["US", "CA", "GB", "AU", "NZ", "IE", "DE", "FR", "NL", "ES", "IT", "SE", "IN", "SG", "AE", "ZA", "JP", "MX", "BR"]
SHOP_RECHECK = timedelta(days=28)

SOFT = {"blocked", "error"}                       # could not read the page: try again next run
HARD = {"gone", "not_program", "closed", "noindex", "robots", "moved"}
MAX_FAILS = 6                                     # consecutive failed checks before an entry is retired
MAX_FRESH_AGE = timedelta(days=16)

def canonical(url):
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower()
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit(("https", host, path, p.query if len(p.query) < 80 else "", ""))


def load_excluded():
    try:
        with open(EXCLUDE, encoding="utf-8") as f:
            return {line.split("#")[0].strip().lower() for line in f if line.split("#")[0].strip()}
    except FileNotFoundError:
        return set()


def check_url(client, url):
    """One robots-checked look at one page. Returns {'status': ..., plus the page's details when live}."""
    try:
        r = client.get(url)
    except FetchError as e:
        if e.kind == "robots_disallowed":
            return {"status": "blocked" if "unavailable" in e.detail else "robots", "note": e.detail[:120]}
        if e.kind in ("bad_url", "private_address"):
            return {"status": "gone", "note": e.kind}
        return {"status": "error", "note": e.kind}
    final = canonical(r.url)
    if site_key(urlsplit(final).hostname or "") != site_key(urlsplit(url).hostname or ""):
        return {"status": "moved", "note": "redirects to another site"}
    if r.status in (404, 410):
        return {"status": "gone", "note": f"HTTP {r.status}"}
    if r.status in (401, 403, 429, 503) or r.status >= 500:
        return {"status": "blocked" if r.status in (401, 403, 429) else "error", "note": f"HTTP {r.status}"}
    if r.status != 200:
        return {"status": "error", "note": f"HTTP {r.status}"}
    if "html" not in r.headers.get("content-type", "text/html").lower():
        return {"status": "not_program", "note": "not a web page"}
    info = classify.analyse(r.text(), final)
    if info["challenge"]:
        return {"status": "blocked", "note": info["reason"]}
    if info["noindex"]:
        return {"status": "noindex", "note": info["reason"]}
    if info["closed"]:
        return {"status": "closed", "note": info["reason"]}
    if not info["is_program"]:
        return {"status": "not_program", "note": info["reason"]}
    return {"status": "live", "note": "", "info": info, "final_url": final}


def shop_meta(client, page_url):
    """Read a store's own public summary, /meta.json, which Shopify stores publish: name, country and
    the countries the store ships to. Robots-checked like every other request.

    Returns a dict, {} when the site publishes no such file, or None when it could not be read now.
    """
    host = urlsplit(page_url).hostname
    try:
        r = client.get(f"https://{host}/meta.json")
    except FetchError as e:
        return {} if e.kind == "robots_disallowed" else None
    if r.status in (404, 410) or (r.status == 200 and "json" not in r.headers.get("content-type", "").lower()):
        return {}
    if r.status != 200:
        return None
    try:
        d = json.loads(r.text())
    except ValueError:
        return {}
    if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not d["name"].strip():
        return {}
    ships = [c for c in (d.get("ships_to_countries") or []) if isinstance(c, str)]
    world = "*" in ships
    named = [c for c in ships if c != "*"]
    return {"name": " ".join(d["name"].split())[:60], "country": str(d.get("country") or "")[:2].upper(),
            "description": str(d.get("description") or "")[:600],
            "ships_to": [c for c in MARKETS if world or c in named], "ships_world": world, "ships_count": len(named)}


def shown(entry, strikes):
    """Is this entry published? Live, or unreadable for fewer than `strikes` runs in a row."""
    if not entry.get("verified_at"):
        return False
    if entry.get("status") == "live":
        return True
    return entry.get("status") in SOFT and entry.get("fails", 0) < strikes


def apply_result(entry, res, now):
    entry["checked_at"] = iso(now)
    entry["status"] = res["status"]
    entry["note"] = res.get("note", "")
    if res["status"] == "live":
        info = res["info"]
        host = urlsplit(res["final_url"]).hostname
        entry.update(url=res["final_url"], host=host, title=info["title"], types=info["types"], apply=info["apply"],
                     facts=info["facts"], lang=info["lang"], verified_at=iso(now), fails=0)
        shop = res.get("shop")
        if shop is not None:                      # the store summary was read (or found absent) in this run
            entry["shop_checked"] = iso(now)
            if shop:
                entry["shop"] = {k: shop[k] for k in ("name", "country", "ships_to", "ships_world", "ships_count")}
                entry["category"] = classify.categorize(shop["name"], host, info["title"], shop["description"])
                entry["category_from"] = "store"
            else:
                entry.pop("shop", None)
                entry["category_from"] = "page"
        store = entry.get("shop") or {}
        entry["brand"] = store.get("name") or info["brand"]
        if entry.get("category_from") != "store" or not entry.get("category"):
            entry["category"], entry["category_from"] = info["category"], "page"
        entry["region"] = classify.COUNTRY.get(store.get("country", ""), "") or info["region"]
        entry.setdefault("first_seen", iso(now)[:10])
    else:
        entry["fails"] = entry.get("fails", 0) + 1
    return entry


def assign_ids(entries):
    """Stable, readable ids: the brand slug, with the host added only when two brands collide."""
    taken = {e["id"] for e in entries if e.get("id")}
    for e in entries:
        if e.get("id") or not e.get("brand"):
            continue
        base = slugify(e["brand"]) or slugify(e["host"])
        cand = base
        if cand in taken:
            cand = f"{base}-{slugify(site_key(e['host']).split('.')[0])}"
        n = 2
        while cand in taken:
            cand = f"{base}-{n}"
            n += 1
        e["id"] = cand
        taken.add(cand)


def read_queue():
    try:
        with open(QUEUE, encoding="utf-8") as f:
            return [line.strip() for line in f if re.match(r"\s*https?://", line)]
    except FileNotFoundError:
        return []


def run(candidates=None, check_all=False, max_seconds=None, limit=None, private_log=None, now=None, client=None,
        quiet=False):
    cfg = load_config()
    c = cfg["crawler"]
    now = now or now_utc()
    started = time.monotonic()
    data = read_json(PROGRAMS, {"programs": []}) or {"programs": []}
    entries = {e["url"]: e for e in data["programs"]}
    dropped = read_json(DROPPED, {"dropped": []}) or {"dropped": []}
    dropped_urls = {d["url"] for d in dropped["dropped"]}
    excluded = load_excluded()
    strikes = c["strikes_before_drop"]
    before_shown = {u for u, e in entries.items() if shown(e, strikes)}

    cutoff = now - timedelta(days=c["recheck_after_days"])
    work = []
    for url, e in entries.items():
        last = parse_iso(e.get("checked_at"))
        if check_all or last is None or last <= cutoff:
            work.append(url)
    known = set(entries) | dropped_urls
    new_urls = []
    queued = {canonical(u) for u in read_queue()}
    for raw in list(candidates or []) + sorted(queued):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        u = canonical(raw)
        if u not in known and u not in new_urls:
            new_urls.append(u)
    work += new_urls
    work = [u for u in work if site_key(urlsplit(u).hostname or "") not in excluded
            and (urlsplit(u).hostname or "") not in excluded]
    if limit:
        work = work[:limit]

    client = client or Client(c["user_agent"], c["token"], min_host_delay=c["min_host_delay_seconds"],
                              max_crawl_delay=c["max_crawl_delay_seconds"], global_rps=c["global_requests_per_second"],
                              max_bytes=c["max_bytes"], timeout=c["timeout_seconds"])
    by_host = {}
    for u in work:
        by_host.setdefault(urlsplit(u).hostname, []).append(u)
    results, lock, tally = {}, threading.Lock(), Counter()
    log = open(private_log, "a", encoding="utf-8") if private_log else None
    deadline = started + max_seconds if max_seconds else None

    def do_host(urls):
        for u in urls:
            if deadline and time.monotonic() > deadline:
                return
            try:
                res = check_url(client, u)
                if res["status"] == "live":
                    last = parse_iso((entries.get(u) or {}).get("shop_checked"))
                    if last is None or now - last >= SHOP_RECHECK:
                        res["shop"] = shop_meta(client, res["final_url"])
                        shop = res["shop"] or {}
                        if classify.restricted(shop.get("name", ""), shop.get("description", "")):
                            res = {"status": "not_program", "note": "age-restricted store or product"}
            except Exception as e:  # one odd page must never stop the run
                res = {"status": "error", "note": f"{type(e).__name__}"[:80]}
            with lock:
                results[u] = res
                tally[res["status"]] += 1
                if log:
                    log.write(json.dumps({"url": u, "status": res["status"], "note": res.get("note", ""),
                                          "final": res.get("final_url", "")}) + "\n")
                    log.flush()
                done = len(results)
                if not quiet and done % 100 == 0:
                    print(f"  checked {done}/{len(work)}  {dict(tally)}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=c["workers"]) as ex:
        list(ex.map(do_host, by_host.values()))
    if log:
        log.close()

    added, removed = [], []
    for u, res in results.items():
        if u in entries:
            e = apply_result(entries[u], res, now)
            if res["status"] == "live" and e["url"] != u:      # the page moved within the site
                entries.pop(u)
                if u in before_shown:
                    before_shown.discard(u)
                    before_shown.add(e["url"])
                if e["url"] in entries:                         # ...onto a page that is already listed
                    continue
                entries[e["url"]] = e
        elif res["status"] == "live":
            e = apply_result({"url": u}, res, now)
            if e["url"] not in entries:
                entries[e["url"]] = e
                added.append(e)
    # Retire entries that failed hard, or failed softly too many times in a row.
    for u in list(entries):
        e = entries[u]
        if e.get("status") in HARD or e.get("fails", 0) >= MAX_FAILS:
            if e.get("status") == "closed" and e.get("fails", 0) < MAX_FAILS:
                continue  # keep watching a paused program; it returns when the page reopens
            entries.pop(u)
            dropped["dropped"].append({"url": u, "brand": e.get("brand", ""), "reason": e.get("status"),
                                       "note": e.get("note", ""), "dropped_at": iso(now)[:10]})
    # Pages from the public queue that did not qualify are remembered, so they are not tried every week.
    for u in sorted(queued):
        res = results.get(u)
        if res and res["status"] != "live" and res["status"] not in SOFT:
            dropped["dropped"].append({"url": u, "brand": "", "reason": res["status"], "note": res.get("note", ""),
                                       "dropped_at": iso(now)[:10], "candidate": True})
    for d in excluded:
        for u in [u for u, e in entries.items() if site_key(urlsplit(u).hostname or "") == d or urlsplit(u).hostname == d]:
            e = entries.pop(u)
            dropped["dropped"].append({"url": u, "brand": e.get("brand", ""), "reason": "excluded",
                                       "note": "listed in config/exclude.txt", "dropped_at": iso(now)[:10]})

    after = list(entries.values())
    assign_ids(after)
    after_shown = {e["url"] for e in after if shown(e, strikes)}
    for u in before_shown - after_shown:
        prev = next((d for d in reversed(dropped["dropped"]) if d["url"] == u), None)
        e = entries.get(u)
        removed.append({"brand": (e or prev or {}).get("brand", ""), "url": u,
                        "reason": (e or {}).get("status") or (prev or {}).get("reason", "")})
    lost = len(before_shown - after_shown)
    summary = {"checked": len(results), "results": dict(tally), "listed": len(after_shown), "added": len(added),
               "removed": lost, "requests": client.requests_made, "seconds": int(time.monotonic() - started),
               "unfinished": len(work) - len(results)}
    if before_shown and lost > max(10, cfg["max_drop_share"] * len(before_shown)):
        print(f"REFUSING to write: this run would remove {lost} of {len(before_shown)} listings. {summary}")
        return summary, False
    if after_shown and len(after_shown) < cfg["min_listings_to_publish"] and len(before_shown) >= cfg["min_listings_to_publish"]:
        print(f"REFUSING to write: only {len(after_shown)} listings would remain. {summary}")
        return summary, False

    after.sort(key=lambda e: ((e.get("brand") or "").lower(), e["url"]))
    write_json(PROGRAMS, {"programs": after, "updated_at": iso(now)})
    if queued:  # keep only what this run did not get to, or could not read
        left = sorted(u for u in queued if u not in results or results[u]["status"] in SOFT)
        with open(QUEUE, "w", encoding="utf-8") as f:
            f.write("# New program pages to try, one address per line. The weekly check empties this file.\n" + "".join(u + "\n" for u in left))
    dropped["dropped"] = dropped["dropped"][-5000:]
    write_json(DROPPED, dropped)
    changes = read_json(CHANGES, {"runs": []}) or {"runs": []}
    if results:
        changes["runs"].append({
            "date": iso(now), "checked": len(results), "listed": len(after_shown), "launch": not before_shown,
            "added": [] if not before_shown else [
                {"brand": e["brand"], "id": e["id"], "types": e["types"], "category": e["category"]} for e in added
                if shown(e, strikes)][:400],
            "removed": [{"brand": r["brand"], "reason": r["reason"]} for r in removed if r["brand"]][:400]})
        changes["runs"] = changes["runs"][-60:]
        write_json(CHANGES, changes)
    status = read_json(STATUS, {}) or {}
    status.update(last_run=iso(now), last_summary=summary)
    if results and tally.get("live", 0) > 0 and not summary["unfinished"]:
        status["last_success"] = iso(now)
    elif not work:
        status["last_noop"] = iso(now)
    write_json(STATUS, status)
    if not quiet:
        print(json.dumps(summary))
    return summary, True


def check_fresh(now=None):
    """Has any run verified listings recently? Used by the self-test to catch a refresh that stopped."""
    now = now or now_utc()
    data = read_json(PROGRAMS, {"programs": []}) or {"programs": []}
    newest = max((parse_iso(e.get("verified_at")) for e in data["programs"] if e.get("verified_at")), default=None)
    if newest is None or now - newest > MAX_FRESH_AGE:
        print(f"STALE: newest verification is {iso(newest) if newest else 'never'} (limit {MAX_FRESH_AGE.days} days)")
        return False
    print(f"fresh: newest verification {iso(newest)}")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="re-check every listing, not only those due")
    ap.add_argument("--candidates", help="file of new public URLs to try, one per line")
    ap.add_argument("--max-seconds", type=int, help="stop starting new checks after this long")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--private-log", help="append every result to this JSONL file (kept out of the repository)")
    ap.add_argument("--check-fresh", action="store_true")
    a = ap.parse_args(argv)
    if a.check_fresh:
        return 0 if check_fresh() else 1
    cands = []
    if a.candidates:
        with open(a.candidates, encoding="utf-8") as f:
            cands = [line for line in f if re.match(r"\s*https?://", line)]
    _, ok = run(candidates=cands, check_all=a.all, max_seconds=a.max_seconds, limit=a.limit, private_log=a.private_log)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
