"""Build the static site from data/programs.json.

  python3 -m directory.build [--site _site]

Environment (all optional):
  SITE_URL          public base URL (the one setting to change for a custom domain)
  SITE_INDEXABLE    "false" to add noindex and publish no sitemap
  GOATCOUNTER_URL   privacy-friendly page counts, e.g. https://<code>.goatcounter.com/count
  SPONSOR_URL, SPONSOR_LABEL, SPONSOR_TEXT   the one clearly labelled sponsor slot
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import statistics
import sys
from collections import Counter
from html import escape as E
from urllib.parse import urlsplit

from . import md
from .classify import CATEGORY_LABEL, CATEGORIES, COUNTRY, LANG_NAME, RESIDENT_LABEL, SOCIAL_LABEL, TYPE_LABEL, TYPE_ORDER
from .common import DATA, ROOT, human_date, iso, load_config, now_utc, parse_iso, read_json, site_key, site_url, slugify
from .verify import CHANGES, PROGRAMS, shown

MIN_LIST = 8          # a platform, region or category-and-type page needs at least this many listings
METHOD_RANK = {"platform": 0, "external_form": 1, "form": 2, "portal": 3, "link": 4, "email": 5}
METHOD_LABEL = {"form": "Form on the page", "email": "Email address on the page",
                "portal": "Sign-up portal on the brand's site", "link": "Application page linked from the page"}
TYPE_PLURAL = {"ambassador": "Ambassador programs", "affiliate": "Affiliate programs",
               "creator": "Creator and influencer programs", "gifting": "PR and gifting programs",
               "collab": "Collaboration programs"}
TYPE_BLURB = {
    "ambassador": "Ongoing relationships: a brand picks people to represent it, usually in exchange for products, a discount code or commission.",
    "affiliate": "You share a tracked link or code and earn a commission on the sales it brings in.",
    "creator": "Brands looking for influencers, content creators or UGC makers for campaigns and content.",
    "gifting": "Pages where a brand takes requests to join its PR list or to receive gifted products.",
    "collab": "Open collaboration pages that invite creators to pitch or apply to work with the brand.",
}
REASON = {"gone": "the page was removed", "not_program": "the page no longer describes an open program",
          "closed": "the page says applications are closed or paused", "noindex": "the site asked not to be listed",
          "robots": "the site's robots.txt asked crawlers to stay away", "moved": "the page moved to another site",
          "blocked": "the page could not be read", "error": "the page could not be read", "excluded": "removed on request"}

FTC_URL = "https://www.ftc.gov/influencers"


class Site:
    def __init__(self, out, now=None):
        self.cfg = load_config()
        self.url = site_url(self.cfg)
        self.base = urlsplit(self.url).path.rstrip("/")
        self.out = out
        self.now = now or now_utc()
        self.indexable = self.cfg.get("indexable", True) and os.environ.get("SITE_INDEXABLE", "").lower() != "false"
        self.name = self.cfg["name"]
        self.repo_url = f"https://github.com/{self.cfg['repo']}"
        self.urls = []           # canonical URLs of indexable pages, for the sitemap and IndexNow
        self.paths = {"/"}       # every page path written so far
        self.og_jobs = []        # (file name, title, subtitle) for directory.og

    def href(self, path):
        return self.base + path

    def write(self, rel, text):
        path = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    # --- page shell ----------------------------------------------------------------------------
    def page(self, path, title, description, body, *, crumbs=None, jsonld=None, og=None, nav="", listed=True,
             body_class="", bare=False, lastmod=None):
        canonical = self.url + path
        full_title = title if self.name in title else f"{title} | {self.name}"
        og_file = "home.png"
        if og:
            og_file = og[0] + ".png"
            self.og_jobs.append(og)
        robots = "" if (self.indexable and listed) else '<meta name="robots" content="noindex">\n'
        ld = ""
        for block in jsonld or []:
            safe = json.dumps(block, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            ld += '<script type="application/ld+json">' + safe + "</script>\n"
        gc = os.environ.get("GOATCOUNTER_URL", "").strip()
        analytics = f'<script data-goatcounter="{E(gc)}" async src="https://gc.zgo.at/count.js"></script>\n' if gc else ""
        crumb_html = ""
        if crumbs:
            parts = [f'<a href="{self.href(p)}">{E(t)}</a>' for t, p in crumbs]
            crumb_html = '<p class="crumbs">' + " › ".join(parts) + "</p>"
        head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(full_title)}</title>
<meta name="description" content="{E(description)}">
{robots}<link rel="canonical" href="{E(canonical)}">
<meta name="site-base" content="{E(self.base)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{E(self.name)}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(description)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{E(self.url)}/og/{og_file}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{self.href('/static/favicon.svg')}" type="image/svg+xml">
<link rel="alternate" type="application/atom+xml" title="{E(self.name)}: weekly changes" href="{self.href('/feed.xml')}">
<link rel="stylesheet" href="{self.href('/static/style.css')}">
{ld}{analytics}</head>
"""
        if bare:
            html = head + f'<body class="{body_class}">\n<main>\n{body}\n</main>\n<script src="{self.href("/static/app.js")}" defer></script>\n</body>\n</html>\n'
        else:
            def nav_link(key, label, p):
                cur = ' aria-current="page"' if nav == key else ""
                return f'<a href="{self.href(p)}"{cur}>{label}</a>'
            html = head + f"""<body class="{body_class}">
<a class="skip" href="#main">Skip to content</a>
<header class="site"><div class="wrap">
<a class="brand" href="{self.href('/')}">{LOGO}<span>{E(self.name)}</span></a>
<nav class="main" aria-label="Main">
{nav_link('browse', 'Browse', '/#browse')}
{nav_link('guides', 'Guides', '/guides/')}
{nav_link('changes', 'Changes', '/changes/')}
{nav_link('method', 'How it works', '/methodology/')}
{nav_link('data', 'Data', '/data/')}
</nav>
</div></header>
<main id="main"><div class="wrap">
{crumb_html}
{body}
</div></main>
{self.footer()}
<script src="{self.href('/static/app.js')}" defer></script>
</body>
</html>
"""
        rel = path.lstrip("/")
        if rel.endswith("/") or rel == "":
            rel += "index.html"
        self.write(rel, html)
        self.paths.add(path)
        if listed and self.indexable:
            self.urls.append((canonical, lastmod or self.asof_date))

    def footer(self):
        return f"""<footer class="site"><div class="wrap"><div class="cols">
<div><strong>{E(self.name)}</strong>
<p>Links to application pages that brands publish themselves. Free, no sign-up, no ads. We are not affiliated
with any brand listed, and a listing is not an endorsement. We never apply for you.</p></div>
<div><strong>Use it well</strong><ul>
<li><a href="{self.href('/guides/disclose-gifted-products-and-affiliate-links/')}">Disclose gifted products and affiliate links</a></li>
<li><a href="{self.href('/guides/spot-a-fake-brand-ambassador-offer/')}">Spot a fake ambassador offer</a></li>
<li><a href="{self.href('/methodology/')}">How listings are checked</a></li>
<li><a href="{self.href('/methodology/#for-brands')}">Brands: correct or remove a listing</a></li></ul></div>
<div><strong>Open project</strong><ul>
<li><a href="{self.href('/data/')}">Download the data (CC0)</a></li>
<li><a href="{self.href('/embed/')}">Embed a list on your site</a></li>
<li><a href="{self.href('/feed.xml')}">Weekly changes feed</a></li>
<li><a href="{E(self.repo_url)}" rel="noopener">Source code on GitHub</a></li>
<li><a href="{self.href('/about/')}">About</a></li></ul></div>
</div>
<p>Listings last checked <time datetime="{E(self.asof_iso)}">{E(self.asof_human)}</time>. Details marked "the page mentions"
are read from each brand's page by a script and can be wrong or out of date: confirm on the brand's page before you apply.</p>
</div></footer>"""

    def sponsor(self):
        url = os.environ.get("SPONSOR_URL", "").strip()
        if not url.startswith("https://"):
            return ""
        label = os.environ.get("SPONSOR_LABEL", "").strip() or urlsplit(url).hostname
        text = os.environ.get("SPONSOR_TEXT", "").strip()
        return (f'<aside class="sponsor" aria-label="Sponsor"><small>Sponsor</small>'
                f'<a href="{E(url)}" rel="sponsored noopener">{E(label)}</a>{(" — " + E(text)) if text else ""}</aside>')


LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#0f6b5c"/>'
        '<path d="M9 16.5l4.5 4.5L23 11" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
FAVICON = LOGO.replace(' aria-hidden="true"', ' xmlns="http://www.w3.org/2000/svg"')


# ------------------------------------------------------------------------------------------------
# Listings
# ------------------------------------------------------------------------------------------------
def load_listings(cfg):
    data = read_json(PROGRAMS, {"programs": []}) or {"programs": []}
    strikes = cfg["crawler"]["strikes_before_drop"]
    rows = [e for e in data["programs"] if shown(e, strikes) and e.get("types") and e.get("apply") and e.get("id")]
    # One listing per site and main program type, then one per brand name and type (regional copies of
    # the same store): prefer a platform link, then a shorter address.
    def rank(e):
        return (METHOD_RANK.get(e["apply"]["method"], 9), len(e["url"]), e["url"])

    for keyfn in (lambda e: (site_key(e["host"]), e["types"][0]), lambda e: (slugify(e["brand"]), e["types"][0])):
        best = {}
        for e in rows:
            k = keyfn(e)
            if k not in best or rank(e) < rank(best[k]):
                best[k] = e
        rows = list(best.values())
    rows.sort(key=lambda e: (e["brand"].lower(), e["url"]))
    return rows


def followers(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:g}M"
    if n >= 1_000:
        return f"{n / 1_000:g}K"
    return str(n)


def mentions(f):
    out = []
    if f.get("commission_pct"):
        out.append(f"{f['commission_pct']}% commission")
    if f.get("free_product"):
        out.append("free or gifted products")
    if f.get("paid"):
        out.append("paid work")
    if f.get("discount_pct"):
        out.append(f"a {f['discount_pct']}% discount")
    if f.get("followers_min"):
        out.append(f"{followers(f['followers_min'])}+ followers")
    if f.get("no_follower_minimum"):
        out.append("no follower minimum")
    if f.get("residents"):
        out.append(f"open to {RESIDENT_LABEL[f['residents']]}")
    if f.get("min_age"):
        out.append(f"applicants must be {f['min_age']}+")
    if f.get("platforms"):
        out.append(", ".join(SOCIAL_LABEL.get(p, p) for p in f["platforms"]))
    return out


def how(e):
    a = e["apply"]
    if a["method"] == "platform":
        return f"Apply through {E(a['label'])} (linked from the page)"
    if a["method"] == "external_form":
        return f"{E(a['label'])} linked from the page"
    return E(METHOD_LABEL.get(a["method"], "Form on the page"))


def via_label(e):
    a = e["apply"]
    return METHOD_LABEL.get(a["method"], a["label"])


def ships(e):
    """'Store ships worldwide' / 'Store ships to US, CA' from the store's own summary, or ''."""
    shop = e.get("shop") or {}
    if shop.get("ships_world"):
        return "Store ships worldwide"
    if shop.get("ships_to"):
        more = shop.get("ships_count", 0) - len(shop["ships_to"])
        return "Store ships to " + ", ".join(shop["ships_to"][:6]) + (f" and {more} more" if more > 0 else "")
    return ""


def lang_code(e):
    return (e.get("lang") or "")[:2].lower()


def card(e):
    m = mentions(e.get("facts") or {})
    chips = "".join(f'<li class="chip type">{E(TYPE_LABEL[t])}</li>' for t in e["types"])
    chips += f'<li class="chip">{E(CATEGORY_LABEL.get(e["category"], e["category"]))}</li>'
    if e.get("region"):
        chips += f'<li class="chip">{E(e["region"])}</li>'
    lc = lang_code(e)
    ship = ships(e)
    ship_html = f'<p class="ships">{E(ship)}</p>' if ship else ""
    if lc and lc != "en" and lc in LANG_NAME:
        chips += f'<li class="chip">{E(LANG_NAME[lc])} page</li>'
    when = parse_iso(e["verified_at"])
    mention_html = f'<p class="mentions"><b>The page mentions:</b> {E(" · ".join(m))}</p>' if m else ""
    return (f'<li class="card" id="{E(e["id"])}"><h3>{E(e["brand"])}</h3><div class="host">{E(e["host"])}</div>'
            f'<ul class="chips">{chips}</ul><p class="how">{how(e)}</p>{mention_html}{ship_html}'
            f'<div class="foot"><small>Verified <time datetime="{E(e["verified_at"])}">{when.strftime("%b")} {when.day}, {when.year}</time></small>'
            f'<a class="btn primary" data-out="{E(e["id"])}" href="{E(e["url"])}" rel="noopener nofollow">Open the page'
            f'<span aria-hidden="true"> ↗</span><span class="visually-hidden"> on {E(e["host"])}</span></a></div></li>')


