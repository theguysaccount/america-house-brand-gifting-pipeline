# OPERATIONS

Everything runs on GitHub Actions in `theguysaccount/america-house-brand-gifting-pipeline`. No human has a job here.
Live site: https://theguysaccount.github.io/america-house-brand-gifting-pipeline/ (indexed).

## Automated jobs

| Workflow | When (UTC) | What it does | How it fails safely |
|---|---|---|---|
| **Verify and deploy** `refresh.yml` | Tue 05:23 and Fri 05:37; every push to `main`; by hand | On schedule or by hand: `directory.verify` re-reads every listed page whose last check is 5+ days old (robots.txt first, one page per site, about 2.5 requests a second overall), plus anything in `data/candidates.txt`. Then: tests, build, share cards, guard, headless-Chrome check of the search, commit `data/`, deploy to Pages, check the live site, ping IndexNow. A push skips the crawl and just rebuilds. | The second weekly slot is a no-op unless GitHub skipped the first (work is chosen by age, not by day). A page that cannot be read keeps its older "verified" date for one more run, then is hidden until it can be read. A run that would remove more than 40% of listings, or leave fewer than 50, **writes nothing and fails**. Any failed step before "deploy" leaves the last good site live. IndexNow failures are ignored. |
| **Weekly self-test** `selftest.yml` | Thu 07:41; by hand | Runs the tests. Fetches every URL in the live sitemap plus the downloads, feed, share image and key file. Checks each page carries its as-of date and that the listings were verified within 16 days. If they are stale it starts **Verify and deploy**. Runs the keep-alive. | Read-only against this site only. It never touches a brand's site. A failure emails the repository owner; the site is unchanged. |
| **Tests** `test.yml` | Pull requests, pushes to other branches | Tests on Python 3.9 and 3.12, build, guard, browser check. | Never deploys. |

**Keep-alive.** GitHub pauses schedules in a public repository after 60 days without a commit. The weekly data commit
normally prevents that. As a backstop every scheduled run calls `.github/scripts/keepalive.sh`, which re-enables any
workflow whose state is `disabled_inactivity` and pushes an empty commit if `main` has been quiet for 45 days.

**GitHub skips scheduled runs on this account.** Nothing depends on a run firing at a set time: there are two weekly slots,
every run is safe to repeat, and the self-test starts a refresh when the data is stale.

## What to watch

- **Actions tab.** A red "Verify and deploy" means the site was not updated that time; the previous site is still live.
  Read the failing step:
  - *Re-check listings* says `REFUSING to write`: the run would have removed too much. Usually the runner's network or a
    site-wide block. Re-run it. If it repeats, look at `results` in the log to see which outcome spiked.
  - *Guard* lists each problem (missing page, broken link, a field that should not be public).
  - *Browser check* means the search page did not render what the data says.
- **`data/status.json`**: `last_success`, and `last_summary` with the count of each outcome
  (`live`, `blocked`, `gone`, `not_program`, `closed`, `robots`, `noindex`, `moved`, `error`).
  A rising `blocked` count means brand sites are refusing the runner's addresses. Nothing here tries to get around that:
  those listings age out, and the directory shrinks honestly.
- **`data/changes.json`** and the site's `/changes/` page: what each run added and removed, with reasons.
- **Issues** labelled `listing` (a brand asks for a correction or removal) and `suggestion` (someone suggests a page).
  Nobody is notified of these except the repository owner's GitHub email.
- The weekly self-test's email is the only alert. There is no other monitoring.

## Manual levers (all optional)

- **Run now:** Actions → Verify and deploy → Run workflow. Untick "crawl" to only rebuild; tick "all" to re-check
  everything; set "limit" to try a few pages.
- **Remove a site for good:** add its domain to `config/exclude.txt` (one per line, `#` comments allowed) and push.
  It is dropped at the next run and never fetched again.
- **Add pages:** put addresses in `data/candidates.txt`, one per line, and push or wait. The next crawl tries them, lists
  the ones that pass, remembers the ones that fail, and empties the file.
- **Change pace or thresholds:** `config/site.json` (`global_requests_per_second`, `min_host_delay_seconds`,
  `recheck_after_days`, `strikes_before_drop`, `max_drop_share`, `min_listings_to_publish`).
- **Stage the site (hide from search):** `gh variable set SITE_INDEXABLE --body false -R theguysaccount/america-house-brand-gifting-pipeline`
  (or set `"indexable": false` in `config/site.json`), then run the workflow. Pages get `noindex`, the sitemap disappears, IndexNow is skipped.

## Keys Jack can turn later

None is needed for the site to work.

