import unittest

from directory.robots import Robots, from_response

TOKEN = "CreatorProgramDirectoryBot"
SHOP = """
# a typical shop
User-agent: *
Disallow: /admin
Disallow: /cart
Disallow: /collections/*sort_by*
Disallow: /*?*oseid=*
Disallow: /search
Allow: /search/howto$
Sitemap: https://example.com/sitemap.xml

User-agent: Nutch
Disallow: /

User-agent: AhrefsBot
Crawl-delay: 10
"""


class RobotsTest(unittest.TestCase):
    def test_prefix_wildcard_and_anchor(self):
        r = Robots(SHOP)
        self.assertTrue(r.allowed("https://x.example/pages/ambassador", TOKEN))
        self.assertFalse(r.allowed("https://x.example/cart", TOKEN))
        self.assertFalse(r.allowed("https://x.example/collections/all?sort_by=price", TOKEN))
        self.assertFalse(r.allowed("https://x.example/a?x=1&oseid=3", TOKEN))
        self.assertTrue(r.allowed("https://x.example/search/howto", TOKEN))
        self.assertFalse(r.allowed("https://x.example/search/howto2", TOKEN))

    def test_longest_rule_wins_and_allow_wins_ties(self):
        r = Robots("User-agent: *\nDisallow: /\nAllow: /pages/")
        self.assertTrue(r.allowed("/pages/a", TOKEN))
        self.assertFalse(r.allowed("/blogs/a", TOKEN))
        self.assertTrue(Robots("User-agent: *\nDisallow: /p\nAllow: /p").allowed("/p", TOKEN))

    def test_own_group_replaces_the_wildcard_group(self):
        r = Robots(SHOP + f"\nUser-agent: {TOKEN}\nCrawl-delay: 7\nDisallow: /pages/private\n")
        self.assertFalse(r.allowed("/pages/private-offer", TOKEN))
        self.assertTrue(r.allowed("/cart", TOKEN))
        self.assertEqual(r.crawl_delay(TOKEN), 7)
        self.assertIsNone(Robots(SHOP).crawl_delay(TOKEN))

    def test_opt_out_snippet_from_the_readme_works(self):
        r = Robots(f"User-agent: *\nAllow: /\n\nUser-agent: {TOKEN}\nDisallow: /\n")
        self.assertFalse(r.allowed("/pages/ambassador", TOKEN))
        self.assertTrue(r.allowed("/pages/ambassador", "SomeOtherBot"))

    def test_empty_disallow_allows_everything(self):
        self.assertTrue(Robots("User-agent: *\nDisallow:").allowed("/x", TOKEN))
        self.assertFalse(Robots("User-agent: *\nDisallow: /").allowed("/x", TOKEN))

    def test_fetch_outcomes_are_conservative(self):
        self.assertTrue(from_response(404, "")[0].allowed("/x", TOKEN))
        for status in (401, 403, 429, 500, 503, 0):
            self.assertFalse(from_response(status, "")[0].allowed("/x", TOKEN), status)


if __name__ == "__main__":
    unittest.main()
