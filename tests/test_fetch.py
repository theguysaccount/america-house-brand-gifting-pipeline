import unittest

from directory import fetch
from directory.fetch import Client, FetchError, Response
from directory.robots import Robots


class FakeTime:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.now += s


class PacedClient(Client):
    """A client whose network is replaced by a script of (status, headers, body) per URL."""

    def __init__(self, script, **kw):
        self.t = FakeTime()
        super().__init__("TestBot/1.0 (+https://example.org)", "TestBot", clock=self.t.clock, sleep=self.t.sleep, **kw)
        self.script, self.seen = script, []

    def _once(self, url):
        host = url.split("/")[2]
        self._wait_turn(host)
        self.seen.append(url)
        out = self.script.get(url, (404, {}, b""))
        if isinstance(out, Exception):
            raise out
        return out


HTML = (200, {"content-type": "text/html"}, b"<html><title>ok</title></html>")


class FetchTest(unittest.TestCase):
    def test_robots_is_read_first_and_obeyed(self):
        c = PacedClient({"https://a.example/robots.txt": (200, {}, b"User-agent: *\nDisallow: /private\n"),
                         "https://a.example/pages/x": HTML})
        self.assertEqual(c.get("https://a.example/pages/x").status, 200)
        self.assertEqual(c.seen[0], "https://a.example/robots.txt")
        with self.assertRaises(FetchError) as cm:
            c.get("https://a.example/private/x")
        self.assertEqual(cm.exception.kind, "robots_disallowed")
        self.assertEqual(c.seen.count("https://a.example/robots.txt"), 1, "robots.txt is read once per host per run")

    def test_unreadable_robots_closes_the_site_for_this_run(self):
        for status in (403, 429, 500):
            c = PacedClient({"https://a.example/robots.txt": (status, {}, b""), "https://a.example/pages/x": HTML})
            with self.assertRaises(FetchError):
                c.get("https://a.example/pages/x")
            self.assertNotIn("https://a.example/pages/x", c.seen)
        c = PacedClient({"https://a.example/pages/x": HTML})  # 404 robots.txt: no rules published
        self.assertEqual(c.get("https://a.example/pages/x").status, 200)

    def test_requests_to_one_host_are_spaced_and_crawl_delay_is_honoured(self):
        c = PacedClient({"https://a.example/robots.txt": (200, {}, b"User-agent: *\nCrawl-delay: 9\n"),
                         "https://a.example/1": HTML, "https://a.example/2": HTML}, min_host_delay=3, global_rps=0)
        c.get("https://a.example/1")
        c.get("https://a.example/2")
        self.assertEqual(c.t.slept, [3.0, 9.0])  # default gap before the page, then the site's own Crawl-delay

    def test_crawl_delay_is_capped_and_never_below_the_default(self):
        c = PacedClient({"https://a.example/robots.txt": (200, {}, b"User-agent: *\nCrawl-delay: 600\n"),
                         "https://a.example/1": HTML, "https://a.example/2": HTML},
                        min_host_delay=3, max_crawl_delay=30, global_rps=0)
        c.get("https://a.example/1")
        c.get("https://a.example/2")
        self.assertEqual(c.t.slept[-1], 30.0)

    def test_global_rate_limit_spaces_different_hosts(self):
        script = {f"https://h{i}.example/robots.txt": (404, {}, b"") for i in range(3)}
        script.update({f"https://h{i}.example/p": HTML for i in range(3)})
        c = PacedClient(script, min_host_delay=0, global_rps=2)
        for i in range(3):
            c.get(f"https://h{i}.example/p")
        self.assertGreaterEqual(c.t.now, 2.5 - 1e-9)  # six requests at two per second

    def test_redirects_are_followed_with_a_limit_and_rechecked_against_robots(self):
        c = PacedClient({"https://a.example/old": (301, {"location": "/new"}, b""), "https://a.example/new": HTML})
        r = c.get("https://a.example/old")
        self.assertEqual((r.url, r.chain), ("https://a.example/new", ["https://a.example/old"]))
        loop = PacedClient({"https://a.example/x": (302, {"location": "/x"}, b"")})
        with self.assertRaises(FetchError) as cm:
            loop.get("https://a.example/x")
        self.assertEqual(cm.exception.kind, "redirect_limit")
        blocked = PacedClient({"https://a.example/robots.txt": (200, {}, b"User-agent: *\nDisallow: /new\n"),
                               "https://a.example/old": (301, {"location": "/new"}, b""), "https://a.example/new": HTML})
        with self.assertRaises(FetchError):
            blocked.get("https://a.example/old")

    def test_only_public_addresses_and_plain_urls(self):
        c = Client("TestBot/1.0", "TestBot", global_rps=0, min_host_delay=0)
        for bad in ("ftp://a.example/x", "https://user:pw@a.example/", "https://a.example:8443/x"):
            with self.assertRaises(FetchError) as cm:
                c._once(bad)
            self.assertEqual(cm.exception.kind, "bad_url")
        for private in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"):
            with self.assertRaises(FetchError) as cm:
                fetch.public_addresses(private, 443)
            self.assertEqual(cm.exception.kind, "private_address")

    def test_html_served_as_robots_is_not_a_rule_set(self):
        c = PacedClient({"https://a.example/robots.txt": (200, {}, b"<html><body>Just a moment... captcha</body></html>"),
                         "https://a.example/p": HTML})
        with self.assertRaises(FetchError):
            c.get("https://a.example/p")

    def test_response_text_decodes_declared_charset(self):
        r = Response("https://a.example/", 200, {"content-type": "text/html; charset=iso-8859-1"}, "café".encode("latin-1"), [])
        self.assertEqual(r.text(), "café")
        self.assertIsInstance(Robots(""), Robots)


if __name__ == "__main__":
    unittest.main()
