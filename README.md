# Creator Program Directory

A free, public directory of the ambassador, creator, affiliate and gifting application pages that
brands publish on their own websites. Every listing is a link to the brand's own page, re-checked
every week by a small crawler. Creators apply themselves, on the brand's site. This project never
submits, fills in or automates any application.

## About the crawler (for site owners)

- User-Agent: `CreatorProgramDirectoryBot/1.0 (+https://github.com/theguysaccount/america-house-brand-gifting-pipeline)`
- It reads your `robots.txt` first and obeys it, including `Crawl-delay`.
- It requests one page per listing about once a week, with plain `GET` requests. No cookies, no
  form posts, no scripts, no logins.
- It stops at any bot check, `401`, `403` or `429` and does not try again in that run.
- It lists a page only if the page itself names a creator, ambassador, affiliate or gifting program
  and shows a way to apply. It skips pages marked `noindex`.

**To remove your page:** add this to your `robots.txt` and the listing disappears on the next run:

```
User-agent: CreatorProgramDirectoryBot
Disallow: /
```

A `noindex` robots meta tag on the page works too. You can also open an issue in this repository.

More documentation follows as the site is built.
