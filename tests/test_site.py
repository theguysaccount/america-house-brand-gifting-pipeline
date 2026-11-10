import csv
import io
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from directory import build, guard, og, verify
from directory.classify import CATEGORIES, TYPE_ORDER

NOW = datetime(2026, 3, 2, 6, 0, tzinfo=timezone.utc)


def fixture():
    """A synthetic directory: enough entries in two categories for list pages, plus edge cases."""
    rows = []
    cats = ["coffee", "skincare-beauty", "snacks"]
    methods = [{"method": "platform", "provider": "shopify_collabs", "label": "Shopify Collabs"},
               {"method": "form", "provider": "on_page", "label": "Form on the page"},
               {"method": "external_form", "provider": "google_forms", "label": "Google Forms"},
               {"method": "email", "provider": "email", "label": "Email address on the page"}]
    for i in range(72):
        cat = cats[i % 3] if i < 66 else "pets"
        types = [["ambassador"], ["affiliate"], ["creator", "collab"], ["ambassador", "affiliate"]][i % 4]
        facts = {}
        if i % 2 == 0:
            facts["commission_pct"] = 10 + i % 7
        if i % 3 == 0:
            facts["free_product"] = True
        if i % 5 == 0:
            facts["no_follower_minimum"] = True
        if i % 6 == 0:
            facts.update(residents="US", min_age=18, platforms=["instagram", "tiktok"])
        e = {"id": f"brand-{i}", "url": f"https://brand{i}.example/pages/program", "host": f"brand{i}.example",
             "brand": f"Brand <{i}> & Co" if i == 5 else f"Brand {i}", "title": "Program", "types": types,
             "apply": methods[i % 4], "facts": facts, "category": cat, "category_from": "store", "region": "Australia" if i % 4 == 0 else "",
             "lang": "de" if i == 7 else "en", "verified_at": "2026-03-01T05:40:00Z", "checked_at": "2026-03-01T05:40:00Z",
             "first_seen": "2026-01-05", "status": "live", "note": "", "fails": 0}
        if i % 4 == 0:
            e["shop"] = {"name": e["brand"], "country": "AU", "ships_to": ["AU", "NZ"], "ships_world": False, "ships_count": 2}
        elif i % 4 == 1:
            e["shop"] = {"name": e["brand"], "country": "US", "ships_to": ["US", "CA"], "ships_world": True, "ships_count": 2}
        rows.append(e)
    # a second page on the same site and of the same kind: only one may be shown
    rows.append(dict(rows[0], id="brand-0-b", url="https://brand0.example/pages/program-application-form-long"))
    # checked but not shown: blocked twice, and a paused program
    rows.append(dict(rows[1], id="hidden-1", url="https://hidden1.example/p", host="hidden1.example", brand="Hidden One",
                     status="blocked", fails=2))
    rows.append({"url": "https://paused.example/p", "status": "closed", "fails": 1, "checked_at": "2026-03-01T05:40:00Z", "note": ""})
    return {"programs": rows, "updated_at": "2026-03-01T05:40:00Z"}


CHANGES = {"runs": [
    {"date": "2026-01-05T06:00:00Z", "checked": 400, "listed": 70, "launch": True, "added": [], "removed": []},
    {"date": "2026-03-01T05:40:00Z", "checked": 73, "listed": 72, "launch": False,
     "added": [{"brand": "Brand 3", "id": "brand-3", "types": ["ambassador", "affiliate"], "category": "coffee"}],
     "removed": [{"brand": "Old Brand", "reason": "gone"}, {"brand": "Shy Brand", "reason": "robots"}]}]}