def summarize(rows):
    """Counts used in a list page's opening paragraph. Every number comes from the rows on that page."""
    n = len(rows)
    brands = len({e["host"].replace("www.", "") for e in rows})
    types = Counter(t for e in rows for t in e["types"])
    methods = Counter(e["apply"]["method"] for e in rows)
    comm = [e["facts"]["commission_pct"] for e in rows if e.get("facts", {}).get("commission_pct")]
    free = sum(1 for e in rows if e.get("facts", {}).get("free_product"))
    nomin = sum(1 for e in rows if e.get("facts", {}).get("no_follower_minimum"))
    return {"n": n, "brands": brands, "types": types, "methods": methods, "commission": comm, "free": free, "nomin": nomin}


def plural(n, one, many=None):
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


TYPE_NOUN = {"ambassador": ("ambassador program", "ambassador programs"), "affiliate": ("affiliate program", "affiliate programs"),
             "creator": ("creator and influencer program", "creator and influencer programs"),
             "gifting": ("PR and gifting page", "PR and gifting pages"), "collab": ("collaboration page", "collaboration pages")}
METHOD_PHRASE = [("platform", "a creator or affiliate platform"), ("form", "an application form on the brand's own page"),
                 ("external_form", "a hosted form such as Google Forms or Typeform"), ("portal", "a sign-up portal on the brand's site"),
                 ("link", "an application page linked from the listed page"), ("email", "an email address on the page")]


def intro_sentences(s, asof_human):
    """Plain sentences built only from counts of the rows on the page."""
    parts = []
    t = s["types"]
    kinds = [f"{t[k]:,} {TYPE_NOUN[k][0 if t[k] == 1 else 1]}" for k in TYPE_ORDER if t.get(k)]
    if len(kinds) > 1:
        parts.append("By kind (a page can be more than one): " + ", ".join(kinds) + ".")
    m = s["methods"]
    how_bits = [f"{phrase} ({m[key]:,})" for key, phrase in METHOD_PHRASE if m.get(key)]
    if how_bits:
        parts.append("How you apply: " + "; ".join(how_bits) + ".")
    extra = []
    if s["commission"]:
        med = statistics.median(s["commission"])
        extra.append(f"a commission rate on {len(s['commission']):,} (median {med:g}%)")
    if s["free"]:
        extra.append(f"free or gifted products on {s['free']:,}")
    if s["nomin"]:
        extra.append(f"no follower minimum on {s['nomin']:,}")
    if extra:
        parts.append("What the pages mention: " + "; ".join(extra) + ".")
    return " ".join(parts)