### 1. Custom domain
Candidates, checked 2026-11-10: **`collabcupid.com`** (owned at Namecheap since 2020, auto-renew on, parked) and
**`creatorcombine.com`** (owned, auto-renew on, parked). Unregistered: `creatorprograms.org`,
`creatorprogramdirectory.com` (buying needs Jack's OK). `creatorships.org` is owned but already serves another site.

1. Namecheap → Domain List → the domain → Advanced DNS. Remove the parking records, then add:
   - `A` `@` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` (four records)
   - `CNAME` `www` → `theguysaccount.github.io.`
2. GitHub → repository Settings → Pages → Custom domain → enter the domain → Save. Wait for the certificate, then tick
   "Enforce HTTPS". (CLI: `gh api -X PUT repos/theguysaccount/america-house-brand-gifting-pipeline/pages -f cname=<domain>`,
   later `-F https_enforced=true`.)
3. Set the one base-URL setting:
   `gh variable set SITE_URL --body "https://<domain>" -R theguysaccount/america-house-brand-gifting-pipeline`
4. Actions → Verify and deploy → Run workflow with "crawl" unticked. Canonical links, sitemap, share cards, the embed
   snippet and IndexNow all follow `SITE_URL`. GitHub redirects the old `github.io` address to the domain.
5. Recommended: verify the domain for the account (GitHub → Settings → Pages → Add a domain) so nobody else can claim it.

### 2. Money: the sponsor slot
One labelled box ("Sponsor") on the home page and every list page, off until configured:

```
gh variable set SPONSOR_URL   --body "https://example-creator-tool.com/?ref=directory" -R theguysaccount/america-house-brand-gifting-pipeline
gh variable set SPONSOR_LABEL --body "Example Media Kits"
gh variable set SPONSOR_TEXT  --body "Make a media kit in five minutes"
```

Then run the workflow. The link is rendered with `rel="sponsored"`. Only `https://` addresses are accepted.
**GitHub Pages is for non-commercial use.** Before a sponsor pays, move hosting: create a Cloudflare Pages (or Netlify)
project that builds this repository with `python3 -m directory.build --site _site`, point the domain there, and keep the
Actions crawl committing `data/` (the host rebuilds on each commit). That needs an account, so it was not done.
Never sell placement inside the listings: the directory's value is that order and inclusion are not for sale.

### 3. Analytics (the activation metric)
Create a free GoatCounter site, then:
`gh variable set GOATCOUNTER_URL --body "https://<code>.goatcounter.com/count" -R theguysaccount/america-house-brand-gifting-pipeline`
and run the workflow. Page views, outbound clicks (`out-<listing id>`) and shared searches (`share-search`) start
recording. Needs an account, so it was not done. Until then there are no usage numbers.

### 4. Growing the directory (a scheduled Claude routine)
The weekly job only re-checks. New brands arrive through `data/candidates.txt`. Suggested weekly routine, which needs no
secrets (it opens a pull request):

> In `theguysaccount/america-house-brand-gifting-pipeline`: read open issues labelled `suggestion` and collect the
> addresses they propose. Then find up to 40 more pages where a consumer brand invites ambassador, creator, affiliate or
> gifting applications on its own website (search for phrases such as "become an ambassador", "creator program",
> "affiliate program" plus a product category that has few listings in `data/programs.json`). Skip marketplaces, agencies,
> alcohol, tobacco, cannabis, weapons, adult and gambling brands, and anything that asks for a fee. Skip any address already
> in `data/programs.json` or `data/dropped.json`. Append the addresses to `data/candidates.txt`, one per line, open a pull
> request titled "Candidates: <date>", and close the suggestion issues you used with a note. Do not edit any other file.

The crawler still decides what is listed, so a bad candidate costs one request. Suggestions from strangers are not
auto-queued on purpose: a page that imitates a brand could pass an automatic check.

### 5. Search Console
Bing and Yandex already receive every page through IndexNow. For Google: verify the property (a DNS TXT record once a
custom domain exists, or the HTML-tag method) and submit `/sitemap.xml`. Needs the Google account owner.

### 6. Removal and correction requests
Brands can remove themselves through `robots.txt` or `noindex` with no human involved. Requests filed as issues need a
person (or the routine above, extended) to add the domain to `config/exclude.txt`.

## Costs
$0. Public repository, GitHub-hosted runners (about 15 minutes per weekly crawl), GitHub Pages, no paid services, no keys.

## What this project will never do
Submit or fill in an application, solve or bypass a CAPTCHA or bot check, disguise its crawler, publish contact details,
or publish anything from a private outreach record. `directory.guard` fails the build if a field outside the public
schema, or wording from such records, appears in the data or the site.
