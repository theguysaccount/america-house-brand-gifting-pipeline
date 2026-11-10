# LAUNCH

Machine-driven: nothing here is posted, sent or bought by anyone. The site is live at its GitHub Pages address and its
distribution runs through search.

## What is live
- https://theguysaccount.github.io/america-house-brand-gifting-pipeline/ (GitHub Pages, built by Actions).
- Sitemap, robots.txt, canonical URLs, structured data (WebSite + SearchAction, CollectionPage + ItemList, Article, Dataset,
  BreadcrumbList), Open Graph cards for every page, an Atom feed of weekly changes.
- IndexNow key published; the deploy workflow submits every URL after each deploy.
- The account's root site lists this sitemap in its `robots.txt` within a day (rebuilt daily by another repository).

## The search surfaces (what people type, and the page that answers it)
| Query pattern | Page |
|---|---|
| "[category] brand ambassador program" (coffee, skincare, supplements, tea, snacks...) | `/category/<category>/` and `/category/<category>/ambassador/` |
| "brands looking for ambassadors", "brand ambassador programs open" | `/type/ambassador/` |
| "brands that send free products", "brands that send PR packages" | `/lists/free-products/` |
| "affiliate programs for small creators", "no follower minimum" | `/lists/no-follower-minimum/`, `/type/affiliate/` |
| "Shopify Collabs brands", "brands on UpPromote" | `/apply/<platform>/` |
| "brand ambassador programs UK / Canada / Australia" | `/region/<country>/` |
| "is this brand ambassador offer a scam" | `/guides/spot-a-fake-brand-ambassador-offer/` |
| "how to disclose gifted products" | `/guides/disclose-gifted-products-and-affiliate-links/` |

A list page exists only while it has at least 8 verified listings, so there are no thin pages.

## Loops built into the product
- **Shareable searches.** Every filter state is in the address bar; "Copy link to this search" copies it.
- **Embeddable widget.** `/embed/` gives creator newsletters, courses and communities a self-updating list with a link back.
- **Open data.** CSV and JSON under CC0 with a request to link back; listed as a schema.org `Dataset`.
- **Weekly change feed.** `/feed.xml` for people who track new programs.

## First 1,000 users: the plan a machine can run
1. Search and IndexNow (running). Bing, Yandex and others receive every URL on each deploy.
2. Google: needs Search Console verification, which needs a domain or a meta tag set by the account owner (OPERATIONS.md, key 5).
3. Directory growth: more verified listings means more long-tail pages. Feed `data/candidates.txt` (OPERATIONS.md, key 4).
4. GitHub discovery: repository description and topics are set.

## For a human, later (drafts only; nothing has been sent)
- **Show HN / r/UGCcreators / r/influencermarketing post** (owner's account, their call):
  "I built a free directory of brands' own ambassador and creator application pages. A crawler re-reads every page weekly and
  drops the dead ones. 700+ programs, no sign-up, open data." Link the home page; answer how listings are verified.
- **Creator newsletters:** offer the embed widget rather than asking for a mention.
- **14-day check:** day 1 confirm Bing indexing; day 7 first scheduled re-check lands and the change log gets its first
  entry; day 14 compare outbound clicks per category (needs analytics) and add candidates in the best category.

## Custom domain
Not needed to launch. Exact DNS records and the one setting to change are in OPERATIONS.md, key 1.
