# STATE (2026-11-10)

**Live:** https://theguysaccount.github.io/america-house-brand-gifting-pipeline/ (indexed; no public original existed).

## Works
- Public directory of 730 open brand programs from 716 brands, each read from the brand's own page on 2026-11-10.
- Search and filters (category, kind, how you apply, what the page mentions, where the store ships), shareable search links.
- List pages by category, kind of program, application platform, country and perk; six guides; weekly change log and feed;
  CSV/JSON downloads (CC0); embeddable widget.
- Crawler that obeys robots.txt and Crawl-delay, stops at bot checks, honours `noindex`, and never submits anything.
- GitHub Actions: twice-weekly re-check and deploy, weekly self-test with stale-data watchdog, keep-alive. 58 tests.
  Both scheduled workflows have passed on GitHub's own schedule trigger (first on 2026-11-10), not only by hand.

## Inherited from the private pipeline (`america-house-form-pipeline`, not in this repository)
- Reused as ideas, rewritten in Python: robots handling, bot-check detection, form-purpose and route-purpose rules.
- Used once, locally: the public page addresses in its discovery cache, as candidates (2,903 checked; 747 passed).
- Left behind on purpose: submission and browser-ledger code, the SQLite ledger, every attempt, receipt, review and
  profile file, and the third-party Shopify store list (no stated licence).
- Broken in the original and not needed here: `cli.mjs` imports modules that only exist as later additions; the
  campaign folder it points at is outside the batch.

## Not done
- No analytics yet (needs a GoatCounter account), so the activation metric is not being counted.
- No new-brand discovery in the weekly job: it re-checks what is listed and whatever is in `data/candidates.txt`.
- No custom domain. Sponsor slot is off.