# ------------------------------------------------------------------------------------------------
# Build
# ------------------------------------------------------------------------------------------------
def build(out, now=None):
    site = Site(out, now)
    cfg = site.cfg
    rows = load_listings(cfg)
    newest = max((parse_iso(e["verified_at"]) for e in rows), default=site.now)
    site.asof_iso, site.asof_human, site.asof_date = iso(newest), human_date(newest), iso(newest)[:10]
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(out, "static"))
    site.write("static/favicon.svg", FAVICON)

    asof = f'<p class="asof">Every listing below was read from the brand\'s own page. Last full check: <time datetime="{site.asof_iso}">{site.asof_human}</time>.</p>'
    s_all = summarize(rows)

    # --- groupings ---------------------------------------------------------------------------------
    by_cat, by_type, by_via, by_region, combos = {}, {}, {}, {}, {}
    # A category with only a handful of listings would make a thin page: those listings go under "Other brands".
    sizes = Counter(e["category"] for e in rows)
    for e in rows:
        if sizes[e["category"]] < MIN_LIST:
            e["category"] = "other"
    for e in rows:
        by_cat.setdefault(e["category"], []).append(e)
        for t in e["types"]:
            by_type.setdefault(t, []).append(e)
            combos.setdefault((e["category"], t), []).append(e)
        if e["apply"]["method"] in ("platform", "external_form"):
            by_via.setdefault(e["apply"]["label"], []).append(e)
        if e.get("region"):
            by_region.setdefault(e["region"], []).append(e)
    cat_order = [k for k, _, _ in CATEGORIES if k in by_cat] + (["other"] if "other" in by_cat else [])
    type_pages = [t for t in TYPE_ORDER if len(by_type.get(t, [])) >= MIN_LIST]
    via_pages = {k: v for k, v in by_via.items() if len(v) >= MIN_LIST}
    region_pages = {k: v for k, v in by_region.items() if len(v) >= MIN_LIST}
    combo_pages = {k: v for k, v in combos.items() if len(v) >= MIN_LIST and k[0] != "other" and k[1] != "collab"}
    perks = [
        ("free-products", "Brands whose creator programs mention free products",
         "Brand programs whose own pages mention free, gifted or complimentary products for creators and ambassadors.",
         "These brands' application pages mention free, gifted or complimentary products. That is the page's wording, not a promise: most brands choose who receives products.",
         [e for e in rows if e.get("facts", {}).get("free_product")]),
        ("no-follower-minimum", "Creator programs open to small accounts",
         "Brand ambassador, creator and affiliate programs whose pages say there is no follower minimum, or ask for 5,000 followers or fewer.",
         "These pages either say there is no follower minimum or name a minimum of 5,000 followers or fewer.",
         [e for e in rows if e.get("facts", {}).get("no_follower_minimum") or 0 < e.get("facts", {}).get("followers_min", 0) <= 5000]),
        ("commission", "Brand programs that pay commission",
         "Brand affiliate and ambassador programs whose pages state a commission rate, with the rate each page mentions.",
         "Each of these pages states a commission percentage. Rates change and often depend on tiers, so read the brand's terms.",
         [e for e in rows if e.get("facts", {}).get("commission_pct")]),
        ("paid", "Brand programs that mention paid work",
         "Brand creator programs whose pages mention paid collaborations, paid campaigns or cash payments.",
         "These pages mention paid collaborations, paid campaigns or cash payments alongside or instead of products.",
         [e for e in rows if e.get("facts", {}).get("paid")]),
    ]
    perks = [p for p in perks if len(p[4]) >= MIN_LIST]

    def list_page(path, h1, title, description, lede, items, crumbs, og_key, extra_html="", related=""):
        s = summarize(items)
        count_line = (f'As of <time datetime="{site.asof_iso}">{site.asof_human}</time>, this page lists '
                      f'{plural(s["n"], "open program")} from {plural(s["brands"], "brand")}.')
        ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": h1, "description": description,
               "url": site.url + path, "dateModified": site.asof_iso,
               "isPartOf": {"@type": "WebSite", "name": site.name, "url": site.url + "/"},
               "mainEntity": {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": [
                   {"@type": "ListItem", "position": i + 1, "name": e["brand"], "url": e["url"]} for i, e in enumerate(items[:100])]}},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": i + 1, "name": t, "item": site.url + p} for i, (t, p) in enumerate(crumbs + [(h1, path)])]}]
        body = (f"<h1>{E(h1)}</h1>\n<p class=\"lede\">{lede}</p>\n<p>{count_line} {E(intro_sentences(s, site.asof_human))}</p>\n"
                f"{extra_html}{site.sponsor()}\n<ul class=\"cards\">\n" + "\n".join(card(e) for e in items) + "\n</ul>\n"
                f'<p class="note">Applying is free. A real brand program never asks you to pay a fee or buy products to be considered. '
                f'If you receive free products or commission, U.S. rules require a clear disclosure in your posts: see the '
                f'<a href="{FTC_URL}" rel="noopener">FTC\'s guidance for influencers</a> and our '
                f'<a href="{site.href("/guides/disclose-gifted-products-and-affiliate-links/")}">plain-language guide</a>.</p>\n{related}')
        site.page(path, title, description, body, crumbs=crumbs, jsonld=ld, og=(og_key, h1, f"{s['n']} open programs · checked {site.asof_human}"), nav="browse")

    def tiles(pairs):
        return '<ul class="grid">' + "".join(
            f'<li><a class="tile" href="{site.href(p)}"><b>{E(t)}</b><span>{E(sub)}</span></a></li>' for t, sub, p in pairs) + "</ul>"

    home = [("Home", "/")]
    cat_tiles = [(CATEGORY_LABEL[k], plural(len(by_cat[k]), "program"), f"/category/{k}/") for k in cat_order]
    type_tiles = [(TYPE_PLURAL[k], plural(len(by_type[k]), "program"), f"/type/{k}/") for k in type_pages]
    perk_tiles = [(p[1], plural(len(p[4]), "program"), f"/lists/{p[0]}/") for p in perks]
    via_tiles = [(f"Via {k}", plural(len(v), "program"), f"/apply/{slugify(k)}/") for k, v in sorted(via_pages.items(), key=lambda kv: -len(kv[1]))]
    region_tiles = [(k, plural(len(v), "program"), f"/region/{slugify(k)}/") for k, v in sorted(region_pages.items(), key=lambda kv: -len(kv[1]))]

    # --- category pages ------------------------------------------------------------------------------
    for k in cat_order:
        label = CATEGORY_LABEL[k]
        items = by_cat[k]
        sub = [(f"{label}: {TYPE_PLURAL[t].lower()}", plural(len(v), "program"), f"/category/{k}/{t}/")
               for (c, t), v in sorted(combo_pages.items(), key=lambda kv: TYPE_ORDER.index(kv[0][1])) if c == k]
        low = label.lower()
        h1 = f"{label} brands with ambassador, creator and affiliate programs" if k != "other" else "More brands with ambassador, creator and affiliate programs"
        list_page(f"/category/{k}/", h1,
                  f"{label} brand ambassador, creator and affiliate programs" if k != "other" else "More brand ambassador and creator programs",
                  f"{label} brands that publish an open ambassador, creator, affiliate or gifting application page, with how to apply and the date each page was last checked.",
                  f"{E(label)} brands that publish their own application page for ambassadors, creators, affiliates or gifting. "
                  f"Each card links straight to the brand's page.",
                  items, home, f"category-{k}", extra_html=(f"<h2>Narrow it down</h2>{tiles(sub)}" if sub else ""),
                  related=f"<h2>Other categories</h2>{tiles([t for t in cat_tiles if t[2] != f'/category/{k}/'])}")
    for (k, t), items in combo_pages.items():
        label, tl = CATEGORY_LABEL[k], TYPE_PLURAL[t]
        list_page(f"/category/{k}/{t}/", f"{label}: {tl.lower()}", f"{label} brand {tl.lower()}",
                  f"{label} brands with open {tl.lower()}: links to each brand's own application page, how to apply and when the page was last checked.",
                  f"{E(TYPE_BLURB[t])} These are the {E(label.lower())} brands in the directory whose own pages name this kind of program.",
                  items, home + [(label, f"/category/{k}/")], f"category-{k}-{t}")
    # --- type pages ----------------------------------------------------------------------------------
    for t in type_pages:
        list_page(f"/type/{t}/", f"{TYPE_PLURAL[t]} open to applications", f"{TYPE_PLURAL[t]} open to applications",
                  f"Brands with open {TYPE_PLURAL[t].lower()}: a link to each brand's own application page, how to apply, and the date it was last checked.",
                  E(TYPE_BLURB[t]), by_type[t], home, f"type-{t}",
                  related=f"<h2>Other kinds of program</h2>{tiles([x for x in type_tiles if x[2] != f'/type/{t}/'])}")
    for label, items in via_pages.items():
        kind = items[0]["apply"]["method"]
        lede = (f"These brands send applicants to {E(label)}, a platform brands use to run creator and affiliate programs. You apply there, usually with a free creator account."
                if kind == "platform" else f"These brands take applications through a {E(label)} form linked from their own page.")
        list_page(f"/apply/{slugify(label)}/", f"Brand programs that take applications through {label}",
                  f"Brands recruiting creators through {label}",
                  f"Brands whose ambassador, creator or affiliate application runs through {label}, with a link to each brand's own page.",
                  lede, items, home, f"apply-{slugify(label)}")
    for slug, h1, desc, lede, items in perks:
        list_page(f"/lists/{slug}/", h1, h1, desc, E(lede), items, home, f"list-{slug}")
    for label, items in region_pages.items():
        list_page(f"/region/{slugify(label)}/", f"Brand ambassador and creator programs in {label}",
                  f"Brand ambassador and creator programs in {label}",
                  f"Brands based in {label} that publish an open ambassador, creator or affiliate application page, with how to apply.",
                  f"Brands whose store says it is based in {E(label)}, or whose web address points there. Shipping varies: each card shows where the store ships when the store publishes it.",
                  items, home, f"region-{slugify(label)}")

    # --- home ----------------------------------------------------------------------------------------
    stats = (f'<div class="stats"><div class="stat"><b>{s_all["n"]:,}</b><span>open programs listed</span></div>'
             f'<div class="stat"><b>{s_all["brands"]:,}</b><span>brands</span></div>'
             f'<div class="stat"><b>{len(cat_order)}</b><span>product categories</span></div>'
             f'<div class="stat"><b><time datetime="{site.asof_iso}">{newest.strftime("%b")} {newest.day}</time></b><span>last full check ({newest.year})</span></div></div>')
    finder = f"""<section id="browse" aria-label="Find a program">
<h2>Find a program</h2>
<div class="finder" id="finder" hidden>
<div class="row">
<label class="f q">Search brands<input type="search" name="q" placeholder="Brand, product or platform" autocomplete="off"></label>
<label class="f">Category<select name="cat"><option value="">All categories</option></select></label>
<label class="f">Kind of program<select name="type"><option value="">All kinds</option></select></label>
<label class="f">How you apply<select name="via"><option value="">Any way</option></select></label>
<label class="f">The page mentions<select name="perk"><option value="">Anything</option><option value="free">Free or gifted products</option>
<option value="commission">A commission rate</option><option value="paid">Paid work</option><option value="small">Small accounts welcome</option></select></label>
<label class="f">Store ships to<select name="ship"><option value="">Anywhere</option></select></label>
</div>
<div class="meta"><span id="count" role="status" aria-live="polite"></span>
<span><button type="button" id="reset">Clear</button> <button type="button" id="copy">Copy link to this search</button></span></div>
</div>
<ul class="cards" id="results"></ul>
<div class="more"><button type="button" id="more" hidden>Show more</button></div>
<noscript><p class="note">The search box needs JavaScript. Every listing is also on the category pages below, which work without it.</p></noscript>
</section>"""
    home_ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": site.name, "url": site.url + "/",
                "description": cfg["tagline"],
                "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": site.url + "/?q={search_term_string}"},
                                    "query-input": "required name=search_term_string"}}]
    body = f"""<h1>Brands with open ambassador, creator and affiliate applications</h1>
<p class="lede">A free directory of the application pages brands publish themselves: ambassador programs, creator and UGC
programs, affiliate programs and gifting requests. Every link goes to the brand's own page, and every page is re-checked each
week. You apply yourself. Nothing is submitted for you.</p>
{stats}
{site.sponsor()}
{finder}
<h2>Browse by category</h2>
{tiles(cat_tiles)}
<h2>Browse by kind of program</h2>
{tiles(type_tiles)}
{('<h2>Popular lists</h2>' + tiles(perk_tiles)) if perk_tiles else ''}
{('<h2>By application platform</h2>' + tiles(via_tiles)) if via_tiles else ''}
{('<h2>By country</h2>' + tiles(region_tiles)) if region_tiles else ''}
<h2>How it works</h2>
<ol class="steps">
<li><b>Brands publish the page</b>We only list pages a brand has put on its own website to invite ambassadors, creators, affiliates or gifting requests.</li>
<li><b>A crawler checks it weekly</b>It obeys each site's robots.txt, reads the page once, and drops listings that are gone, closed or blocked.</li>
<li><b>You apply on the brand's site</b>Open the page, read the brand's terms, and apply yourself. We never fill in or send anything.</li>
</ol>
<p class="note">Applying is free. A real program never asks you to pay to join or to buy products to be considered.
Read <a href="{site.href('/guides/spot-a-fake-brand-ambassador-offer/')}">how to spot a fake ambassador offer</a>.</p>
<h2>Guides</h2>
{{guides}}
"""
    # --- guides --------------------------------------------------------------------------------------
    guides = []
    gdir = os.path.join(ROOT, "content", "guides")
    for fn in sorted(os.listdir(gdir)):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(gdir, fn), encoding="utf-8") as f:
            meta, text = md.front_matter(f.read())
        slug = meta.get("slug") or fn[:-3].split("-", 1)[-1]
        med = f"{statistics.median(s_all['commission']):g}" if s_all["commission"] else "n/a"
        for k, v in {"{count}": f"{s_all['n']:,}", "{asof}": site.asof_human, "{nomin}": f"{s_all['nomin']:,}",
                     "{free}": f"{s_all['free']:,}", "{commission_n}": f"{len(s_all['commission']):,}",
                     "{commission_median}": med}.items():
            text = text.replace(k, v)
        html = md.render(text)

        def fix(m):
            # A guide may point at a list that no longer has enough entries to exist: send the reader to search.
            target = m.group(1)
            ok = target.split("#")[0] in site.paths or target.startswith(("/guides/", "/methodology/", "/about/", "/data/", "/embed/", "/changes/"))
            return f'href="{site.href(target if ok else "/#browse")}"'

        guides.append((slug, meta, re.sub(r'href="\{base\}([^"]*)"', fix, html)))
    for slug, meta, html in guides:
        ld = [{"@context": "https://schema.org", "@type": "Article", "headline": meta["title"], "description": meta["description"],
               "dateModified": meta.get("updated", site.asof_date), "datePublished": meta.get("published", meta.get("updated", site.asof_date)),
               "author": {"@type": "Organization", "name": site.name, "url": site.url + "/"},
               "publisher": {"@type": "Organization", "name": site.name}, "mainEntityOfPage": site.url + f"/guides/{slug}/"}]
        body_g = (f'<article class="prose"><h1>{E(meta["title"])}</h1>\n<p class="lede">{E(meta["description"])}</p>\n{html}\n'
                  f'<p class="asof">Last reviewed <time datetime="{E(meta.get("updated", ""))}">{E(human_date(parse_iso(meta["updated"])) if meta.get("updated") else "")}</time>. '
                  f'General information, not legal advice.</p></article>\n'
                  f'<p><a class="btn primary" href="{site.href("/#browse")}">Browse open programs</a></p>')
        site.page(f"/guides/{slug}/", meta["title"], meta["description"], body_g, crumbs=home + [("Guides", "/guides/")], jsonld=ld,
                  og=(f"guide-{slug}", meta["title"], "Guide"), nav="guides", lastmod=meta.get("updated"))
    guide_tiles = tiles([(m["title"], m["description"], f"/guides/{slug}/") for slug, m, _ in guides])
    site.page("/guides/", "Guides for applying to brand programs",
              "Plain-language guides to brand ambassador, affiliate and gifting programs: how to apply, how to disclose, and how to avoid scams.",
              f"<h1>Guides</h1><p class=\"lede\">Short, practical guides for applying to brand programs.</p>{guide_tiles}", crumbs=home, nav="guides")
    site.page("/", f"{site.name}: brands with open ambassador, creator and affiliate applications", cfg["tagline"],
              body.replace("{guides}", guide_tiles), jsonld=home_ld, og=("home", "Brands with open ambassador, creator and affiliate applications",
                                                                        f"{s_all['n']:,} programs · checked {site.asof_human}"))

    # --- changes + feed ------------------------------------------------------------------------------
    runs = list(reversed((read_json(CHANGES, {"runs": []}) or {"runs": []})["runs"]))
    blocks, entries_xml = [], []
    for r in runs[:26]:
        when = parse_iso(r["date"])
        added, removed = r.get("added", []), r.get("removed", [])
        head = f'<h2 id="{when.strftime("%Y-%m-%d")}"><time datetime="{E(r["date"])}">{human_date(when)}</time></h2>'
        if r.get("launch"):
            text = f"<p>The directory opened with {r['listed']:,} verified programs.</p>"
            summary = f"The directory opened with {r['listed']:,} verified programs."
        else:
            text = f"<p>{r['checked']:,} pages checked. {r['listed']:,} programs listed after this run: {len(added)} added, {len(removed)} removed.</p>"
            summary = f"{r['checked']:,} pages checked; {len(added)} added, {len(removed)} removed; {r['listed']:,} listed."
            if added:
                text += "<h3>Added</h3><ul class=\"changes\">" + "".join(
                    f'<li><a href="{site.href("/category/" + a["category"] + "/")}#{E(a["id"])}">{E(a["brand"])}</a> ({E(", ".join(TYPE_LABEL[t].lower() for t in a["types"]))})</li>'
                    for a in added) + "</ul>"
            if removed:
                text += "<h3>Removed</h3><ul class=\"changes\">" + "".join(
                    f'<li>{E(x["brand"])}: {E(REASON.get(x["reason"], "no longer verified"))}</li>' for x in removed) + "</ul>"
        blocks.append(head + text)
        entries_xml.append(f"<entry><title>{E(human_date(when))}: {E(summary)}</title><id>{E(site.url)}/changes/#{when.strftime('%Y-%m-%d')}</id>"
                           f'<link href="{E(site.url)}/changes/#{when.strftime("%Y-%m-%d")}"/><updated>{E(r["date"])}</updated>'
                           f"<summary>{E(summary)}</summary></entry>")
    site.page("/changes/", "What changed this week", "Programs added to and removed from the directory after each weekly check, with the reason for every removal.",
              "<h1>What changed</h1><p class=\"lede\">After each check, the programs that were added and the listings that were removed, with the reason.</p>"
              + ("".join(blocks) or "<p>No runs recorded yet.</p>"), crumbs=home, nav="changes")
    site.write("feed.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>{E(site.name)}: weekly changes</title>'
               f'<id>{E(site.url)}/</id><link href="{E(site.url)}/changes/"/><link rel="self" href="{E(site.url)}/feed.xml"/>'
               f"<updated>{E(runs[0]['date'] if runs else site.asof_iso)}</updated><author><name>{E(site.name)}</name></author>"
               + "".join(entries_xml[:20]) + "</feed>\n")

    # --- static pages --------------------------------------------------------------------------------
    ua = cfg["crawler"]["user_agent"]
    token = cfg["crawler"]["token"]
    method = f"""<article class="prose"><h1>How listings are found and checked</h1>
<p class="lede">The rules this directory follows, so you can judge how far to trust a listing.</p>
<h2 id="what-is-listed">What gets listed</h2>
<p>Only pages that a brand has published on its own website to invite ambassadors, creators, affiliates or gifting requests.
A page is listed when its address or headline names that kind of program <em>and</em> the page shows a way to apply: a form,
a link to a creator or affiliate platform, a hosted form such as Google Forms, or an email address.</p>
<p>Never listed: general contact forms, wholesale and stockist pages, careers pages, donation and sponsorship request pages,
pages that say applications are closed, and pages a site marks <code>noindex</code>.</p>
<h2 id="how-pages-are-checked">How pages are checked</h2>
<ul>
<li>A crawler reads each site's <code>robots.txt</code> and obeys it, including <code>Crawl-delay</code>.</li>
<li>It fetches each listed page about once a week with a plain request. No cookies, no logins, no forms filled in, nothing submitted.</li>
<li>If a site answers with a bot check, a 403 or a 429, the crawler stops. It does not try to get around it.</li>
<li>A page that is gone, closed, or no longer describes a program is removed in that run. A page that could not be read keeps its
older "verified" date for one more run and is then removed until it can be read again.</li>
</ul>
<p>The crawler identifies itself as <code>{E(ua)}</code>.</p>
<h2 id="the-page-mentions">What "the page mentions" means</h2>
<p>A script looks for a few details in the page's own wording: a commission percentage, a discount percentage, free or gifted
products, paid work, a follower minimum, and which social platforms are named. It can misread a page, and brands change their
terms. Treat these as pointers and confirm on the brand's page. The "verified" date on each card is the last time the crawler
read that page and found an open program on it.</p>
<h2 id="store-details">Where "based in" and "ships to" come from</h2>
<p>Stores built on Shopify publish a small public summary of themselves (a file called <code>meta.json</code>) with the store's
name, country and the countries it ships to. The crawler reads that file at most once every four weeks, if the site's
robots.txt allows it. For other sites the country is a guess from the web address. "Ships to" is the store's general
shipping list, not a promise about gifted products.</p>
<h2 id="not-listed">Stores that are not listed</h2>
<p>The directory leaves out stores for alcohol, tobacco and vaping, cannabis and similar products, weapons, adult products and
gambling. It also leaves out any "program" whose page asks people to pay a fee or buy a kit in order to join.</p>
<h2 id="limits">Limits</h2>
<ul>
<li>This is not a complete list of every brand program. It covers the brands the crawler knows about, mostly consumer products.</li>
<li>A listing says a page exists and looks open. It says nothing about whether the brand will accept you, reply, or ship anything.</li>
<li>Country and shipping details come from the store's own summary or its web address. They are not a promise to ship to you.</li>
<li>We do not rate brands and we are not affiliated with any of them.</li>
</ul>
<h2 id="for-brands">For brands: correct or remove a listing</h2>
<p>The surest way to remove a page is to tell the crawler directly. Add this to your <code>robots.txt</code> and the listing
disappears at the next weekly check:</p>
<pre><code>User-agent: {E(token)}
Disallow: /</code></pre>
<p>A <code>noindex</code> robots meta tag on the page does the same. If the page says applications are closed, the listing is
removed until it reopens. You can also <a href="{E(site.repo_url)}/issues/new/choose" rel="noopener">open an issue</a> to ask for
a correction or removal.</p>
<h2 id="disclosure">Disclosure rules</h2>
<p>If a brand gives you free products, payment or commission, U.S. rules require you to say so clearly when you post about
it. Start with the <a href="{FTC_URL}" rel="noopener">FTC's guidance for influencers</a>. Other countries have their own rules.</p>
<p class="asof">Listings last checked <time datetime="{site.asof_iso}">{site.asof_human}</time>.</p></article>"""
    site.page("/methodology/", "How listings are found and checked",
              "The rules behind the directory: what gets listed, how the weekly robots-respecting check works, what the details mean, and how brands remove a page.",
              method, crumbs=home, nav="method")
    about = f"""<article class="prose"><h1>About</h1>
<p class="lede">A machine-run public directory with one job: save creators the hours it takes to find which brands take applications.</p>
<p>Brands that want ambassadors, creators or affiliates usually say so on a page of their own website. Those pages are hard to
find one by one. This site keeps a list of them, checks every page each week, and removes the ones that have closed or disappeared.
As of <time datetime="{site.asof_iso}">{site.asof_human}</time> it lists {s_all['n']:,} open programs from {s_all['brands']:,} brands.</p>
<h2>What it is not</h2>
<ul><li>Not an agency or a marketplace. Nobody here represents you or the brands.</li>
<li>Not an application service. You apply on the brand's own page, by yourself.</li>
<li>Not a business. It is free, has no accounts and sells nothing. If a sponsor ever appears, it will be in one box labelled "Sponsor".</li></ul>
<h2>Privacy</h2>
<p>The site sets no cookies and has no sign-up. Your searches run in your browser and are not sent anywhere.
{'Page views are counted with GoatCounter, which stores no personal data.' if os.environ.get('GOATCOUNTER_URL') else 'It runs no analytics.'}</p>
<h2>Open data and code</h2>
<p>The <a href="{site.href('/data/')}">full list is free to download</a> under CC0, and the
<a href="{E(site.repo_url)}" rel="noopener">crawler and site code</a> are public. Questions, corrections and removal requests:
<a href="{E(site.repo_url)}/issues" rel="noopener">open an issue on GitHub</a>.</p></article>"""
    site.page("/about/", "About the directory", "What the Creator Program Directory is, what it is not, how it handles privacy, and where the open data and code live.",
              about, crumbs=home)

    # --- data downloads ------------------------------------------------------------------------------
    fields = ["id", "brand", "url", "host", "category", "types", "apply_method", "apply_via", "country", "ships_to",
              "ships_worldwide", "lang", "commission_pct", "discount_pct", "free_product", "paid", "followers_min",
              "no_follower_minimum", "residents", "min_age", "platforms", "first_seen", "verified_at"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(fields)
    public = []
    for e in rows:
        f = e.get("facts") or {}
        rec = {"id": e["id"], "brand": e["brand"], "url": e["url"], "host": e["host"], "category": e["category"], "types": e["types"],
               "apply_method": e["apply"]["method"], "apply_via": via_label(e), "country": e.get("region", ""),
               "ships_to": (e.get("shop") or {}).get("ships_to", []), "ships_worldwide": bool((e.get("shop") or {}).get("ships_world")),
               "lang": lang_code(e), "residents": f.get("residents", ""), "min_age": f.get("min_age", ""),
               "commission_pct": f.get("commission_pct", ""), "discount_pct": f.get("discount_pct", ""),
               "free_product": bool(f.get("free_product")), "paid": bool(f.get("paid")), "followers_min": f.get("followers_min", ""),
               "no_follower_minimum": bool(f.get("no_follower_minimum")), "platforms": f.get("platforms", []),
               "first_seen": e.get("first_seen", ""), "verified_at": e["verified_at"]}
        public.append(rec)
        w.writerow([";".join(rec[k]) if isinstance(rec[k], list) else rec[k] for k in fields])
    site.write("data/programs.csv", buf.getvalue())
    site.write("data/programs.json", json.dumps({"as_of": site.asof_iso, "license": "CC0-1.0", "source": site.url + "/",
                                                 "programs": public}, ensure_ascii=False, indent=1) + "\n")
    compact = [{"id": e["id"], "b": e["brand"], "u": e["url"], "h": e["host"], "c": e["category"], "t": e["types"],
                "m": e["apply"]["method"], "v": via_label(e), "r": e.get("region", ""), "l": lang_code(e),
                "f": e.get("facts") or {}, "d": e["verified_at"], "s": ships(e),
                "k": ["*"] if (e.get("shop") or {}).get("ships_world") else (e.get("shop") or {}).get("ships_to", [])} for e in rows]
    site.write("assets/programs.json", json.dumps({
        "asof": site.asof_iso, "programs": compact,
        "labels": {"categories": CATEGORY_LABEL, "types": TYPE_LABEL, "socials": SOCIAL_LABEL, "langs": LANG_NAME,
                   "residents": RESIDENT_LABEL, "countries": COUNTRY}},
        ensure_ascii=False, separators=(",", ":")))
    data_ld = [{"@context": "https://schema.org", "@type": "Dataset", "name": f"{site.name}: open brand creator programs",
                "description": "Public brand pages that invite ambassador, creator, affiliate or gifting applications, with how to apply and the date each page was last verified.",
                "url": site.url + "/data/", "license": "https://creativecommons.org/publicdomain/zero/1.0/", "dateModified": site.asof_iso,
                "creator": {"@type": "Organization", "name": site.name, "url": site.url + "/"},
                "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": site.url + "/data/programs.csv"},
                                 {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": site.url + "/data/programs.json"}]}]
    data_page = f"""<article class="prose"><h1>Download the data</h1>
<p class="lede">The whole directory as CSV or JSON, free to reuse under <a href="https://creativecommons.org/publicdomain/zero/1.0/" rel="noopener">CC0</a>.</p>
<p><a class="btn primary" href="{site.href('/data/programs.csv')}">programs.csv</a> <a class="btn" href="{site.href('/data/programs.json')}">programs.json</a></p>
<p class="asof">{len(rows):,} rows, as of <time datetime="{site.asof_iso}">{site.asof_human}</time>. The files are rebuilt after every weekly check.</p>
<h2>Columns</h2>
<div class="tablewrap"><table><thead><tr><th>Column</th><th>Meaning</th></tr></thead><tbody>
<tr><td><code>brand</code>, <code>host</code>, <code>url</code></td><td>The brand's name for itself, its site, and the address of its application page.</td></tr>
<tr><td><code>category</code></td><td>Product category, guessed from the brand's name, address and page.</td></tr>
<tr><td><code>types</code></td><td>Kinds of program the page names: ambassador, affiliate, creator, gifting, collab.</td></tr>
<tr><td><code>apply_method</code>, <code>apply_via</code></td><td>How a person applies: a form on the page, a platform, a hosted form, or email.</td></tr>
<tr><td><code>commission_pct</code>, <code>discount_pct</code>, <code>free_product</code>, <code>paid</code>, <code>followers_min</code>, <code>no_follower_minimum</code>, <code>platforms</code></td>
<td>Details read from the page's wording by a script. Pointers, not guarantees.</td></tr>
<tr><td><code>country</code>, <code>ships_to</code>, <code>ships_worldwide</code></td><td>Where the store says it is based and which major markets it ships to, from the store's own public summary file. Where a store publishes none, the country is a hint from its web address.</td></tr>
<tr><td><code>residents</code>, <code>min_age</code></td><td>Eligibility the page states: a country its applicants must live in, and a minimum age.</td></tr>
<tr><td><code>lang</code></td><td>The page's language code.</td></tr>
<tr><td><code>first_seen</code>, <code>verified_at</code></td><td>When the page was first listed, and the last time the crawler read it and found an open program (UTC).</td></tr>
</tbody></table></div>
<p>Source for every row: the brand's own page at <code>url</code>, read on <code>verified_at</code>. Please link back to
<a href="{site.href('/')}">{E(site.name)}</a> if you reuse the list, so readers can find the current version.</p></article>"""
    site.page("/data/", "Download the directory data (CSV, JSON)", "The full list of open brand ambassador, creator, affiliate and gifting programs as CSV and JSON under CC0.",
              data_page, crumbs=home, jsonld=data_ld, nav="data")

    # --- embed ---------------------------------------------------------------------------------------
    snippet = (f'<iframe src="{site.url}/embed/widget/?category=coffee&n=6" title="Open brand programs" loading="lazy" '
               f'style="width:100%;max-width:520px;height:900px;border:0"></iframe>')
    opts = "".join(f"<tr><td><code>category={k}</code></td><td>{E(CATEGORY_LABEL[k])}</td></tr>" for k in cat_order)
    embed = f"""<article class="prose"><h1>Embed a list on your site</h1>
<p class="lede">Running a creator newsletter, course or community? Drop a live list of open programs into any page. It updates itself every week.</p>
<div class="embedbox"><label for="snip"><b>Copy this HTML</b></label><textarea id="snip" readonly>{E(snippet)}</textarea></div>
<h2>Options</h2>
<p>Change the address inside <code>src</code>: <code>category=</code> picks a product category, <code>type=</code> picks a kind of program
(<code>{'</code>, <code>'.join(type_pages)}</code>), and <code>n=</code> sets how many to show (up to 25).</p>
<div class="tablewrap"><table><thead><tr><th>Category option</th><th>Shows</th></tr></thead><tbody>{opts}</tbody></table></div>
<h2>Preview</h2>
<iframe src="{site.href('/embed/widget/')}?category={cat_order[0] if cat_order else ''}&amp;n=3" title="Preview of the embedded list" loading="lazy" style="width:100%;max-width:520px;height:640px;border:1px solid var(--line);border-radius:14px"></iframe>
</article>"""
    site.page("/embed/", "Embed a live list of open brand programs", "Free embeddable widget: a self-updating list of brands with open creator and ambassador applications for your site or newsletter page.",
              embed, crumbs=home)
    site.page("/embed/widget/", "Open brand programs", "Embeddable list of open brand programs.",
              f'<ul class="cards" id="embed-list"></ul><p class="credit">Live list from <a href="{site.url}/" target="_blank" rel="noopener">{E(site.name)}</a>, re-checked weekly.</p>',
              listed=False, body_class="embed", bare=True)
    site.page("/404.html", "Page not found", "That page does not exist.",
              f'<h1>Page not found</h1><p class="lede">That address is not part of the directory. A listing may have been removed after its page closed.</p>'
              f'<p><a class="btn primary" href="{site.href("/")}">Search the directory</a> <a class="btn" href="{site.href("/changes/")}">See what changed</a></p>', listed=False)

    # --- crawler files ---------------------------------------------------------------------------------
    key = open(os.path.join(ROOT, "config", "indexnow-key.txt")).read().strip()
    site.write(f"{key}.txt", key + "\n")
    if site.indexable:
        sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
            f"<url><loc>{E(u)}</loc><lastmod>{E(d)}</lastmod></url>\n" for u, d in site.urls) + "</urlset>\n"
        site.write("sitemap.xml", sm)
        site.write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {site.url}/sitemap.xml\n")
    else:
        site.write("robots.txt", "User-agent: *\nDisallow: /\n")
    site.write("urls.txt", "\n".join(u for u, _ in site.urls) + "\n")
    site.write("og-jobs.json", json.dumps(site.og_jobs))
    site.write(".nojekyll", "")
    return {"pages": len(site.urls), "listings": len(rows), "brands": s_all["brands"], "asof": site.asof_iso,
            "categories": len(cat_order), "og": len(site.og_jobs)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args(argv)
    print(json.dumps(build(a.site)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
