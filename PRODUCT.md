# PRODUCT

**Creator Program Directory**: brands with open ambassador, creator, affiliate and gifting applications, re-checked every week.

## The user
A creator, UGC maker or small creator house (a few hundred to tens of thousands of followers) who wants products, commission
or paid work from consumer brands. Also talent managers who apply on behalf of several creators.

## The painful job
Finding which brands take applications at all. The answer is scattered across thousands of brand websites, usually one link
in a footer. People spend hours searching "brand ambassador program" and land on stale listicles, paid marketplaces that only
show brands already recruiting there, or scam offers in their DMs.

## The promise
One page that lists the application pages brands publish themselves, each one read by a crawler in the last week, with how
you apply and what the page says you get. You apply on the brand's own site. Nothing is submitted for you.

## The wedge
Search. People type "[category] brand ambassador program", "brands that send free products", "affiliate programs for small
creators". Each of those is a page here, built from verified listings, with a date on it. No competitor re-checks its list
weekly and shows the date.

## Why now
Brands moved their creator programs onto self-serve tools (Shopify Collabs, UpPromote, GoAffPro and similar), so thousands of
small brands now publish a standing application page that a crawler can find and verify.

## The one activation metric
Outbound clicks on "Open the page" per visitor (did the visitor reach a brand's application page?). Instrumented as
GoatCounter events `out-<listing id>`; counted once `GOATCOUNTER_URL` is set (OPERATIONS.md, key 3).

## First revenue event
One clearly labelled sponsor slot for a creator tool (media-kit builder, invoicing, link-in-bio). Off until
`SPONSOR_URL` is set. GitHub Pages is non-commercial, so a paying sponsor means moving hosting first (OPERATIONS.md, key 2).

## What v1 deliberately does not do
- No applying on anyone's behalf, no form filling, no outreach, no accounts, no email capture.
- No ratings of brands, no claims about who gets accepted or what ships.
- No generic contact forms, wholesale pages, donation or sponsorship-request pages.
- No alcohol, tobacco, cannabis, weapons, adult or gambling stores, and no pay-to-join "programs".
- Nothing from any private outreach record: only what a brand's public page says, re-read by the crawler.