class SiteTest(unittest.TestCase):
    def build(self, env=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data = os.path.join(self.tmp.name, "data")
        os.makedirs(data)
        with open(os.path.join(data, "programs.json"), "w") as f:
            json.dump(fixture(), f)
        with open(os.path.join(data, "changes.json"), "w") as f:
            json.dump(CHANGES, f)
        self.out = os.path.join(self.tmp.name, "_site")
        clean = {k: v for k, v in os.environ.items() if k not in ("SITE_URL", "SITE_INDEXABLE", "GOATCOUNTER_URL", "SPONSOR_URL",
                                                                 "SPONSOR_LABEL", "SPONSOR_TEXT")}
        clean.update(env or {})
        patches = [mock.patch.object(build, "PROGRAMS", os.path.join(data, "programs.json")),
                   mock.patch.object(build, "CHANGES", os.path.join(data, "changes.json")),
                   mock.patch.object(guard, "DATA", data), mock.patch.object(og, "find_chrome", lambda: None),
                   mock.patch.dict(os.environ, clean, clear=True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.summary = build.build(self.out, now=NOW)
        og.main(["--site", self.out])
        return self.out

    def read(self, rel):
        with open(os.path.join(self.out, rel), encoding="utf-8") as f:
            return f.read()

    def shown(self):
        return json.loads(self.read("assets/programs.json"))["programs"]

    def test_build_passes_its_own_guard(self):
        self.build()
        errors, counts = guard.check(self.out)
        self.assertEqual(errors, [])
        self.assertGreater(counts["cards"], counts["listings"])

    def test_only_verified_listings_are_shown_once_per_site_and_kind(self):
        self.build()
        ids = [p["id"] for p in self.shown()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("brand-0", ids)
        self.assertNotIn("brand-0-b", ids)
        self.assertNotIn("hidden-1", ids)
        self.assertEqual(len(ids), 72)
        self.assertNotIn("paused.example", self.read("data/programs.csv"))

    def test_every_listing_is_on_its_category_page_with_source_link_and_date(self):
        self.build()
        for p in self.shown():
            html = self.read(f"category/{p['c']}/index.html")
            self.assertIn(f'id="{p["id"]}"', html)
            self.assertIn(f'href="{p["u"]}" rel="noopener nofollow"', html)
        self.assertIn('<time datetime="2026-03-01T05:40:00Z">', self.read("category/coffee/index.html"))

    def test_numbers_on_a_page_match_the_rows_on_that_page(self):
        self.build()
        rows = [p for p in self.shown() if p["c"] == "coffee"]
        html = self.read("category/coffee/index.html")
        self.assertIn(f"lists {len(rows)} open programs", html)
        self.assertEqual(html.count('<li class="card"'), len(rows))
        home = self.read("index.html")
        self.assertIn(f"<b>{len(self.shown())}</b><span>open programs listed</span>", home)

    def test_text_is_escaped(self):
        self.build()
        html = self.read("category/skincare-beauty/index.html") + self.read("category/coffee/index.html") + self.read("category/snacks/index.html")
        self.assertIn("Brand &lt;5&gt; &amp; Co", html)
        self.assertNotIn("Brand <5>", html)

    def test_thin_pages_are_not_built_and_guide_links_fall_back_to_search(self):
        self.build()
        self.assertFalse(os.path.exists(os.path.join(self.out, "type", "gifting")), "no gifting listings in the fixture")
        self.assertFalse(os.path.exists(os.path.join(self.out, "category", "pets")), "six pets listings: too few for a page")
        self.assertEqual(sum(1 for p in self.shown() if p["c"] == "other"), 6, "they are listed under Other brands instead")
        self.assertTrue(os.path.exists(os.path.join(self.out, "category", "other", "index.html")))
        self.assertTrue(os.path.exists(os.path.join(self.out, "category", "coffee", "ambassador", "index.html")))
        guide = self.read("guides/creator-platforms-explained/index.html")
        self.assertIn('/apply/shopify-collabs/"', guide)
        sitemap = self.read("sitemap.xml")
        for rel in ("category/coffee/", "type/ambassador/", "lists/free-products/", "apply/shopify-collabs/", "region/australia/",
                    "guides/spot-a-fake-brand-ambassador-offer/", "changes/", "data/"):
            self.assertIn(f"/{rel}</loc>", sitemap, rel)
        self.assertNotIn("embed/widget", sitemap)
        self.assertNotIn("404", sitemap)

    def test_changes_page_and_feed_explain_additions_and_removals(self):
        self.build()
        html = self.read("changes/index.html")
        self.assertIn("The directory opened with 70 verified programs", html)
        self.assertIn("Old Brand: the page was removed", html)
        self.assertIn("Shy Brand: the site&#x27;s robots.txt asked crawlers to stay away", html)
        self.assertIn('#brand-3">Brand 3</a>', html)
        self.assertIn("<entry>", self.read("feed.xml"))

    def test_downloads_match_the_listings(self):
        self.build()
        rows = list(csv.DictReader(io.StringIO(self.read("data/programs.csv"))))
        self.assertEqual(len(rows), len(self.shown()))
        self.assertEqual(rows[0].keys() >= {"brand", "url", "verified_at", "apply_via", "ships_to"}, True)
        j = json.loads(self.read("data/programs.json"))
        self.assertEqual((j["license"], len(j["programs"])), ("CC0-1.0", len(rows)))

    def test_staged_mode_is_noindex_everywhere_with_no_sitemap(self):
        self.build({"SITE_INDEXABLE": "false"})
        self.assertFalse(os.path.exists(os.path.join(self.out, "sitemap.xml")))
        self.assertEqual(self.read("robots.txt"), "User-agent: *\nDisallow: /\n")
        self.assertEqual(self.read("urls.txt").strip(), "")
        for rel in ("index.html", "category/coffee/index.html", "guides/index.html", "methodology/index.html"):
            self.assertIn('<meta name="robots" content="noindex">', self.read(rel), rel)
        self.assertEqual(guard.check(self.out)[0], [])

    def test_one_setting_moves_the_site_to_a_custom_domain(self):
        self.build({"SITE_URL": "https://programs.example"})
        home = self.read("index.html")
        self.assertIn('<link rel="canonical" href="https://programs.example/">', home)
        self.assertIn('href="/static/style.css"', home)
        self.assertNotIn("github.io", home + self.read("sitemap.xml") + self.read("robots.txt"))
        self.assertEqual(guard.check(self.out)[0], [])

    def test_sponsor_slot_is_off_until_configured_and_always_labelled(self):
        self.build()
        self.assertNotIn('class="sponsor"', self.read("index.html"))
        self.build({"SPONSOR_URL": "https://tools.example/", "SPONSOR_LABEL": "Example Tools", "SPONSOR_TEXT": "Media kits"})
        home = self.read("index.html")
        self.assertIn('<aside class="sponsor" aria-label="Sponsor"><small>Sponsor</small><a href="https://tools.example/" rel="sponsored noopener">Example Tools</a>', home)
        self.build({"SPONSOR_URL": "javascript:alert(1)"})
        self.assertNotIn('class="sponsor"', self.read("index.html"))

    def test_guard_catches_a_private_field_or_wording_in_the_data(self):
        self.build()
        path = guard.DATA + "/programs.json"
        d = fixture()
        d["programs"][0]["attempt"] = {"status": "submitted_verified"}
        with open(path, "w") as f:
            json.dump(d, f)
        errors, _ = guard.check(self.out)
        self.assertTrue(any("unexpected field" in e for e in errors))
        self.assertTrue(any("private-record wording" in e for e in errors))

    def test_guard_catches_a_broken_link_and_too_few_listings(self):
        self.build()
        with open(os.path.join(self.out, "about", "index.html"), "a") as f:
            f.write('<a href="/america-house-brand-gifting-pipeline/nope/">x</a>')
        self.assertTrue(any("broken link" in e for e in guard.check(self.out)[0]))
        with open(os.path.join(self.out, "assets", "programs.json"), "w") as f:
            json.dump({"asof": "2026-03-01T05:40:00Z", "programs": []}, f)
        self.assertTrue(any("listings" in e for e in guard.check(self.out)[0]))

    def test_every_category_and_type_has_a_label_and_blurb(self):
        for k, _, _ in CATEGORIES:
            self.assertIn(k, build.CATEGORY_LABEL)
        for t in TYPE_ORDER:
            self.assertIn(t, build.TYPE_PLURAL)
            self.assertIn(t, build.TYPE_BLURB)
        self.assertTrue(set(build.REASON) >= verify.HARD | verify.SOFT)

    def test_page_basics(self):
        self.build()
        for dirpath, _, files in os.walk(self.out):
            for fn in files:
                if not fn.endswith(".html"):
                    continue
                html = open(os.path.join(dirpath, fn), encoding="utf-8").read()
                self.assertEqual(len(re.findall(r"<h1[ >]", html)), 0 if "embed/widget" in dirpath else 1, os.path.join(dirpath, fn))
                self.assertIn('<meta name="viewport"', html)
                self.assertNotIn("{base}", html)
                self.assertNotIn("{asof}", html)
                self.assertNotIn("{count}", html)


if __name__ == "__main__":
    unittest.main()
