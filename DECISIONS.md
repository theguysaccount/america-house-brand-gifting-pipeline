# DECISIONS

Dated log of the choices made while turning the private gifting pipeline into a public, machine-run directory.

## 2026-11-10: what the public product is
- **A directory, not a pipeline.** The original tool found brands' forms and tracked applications sent for one creator house.
  The evaluator's read was blunt: outbound volume without reply data is a vanity metric, and automated submissions risk
  site terms. The machine-run version drops submission entirely. It publishes where to apply and lets creators apply
  themselves. That removes the terms-of-service, privacy and spam risks in one move.
- **Public name: "Creator Program Directory".** Descriptive, matches what people search for, and makes no claim of
  affiliation with any house, brand or platform. The repository keeps the idea's slug.
- **Launched indexed.** There is no public original to compete with (the prompt lists no production domain).

## 2026-11-10: what crosses from the private tool to the public repo
- **Nothing from the house's records.** No applications, receipts, attempts, reviews, contact details, mailbox checks,
  profile, shipping address or outcomes were copied, and none are in this repository's history. The private source was
  copied to a scratch folder outside the repository, never into it.
- **Seed list.** The private tool's read-only discovery cache holds the public addresses of "partnership" pages it saw on
  brand sites. Those addresses were used once, locally, as candidates. Each candidate's status in the private tool was
  ignored, so the public list cannot show which brands were ever contacted. Every candidate was then fetched fresh from the
  public web by the crawler in this repository, and only pages that passed its rules were kept (about one in four).
- **The third-party brand list is not republished.** The private tool started from a public GitHub list of Shopify stores
  with no stated licence. That list is not in this repository. The directory holds only facts this crawler observed itself.
- **Code.** The crawler is a new, small Python (standard library) implementation of the same ideas as the original
  `discover.mjs` / `network.mjs` / `providers.mjs` / `route-purpose.mjs`: obey robots.txt, stop at bot checks, tell
  application forms from newsletter, review and wholesale forms. The submission, preparation, browser-ledger and receipt
  modules were left out: they are operator tools, not part of a static site.
- **Stack change: Node + SQLite + Playwright to Python standard library.** The site must build and refresh inside GitHub
  Actions with no install step and no browser automation against other people's sites. One language, no dependencies, and
  data kept as JSON in the repository so every change is a reviewable commit.

## 2026-11-10: listing rules
- A page is listed only if its address or headline names a creator, ambassador, affiliate or gifting program **and** the page
  shows a way to apply. "Collaborations" alone qualifies only with creator wording or a creator platform link.
- Header, navigation and footer are ignored, so a footer email address or newsletter box never counts as an application.
- **"CAPTCHA-gated" means the crawler was served a bot check instead of the page.** Then the page cannot be verified, the
  crawler never tries to get around it, and the listing leaves after one grace run. A CAPTCHA widget on a form a human
  fills in is not a reason to drop a page: a human can solve it, and nothing here submits forms.
- `noindex` pages and robots.txt disallows are honoured as removal requests. That gives brands a self-serve opt-out that
  works with no human in the loop.
- Stores for alcohol, tobacco and vaping, cannabis-type products, weapons, adult products and gambling are left out. So is
  any page that states a fee or a kit purchase to join. Welcome kits and "no joining fee" wording are not treated as fees.
- Store-wide "are you 18?" pop-ups are ignored (many themes ship one unused); a 21+ gate or "legal drinking age" is not.
- Details ("the page mentions 15% commission") are pulled by conservative patterns, shown as the page's wording with the
  date checked, never as promises.
- The brand's own description is read to choose a category, and is not stored or republished.
- No per-brand pages: a page holding one link would be thin. Listings live on category, kind, platform, country and
  perk pages, each with at least 8 listings, and on the search page.

## 2026-11-10: operations
- Weekly crawl on two slots (Tuesday, Friday) because GitHub drops scheduled runs on this account; work is chosen by
  "last checked five or more days ago", so the second slot is a no-op unless the first was skipped.
- A run that would remove more than 40% of the directory writes nothing and fails: more likely a runner network fault
  or a rule bug than 300 brands closing their programs in one week.
- Suggestions from strangers are not auto-listed. A page that copies a brand and adds a form would pass a naive check and
  hurt users. The queue file `data/candidates.txt` is fed by a reviewer or a scheduled Claude routine (OPERATIONS.md, key 4).

## Questions left for Jack (none blocks the site)
1. Domain: `collabcupid.com` and `creatorcombine.com` are owned and parked; `creatorprograms.org` is unregistered. Which?
2. Should the house's own program appear in the directory? It qualifies only if it has a public application page.
3. Is a paid sponsor wanted at all? It means leaving GitHub Pages.
