import unittest

from directory import classify

from . import pages

URL = "https://maplefinch.example/pages/ambassador-program"


class ClassifyTest(unittest.TestCase):
    def test_ambassador_page_with_application_form_is_listed(self):
        r = classify.analyse(pages.AMBASSADOR_FORM, URL)
        self.assertTrue(r["is_program"], r["reason"])
        self.assertIn("ambassador", r["types"])
        self.assertEqual(r["apply"]["method"], "form")
        self.assertEqual(r["brand"], "Maple & Finch")
        f = r["facts"]
        self.assertEqual((f["commission_pct"], f["discount_pct"], f["min_age"], f["residents"]), (15, 20, 18, "US"))
        self.assertTrue(f["free_product"])
        self.assertEqual(f["platforms"], ["instagram", "tiktok"])

    def test_footer_and_header_never_count(self):
        # The footer holds a mailto link and Instagram; the header holds an "Affiliates" link.
        r = classify.analyse(pages.SHOWCASE, "https://maplefinch.example/pages/our-ambassadors")
        self.assertFalse(r["is_program"])
        self.assertEqual(r["reason"], "page names a program but shows no way to apply")
        r = classify.analyse(pages.WIDGET_OUTSIDE_MAIN, URL)
        self.assertFalse(r["is_program"])

    def test_platform_link_is_the_way_to_apply(self):
        r = classify.analyse(pages.COLLABS_PLATFORM, "https://maplefinch.example/pages/collab")
        self.assertTrue(r["is_program"], r["reason"])
        self.assertEqual(r["apply"]["label"], "Shopify Collabs")
        self.assertEqual(r["types"], ["creator", "collab"])

    def test_business_collaboration_page_is_not_listed(self):
        r = classify.analyse(pages.COLLAB_BUSINESS, "https://maplefinch.example/pages/collaborations")
        self.assertFalse(r["is_program"])

    def test_wholesale_careers_contact_and_login_pages_are_not_listed(self):
        self.assertFalse(classify.analyse(pages.WHOLESALE, "https://maplefinch.example/pages/wholesale-partners")["is_program"])
        self.assertFalse(classify.analyse(pages.AMBASSADOR_FORM, "https://maplefinch.example/pages/contact")["is_program"])
        self.assertFalse(classify.analyse(pages.LOGIN, "https://maplefinch.example/apps/affiliate/login")["is_program"])
        self.assertFalse(classify.analyse(pages.LOGIN, "https://maplefinch.example/pages/affiliate-area")["is_program"])

    def test_hosted_form_link(self):
        r = classify.analyse(pages.AFFILIATE_GOOGLE_FORM, "https://maplefinch.example/pages/affiliate")
        self.assertTrue(r["is_program"], r["reason"])
        self.assertEqual((r["apply"]["method"], r["apply"]["label"]), ("external_form", "Google Forms"))
        self.assertEqual(r["facts"]["commission_pct"], 12)

    def test_portal_on_the_brands_own_site(self):
        r = classify.analyse(pages.PORTAL, "https://www.maplefinch.example/pages/ambassadors")
        self.assertTrue(r["is_program"], r["reason"])
        self.assertEqual(r["apply"]["method"], "portal")

    def test_closed_program_is_reported_closed(self):
        r = classify.analyse(pages.CLOSED, "https://maplefinch.example/pages/ambassadors")
        self.assertTrue(r["closed"])
        self.assertFalse(r["is_program"])

    def test_noindex_and_bot_checks_are_respected(self):
        self.assertTrue(classify.analyse(pages.NOINDEX, URL)["noindex"])
        self.assertTrue(classify.analyse(pages.CHALLENGE, URL)["challenge"])

    def test_newsletter_box_is_not_an_application(self):
        self.assertFalse(classify.analyse(pages.NEWSLETTER_ONLY, URL)["is_program"])

    def test_pay_to_join_is_excluded_but_free_welcome_kits_are_fine(self):
        r = classify.analyse(pages.PAY_TO_JOIN, URL)
        self.assertFalse(r["is_program"])
        self.assertIn("pay", r["reason"])
        self.assertTrue(classify.analyse(pages.NO_FEE, URL)["is_program"])
        for ok in ("NO joining fee - start right away", "we will send you an Ambassador Pack with brand guidelines",
                   "Free starter kit: all approved creators receive three flavours", "There is no membership fee of any kind"):
            self.assertFalse(classify.pay_to_join(ok), ok)
        for bad in ("Starter Kit $ 799 Only", "Pay your listing fee via invoice", "pay $49 to join the team"):
            self.assertTrue(classify.pay_to_join(bad), bad)

    def test_age_restricted_stores_are_excluded(self):
        r = classify.analyse(pages.RESTRICTED, "https://cedarhollow.example/pages/ambassador-program")
        self.assertFalse(r["is_program"])
        self.assertEqual(r["reason"], "age-restricted store or product")
        self.assertFalse(classify.restricted("Fever Hill ginger beer and tonic", "alcohol-free skincare"))
        self.assertTrue(classify.restricted("craft beer club"))

    def test_non_english_page_keeps_its_language(self):
        r = classify.analyse(pages.GERMAN, "https://ahornfink.example/pages/influencer")
        self.assertTrue(r["is_program"], r["reason"])
        self.assertEqual(r["lang"], "de")
        self.assertIn("creator", r["types"])

    def test_categories_follow_the_stores_own_description(self):
        c = classify.categorize
        self.assertEqual(c("Tall Pine Coffee", "tallpinecoffee.example", "Ambassadors", "Speciality coffee roasted in small batches."), "coffee")
        self.assertEqual(c("Honeycomb Co", "honeycombco.example", "Affiliates", "Natural eczema cream made with honey and oatmeal."), "skincare-beauty")
        self.assertEqual(c("Zyx", "zyx.example", "Program", ""), "other")

    def test_brand_name_prefers_the_sites_own_name(self):
        r = classify.analyse(pages.AMBASSADOR_FORM.replace('content="Maple & Finch"', 'content="Maple & Finch | Ambassador Program"'), URL)
        self.assertEqual(r["brand"], "Maple & Finch")

    def test_facts_are_bounded(self):
        f = classify.extract_facts("Earn 95% commission! at least 12 followers. 99% off")
        self.assertNotIn("commission_pct", f)
        self.assertNotIn("followers_min", f)
        self.assertNotIn("discount_pct", f)
        self.assertEqual(classify.extract_facts("open to creators with 5k+ followers on YouTube")["followers_min"], 5000)


if __name__ == "__main__":
    unittest.main()
