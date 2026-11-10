"""Check a built site before it is published. Exit 1 (and publish nothing) if anything is off.

  python3 -m directory.guard [_site]

Checks: the key pages exist; enough listings; every card links out to an https page with a verified
date; every internal link resolves; the public data carries only the public fields; and nothing from
private outreach records (the wording such records use) appears anywhere in the site or the data.
"""
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .common import DATA, ROOT, load_config, site_url

MUST = ["index.html", "404.html", "robots.txt", "urls.txt", "feed.xml", "static/style.css", "static/app.js",
        "static/favicon.svg", "assets/programs.json", "data/programs.csv", "data/programs.json", "data/index.html",
        "methodology/index.html", "about/index.html", "guides/index.html", "changes/index.html", "embed/index.html",
        "embed/widget/index.html", "og/home.png"]
# The public data file may only carry these keys. Anything else is a bug, or a leak.
ENTRY_KEYS = {"id", "url", "host", "brand", "title", "types", "apply", "facts", "category", "category_from", "region",
              "lang", "verified_at", "checked_at", "first_seen", "status", "note", "fails", "shop", "shop_checked"}
SHOP_KEYS = {"name", "country", "ships_to", "ships_world", "ships_count"}
FACT_KEYS = {"commission_pct", "discount_pct", "free_product", "paid", "followers_min", "no_follower_minimum",
             "platforms", "residents", "min_age"}
# Words that belong to private outreach records and must never reach the public site or data.
PRIVATE = re.compile(r"america\s+house|america\.co/sponsors|americahouseresearch|submitted_verified|unknown_delivery|"
                     r"captcha_pending|cua[-_]attempt|browser[-_]result|gmail[-_]check|form_profile|campaign[-_]state", re.I)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.cards, self._card, self._depth = [], [], None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k):
                self.links.append(a[k])
        if tag == "li" and "card" in (a.get("class") or "").split():
            self._card, self._depth = {"out": None, "time": False}, 1
            self.cards.append(self._card)
        elif self._card is not None and tag == "li":
            self._depth += 1
        elif self._card is not None and tag == "a" and a.get("data-out"):
            self._card["out"] = (a.get("href", ""), a.get("rel", ""))
        elif self._card is not None and tag == "time" and a.get("datetime"):
            self._card["time"] = True

    def handle_endtag(self, tag):
        if tag == "li" and self._card is not None:
            self._depth -= 1
            if self._depth <= 0:
                self._card = None


def check(site_dir):
    cfg = load_config()
    errors = []
    base_path = urlparse(site_url(cfg)).path.rstrip("/")
    for f in MUST:
        if not os.path.exists(os.path.join(site_dir, f)):
            errors.append(f"missing {f}")
    indexable = cfg.get("indexable", True) and os.environ.get("SITE_INDEXABLE", "").lower() != "false"
    if indexable and not os.path.exists(os.path.join(site_dir, "sitemap.xml")):
        errors.append("missing sitemap.xml")
    try:
        with open(os.path.join(site_dir, "assets", "programs.json"), encoding="utf-8") as f:
            listed = json.load(f)["programs"]
    except (OSError, ValueError, KeyError):
        listed = []
        errors.append("assets/programs.json unreadable")
    if len(listed) < cfg["min_listings_to_publish"]:
        errors.append(f"only {len(listed)} listings (minimum {cfg['min_listings_to_publish']})")
    for p in listed:
        if not p["u"].startswith("https://") or not p.get("d") or not p.get("t") or not p.get("b"):
            errors.append(f"listing {p.get('id')}: incomplete")
    # the data file carries public fields only
    src = os.path.join(DATA, "programs.json")
    if os.path.exists(src):
        with open(src, encoding="utf-8") as f:
            raw = f.read()
        for e in json.loads(raw).get("programs", []):
            extra = set(e) - ENTRY_KEYS
            extra |= {f"shop.{k}" for k in set(e.get("shop") or {}) - SHOP_KEYS}
            extra |= {f"facts.{k}" for k in set(e.get("facts") or {}) - FACT_KEYS}
            if extra:
                errors.append(f"data/programs.json: unexpected field(s) {sorted(extra)} on {e.get('url')}")
                break
        m = PRIVATE.search(raw)
        if m:
            errors.append(f"data/programs.json: private-record wording {m.group(0)!r}")
    pages = cards = 0
    for dirpath, _, files in os.walk(site_dir):
        for fn in files:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, site_dir).replace(os.sep, "/")
            if fn.endswith((".html", ".json", ".csv", ".xml", ".txt")):
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                m = PRIVATE.search(text)
                if m:
                    errors.append(f"{rel}: private-record wording {m.group(0)!r}")
            if not fn.endswith(".html"):
                continue
            pages += 1
            p = Links()
            p.feed(text)
            for c in p.cards:
                cards += 1
                if not c["out"] or not c["out"][0].startswith("https://") or "nofollow" not in c["out"][1] or not c["time"]:
                    errors.append(f"{rel}: a card lacks its outbound link, nofollow or verified date")
                    break
            if "<title>" not in text or 'name="description"' not in text or 'rel="canonical"' not in text:
                errors.append(f"{rel}: missing title, description or canonical")
            if rel == "404.html":
                continue
            for link in p.links:
                u = urlparse(link)
                if u.scheme or link.startswith(("#", "mailto:", "data:", "//")):
                    continue
                target = u.path
                if target.startswith("/"):
                    if base_path and not target.startswith(base_path + "/"):
                        errors.append(f"{rel}: link {link} ignores the site base path")
                        continue
                    target = target[len(base_path):]
                else:
                    target = urlparse(urljoin("file:///" + rel, target)).path
                full = os.path.join(site_dir, target.lstrip("/"))
                if target.endswith("/") or os.path.isdir(full):
                    full = os.path.join(full, "index.html")
                if not os.path.exists(full):
                    errors.append(f"{rel}: broken link {link}")
    return errors, {"pages": pages, "cards": cards, "listings": len(listed)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = argv[0] if argv else os.path.join(ROOT, "_site")
    errors, counts = check(site_dir)
    for e in errors[:50]:
        print("GUARD", e)
    print(f"guard: {counts['pages']} pages, {counts['cards']} cards, {counts['listings']} listings, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
