import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from directory import verify
from directory.fetch import FetchError, Response

from . import pages

T0 = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)


class FakeClient:
    """Serves scripted pages. `site` maps URL -> html | int status | FetchError."""

    def __init__(self, site):
        self.site, self.requests_made, self.asked = site, 0, []

    def get(self, url, max_redirects=4):
        self.requests_made += 1
        self.asked.append(url)
        v = self.site.get(url, 404)
        if isinstance(v, Exception):
            raise v
        if isinstance(v, int):
            return Response(url, v, {"content-type": "text/html"}, b"", [])
        if isinstance(v, dict):
            return Response(url, 200, {"content-type": "application/json"}, json.dumps(v).encode(), [])
        if isinstance(v, tuple):  # (final_url, html): a redirect
            return Response(v[0], 200, {"content-type": "text/html"}, v[1].encode(), [url])
        return Response(url, 200, {"content-type": "text/html"}, v.encode(), [])


def brand(n):
    host = f"brand{n}.example"
    html = pages.AMBASSADOR_FORM.replace("Maple & Finch", f"Brand {n}").replace("Maple &amp; Finch", f"Brand {n}")
    return f"https://{host}/pages/ambassador-program", html


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = {k: getattr(verify, k) for k in ("PROGRAMS", "DROPPED", "CHANGES", "STATUS", "EXCLUDE", "QUEUE")}
        for k in self._saved:
            setattr(verify, k, os.path.join(self.tmp.name, k.lower() + (".txt" if k in ("EXCLUDE", "QUEUE") else ".json")))
        self.site = dict(brand(n) for n in range(60))
        self.urls = list(self.site)

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(verify, k, v)
        self.tmp.cleanup()

    def run_at(self, days, site=None, **kw):
        client = FakeClient(self.site if site is None else site)
        summary, ok = verify.run(now=T0 + timedelta(days=days), client=client, quiet=True, **kw)
        return summary, ok, client

    def programs(self):
        with open(verify.PROGRAMS) as f:
            return {e["url"]: e for e in json.load(f)["programs"]}

    def listed(self):
        strikes = verify.load_config()["crawler"]["strikes_before_drop"]
        return {u for u, e in self.programs().items() if verify.shown(e, strikes)}

    def test_first_run_lists_verified_candidates_and_records_a_launch(self):
        summary, ok, _ = self.run_at(0, candidates=self.urls + ["https://nope.example/pages/wholesale"])
        self.assertTrue(ok)
        self.assertEqual(self.listed(), set(self.urls))
        e = self.programs()[self.urls[0]]
        self.assertEqual((e["status"], e["fails"], e["first_seen"]), ("live", 0, "2026-01-05"))
        self.assertTrue(e["id"])
        with open(verify.CHANGES) as f:
            run = json.load(f)["runs"][-1]
        self.assertTrue(run["launch"])
        self.assertEqual(run["added"], [], "the launch run does not list every program as 'added'")
        self.assertEqual(summary["results"]["live"], len(self.urls))

    def test_recent_listings_are_not_fetched_again_and_a_rerun_is_a_no_op(self):
        self.run_at(0, candidates=self.urls)
        def snapshot():
            return {k: open(getattr(verify, k)).read() for k in ("PROGRAMS", "DROPPED", "CHANGES", "STATUS")}

        before = snapshot()
        _, ok, client = self.run_at(2)
        self.assertTrue(ok)
        self.assertEqual(client.asked, [], "nothing is due two days after a full check")
        self.assertEqual(snapshot(), before, "a run with nothing due changes no file, so it makes no commit")
        _, _, client = self.run_at(7)
        self.assertEqual(len([u for u in client.asked if u.endswith("ambassador-program")]), len(self.urls))

    def test_gone_closed_and_changed_pages_leave_at_once_with_a_reason(self):
        self.run_at(0, candidates=self.urls)
        site = dict(self.site)
        site[self.urls[0]] = 404
        site[self.urls[1]] = pages.CLOSED
        site[self.urls[2]] = pages.SHOWCASE
        site[self.urls[3]] = pages.NOINDEX
        site[self.urls[4]] = FetchError("robots_disallowed", self.urls[4])
        self.run_at(7, site=site)
        self.assertEqual(self.listed(), set(self.urls[5:]))
        with open(verify.DROPPED) as f:
            reasons = {d["url"]: d["reason"] for d in json.load(f)["dropped"]}
        self.assertEqual([reasons.get(u) for u in (self.urls[0], self.urls[2], self.urls[3], self.urls[4])],
                         ["gone", "not_program", "noindex", "robots"])
        self.assertEqual(self.programs()[self.urls[1]]["status"], "closed", "a paused program is watched, not forgotten")
        with open(verify.CHANGES) as f:
            removed = json.load(f)["runs"][-1]["removed"]
        self.assertEqual(len(removed), 5)

    def test_unreadable_page_keeps_its_date_for_one_run_then_leaves_and_can_return(self):
        self.run_at(0, candidates=self.urls)
        u = self.urls[0]
        site = dict(self.site)
        site[u] = 403
        self.run_at(7, site=site)
        e = self.programs()[u]
        self.assertIn(u, self.listed())
        self.assertEqual((e["status"], e["fails"], e["verified_at"]), ("blocked", 1, "2026-01-05T06:00:00Z"))
        self.run_at(14, site=site)
        self.assertNotIn(u, self.listed())
        self.assertIn(u, self.programs(), "still watched")
        self.run_at(21)  # readable again
        self.assertIn(u, self.listed())
        self.assertEqual(self.programs()[u]["fails"], 0)

    def test_a_run_that_would_gut_the_directory_writes_nothing(self):
        self.run_at(0, candidates=self.urls)
        with open(verify.PROGRAMS) as f:
            before = f.read()
        _, ok, _ = self.run_at(7, site={})  # every page answers 404: far more likely our fault than theirs
        self.assertFalse(ok)
        with open(verify.PROGRAMS) as f:
            self.assertEqual(f.read(), before)

    def test_page_that_moves_within_the_site_keeps_its_listing(self):
        self.run_at(0, candidates=self.urls)
        u = self.urls[0]
        new = u.replace("ambassador-program", "ambassadors")
        site = dict(self.site)
        site[u] = (new, self.site[u])
        self.run_at(7, site=site)
        progs = self.programs()
        self.assertIn(new, progs)
        self.assertNotIn(u, progs)
        self.assertEqual(progs[new]["first_seen"], "2026-01-05")
        with open(verify.CHANGES) as f:
            self.assertEqual(json.load(f)["runs"][-1]["removed"], [])

    def test_redirect_to_another_site_is_not_followed_into_the_directory(self):
        site = dict(self.site)
        site[self.urls[0]] = ("https://elsewhere.example/pages/ambassador-program", self.site[self.urls[0]])
        self.run_at(0, site=site, candidates=self.urls)
        self.assertNotIn(self.urls[0], self.listed())

    def test_store_summary_sets_name_country_shipping_and_category(self):
        site = dict(self.site)
        site["https://brand0.example/meta.json"] = {
            "name": "Brand Zero Coffee", "country": "AU", "description": "Speciality coffee roasted in Melbourne.",
            "ships_to_countries": ["AU", "NZ", "FJ"], "city": "Melbourne", "myshopify_domain": "x.myshopify.com"}
        site["https://brand1.example/meta.json"] = {"name": "Barrel House", "description": "Small-batch bourbon whiskey.", "country": "US"}
        _, _, client = self.run_at(0, site=site, candidates=self.urls)
        e = self.programs()[self.urls[0]]
        self.assertEqual((e["brand"], e["region"], e["category"]), ("Brand Zero Coffee", "Australia", "coffee"))
        self.assertEqual(e["shop"], {"name": "Brand Zero Coffee", "country": "AU", "ships_to": ["AU", "NZ"], "ships_world": False, "ships_count": 3})
        self.assertNotIn("description", json.dumps(e), "the store's own description is read, never republished")
        self.assertNotIn("Melbourne", json.dumps(e))
        self.assertNotIn(self.urls[1], self.listed(), "a store that describes itself as selling spirits is not listed")
        # the summary is read again only after four weeks
        _, _, client = self.run_at(7, site=site)
        self.assertNotIn("https://brand0.example/meta.json", client.asked)
        _, _, client = self.run_at(35, site=site)
        self.assertIn("https://brand0.example/meta.json", client.asked)

    def test_excluded_sites_are_removed_and_never_fetched(self):
        self.run_at(0, candidates=self.urls)
        with open(verify.EXCLUDE, "w") as f:
            f.write("# removal requests\nbrand7.example  # asked on 2026-01-06\n")
        _, _, client = self.run_at(7)
        self.assertNotIn(self.urls[7], self.programs())
        self.assertNotIn(self.urls[7], client.asked)

    def test_public_queue_is_consumed_and_rejects_are_remembered(self):
        self.run_at(0, candidates=self.urls)
        good, html = "https://newbrand.example/pages/ambassador-program", self.site[self.urls[0]].replace("Brand 0", "New Brand")
        bad, flaky = "https://newbrand.example/pages/wholesale", "https://flaky.example/pages/ambassadors"
        site = dict(self.site)
        site.update({good: html, bad: pages.WHOLESALE, flaky: 503})
        with open(verify.QUEUE, "w") as f:
            f.write(f"# queue\n{good}\n{bad}\n{flaky}\n")
        self.run_at(1, site=site)
        self.assertIn(good, self.listed())
        self.assertEqual(verify.read_queue(), [flaky], "only the page that could not be read stays queued")
        with open(verify.DROPPED) as f:
            self.assertIn(bad, {d["url"] for d in json.load(f)["dropped"] if d.get("candidate")})
        with open(verify.CHANGES) as f:
            self.assertEqual([a["brand"] for a in json.load(f)["runs"][-1]["added"]], ["New Brand"])
        _, _, client = self.run_at(2, site=site)
        self.assertNotIn(bad, client.asked)

    def test_check_fresh(self):
        self.assertFalse(verify.check_fresh(now=T0))
        self.run_at(0, candidates=self.urls)
        self.assertTrue(verify.check_fresh(now=T0 + timedelta(days=10)))
        self.assertFalse(verify.check_fresh(now=T0 + timedelta(days=30)))

    def test_ids_are_unique_and_stable(self):
        self.run_at(0, candidates=self.urls)
        ids = {u: e["id"] for u, e in self.programs().items()}
        self.assertEqual(len(set(ids.values())), len(ids))
        self.run_at(7)
        self.assertEqual({u: e["id"] for u, e in self.programs().items()}, ids)


if __name__ == "__main__":
    unittest.main()
