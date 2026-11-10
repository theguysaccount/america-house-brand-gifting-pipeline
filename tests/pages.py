"""Synthetic pages for the tests. Invented brands only: nothing here is copied from a real site."""


def shell(title, main, *, site="Maple & Finch", lang="en", head="", footer="", header=""):
    return f"""<!doctype html><html lang="{lang}"><head><title>{title}</title>
<meta property="og:site_name" content="{site}"><meta name="description" content="Small-batch granola and snacks.">{head}</head>
<body><header><nav><a href="/">Home</a><a href="/pages/affiliate">Affiliates</a></nav>{header}
<form action="/search" role="search"><input type="search" name="q"></form></header>
<main id="MainContent">{main}</main>
<footer><form action="/contact#newsletter"><input type="hidden" name="form_type" value="customer"><input type="email" name="contact[email]"></form>
<a href="mailto:hello@example.com">Email us</a> <a href="https://www.instagram.com/example">Instagram</a>{footer}</footer></body></html>"""


AMBASSADOR_FORM = shell(
    "Ambassador Program – Maple & Finch",
    """<header class="section-header"><h1>Become a Maple &amp; Finch Ambassador</h1></header>
<p>Love our granola? Apply to join our ambassador team. Ambassadors earn 15% commission on every sale, get free products
each season and a 20% discount code to share. No minimum follower count. You must be at least 18 years old and a U.S. resident.
We work with creators on Instagram and TikTok.</p>
<form method="post" action="/contact#ContactForm"><input type="hidden" name="form_type" value="contact">
<input type="text" name="contact[name]"><input type="email" name="contact[email]">
<input type="text" name="contact[instagram]" placeholder="Instagram handle"><textarea name="contact[body]"></textarea>
<button type="submit">Apply</button></form>""")

COLLABS_PLATFORM = shell(
    "Collabs – Maple & Finch",
    """<h1>Join the Maple &amp; Finch family</h1><p>Small-batch granola.</p>
<a href="https://collabs.shopify.com/community_application/abc123">Apply now</a> <a href="/account/login">Already a member? Log in</a>""")

COLLAB_BUSINESS = shell(
    "Collaborations – Maple & Finch",
    """<h1>Collaborations</h1><p>We have teamed up with local bakeries and coffee roasters on limited editions. Get in touch to
discuss a product collaboration for your shop.</p>
<form action="/contact"><input type="hidden" name="form_type" value="contact"><input name="contact[name]">
<input type="email" name="contact[email]"><textarea name="contact[body]"></textarea></form>""")

WHOLESALE = shell(
    "Wholesale – Maple & Finch",
    """<h1>Wholesale partners</h1><p>Stock our granola in your store. Apply for a wholesale account.</p>
<form action="/contact"><input type="hidden" name="form_type" value="contact"><input name="contact[name]">
<input type="email" name="contact[email]"><textarea name="contact[body]"></textarea></form>""")

AFFILIATE_GOOGLE_FORM = shell(
    "Affiliate Program | Maple & Finch",
    """<h1>Affiliate program</h1><p>Earn commission of up to 12% when you share your link. Sign up below.</p>
<a href="https://docs.google.com/forms/d/e/1FAIpQLSexample/viewform">Fill in the application form</a>""")

CLOSED = shell(
    "Ambassadors – Maple & Finch",
    """<h1>Brand ambassadors</h1><p>Thank you for your interest. We are not currently accepting new ambassadors.
Applications are closed until spring.</p>
<form action="/contact"><input type="hidden" name="form_type" value="contact"><input name="contact[name]">
<input type="email" name="contact[email]"><textarea name="contact[body]"></textarea></form>""")

SHOWCASE = shell(
    "Our Ambassadors – Maple & Finch",
    "<h1>Meet our ambassadors</h1><p>Sam runs trails in Oregon. Priya bakes in Leeds. Follow them on Instagram.</p>")

NOINDEX = AMBASSADOR_FORM.replace("<title>", '<meta name="robots" content="noindex, nofollow"><title>')

CHALLENGE = """<!doctype html><html><head><title>Just a moment...</title></head><body>
<div id="cf-chl-widget">Checking your browser before accessing the site.</div></body></html>"""

PAY_TO_JOIN = shell(
    "Ambassador – Maple & Finch",
    """<h1>Become an ambassador</h1><p>Apply today and launch your business. Starter Kit $ 199 gets you everything you need to
join. Build your downline and earn.</p>
<form action="/contact"><input type="hidden" name="form_type" value="contact"><input name="contact[name]">
<input type="email" name="contact[email]"><textarea name="contact[body]"></textarea></form>""")

NO_FEE = AMBASSADOR_FORM.replace("No minimum follower count.", "There is no joining fee. Every ambassador receives a welcome Ambassador Pack.")

RESTRICTED = shell(
    "Ambassador Program – Cedar Hollow Distillery", AMBASSADOR_FORM.split('<main id="MainContent">')[1].split("</main>")[0],
    site="Cedar Hollow Distillery", head='<meta name="keywords" content="x">').replace(
        "Small-batch granola and snacks.", "Small-batch bourbon whiskey and gin.")

LOGIN = shell(
    "Affiliate login – Maple & Finch",
    """<h1>Affiliate login</h1><form><input type="email" name="email"><input type="password" name="password"></form>""")

NEWSLETTER_ONLY = shell(
    "Ambassador Program – Maple & Finch",
    """<h1>Ambassador program</h1><p>Coming soon. Join our newsletter to hear first.</p>
<form action="/contact#newsletter" id="newsletter-form"><input type="hidden" name="form_type" value="customer">
<input type="text" name="contact[first_name]"><input type="text" name="contact[last_name]"><input type="email" name="contact[email]"></form>""")

PORTAL = shell(
    "Ambassadors – Maple & Finch",
    """<h1>Ambassador program</h1><p>Share Maple &amp; Finch and earn.</p>
<a href="https://ambassadors.maplefinch.example/register">Apply now</a>""")

WIDGET_OUTSIDE_MAIN = shell(
    "Ambassador Program – Maple & Finch", "<h1>Ambassador program</h1><p>Details soon.</p>",
    footer='<div class="klaviyo-form-AbC123"></div>')

GERMAN = shell(
    "Influencer werden – Ahorn & Fink",
    """<h1>Influencer-Programm</h1><p>Werde Teil unseres Teams. Jetzt bewerben und kostenlose Produkte erhalten.</p>
<form action="/contact"><input type="hidden" name="form_type" value="contact"><input name="contact[name]">
<input type="email" name="contact[email]"><input name="contact[instagram]"><textarea name="contact[body]"></textarea></form>""",
    site="Ahorn & Fink", lang="de")
