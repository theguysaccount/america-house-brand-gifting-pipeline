"""Tell IndexNow search engines (Bing, Yandex, Seznam, Naver...) which pages exist.

  python3 -m directory.indexnow --urls _site/urls.txt

The key file <key>.txt is published at the site root by directory.build. A failed submission is
reported but never fails the workflow: the site is already live. Skipped when the site is staged
(not indexable) or the URL list is empty.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .common import ROOT, load_config, site_url


def submit(urls, key, base, ua):
    host = urlparse(base).netloc
    body = json.dumps({"host": host, "key": key, "keyLocation": f"{base}/{key}.txt",
                       "urlList": [u for u in urls if urlparse(u).netloc == host][:10000]}).encode()
    for attempt in range(4):
        if attempt:
            time.sleep(30 * attempt)
        req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"IndexNow: {r.status} for {len(urls)} URLs")
                return r.status
        except urllib.error.HTTPError as e:
            print(f"IndexNow: {e.code} {e.read()[:200]!r}")
            # 403 until the engine has fetched the key file for the first time; 429 and 5xx are transient.
            if e.code not in (403, 429) and e.code < 500:
                return e.code
        except Exception as e:  # network trouble: try again
            print(f"IndexNow: {e}")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    a = ap.parse_args(argv)
    cfg = load_config()
    if not cfg.get("indexable", True) or os.environ.get("SITE_INDEXABLE", "").lower() == "false":
        print("IndexNow: skipped (site is staged, not indexable)")
        return 0
    with open(a.urls, encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip().startswith("http")]
    if not urls:
        print("IndexNow: nothing to submit")
        return 0
    with open(os.path.join(ROOT, "config", "indexnow-key.txt"), encoding="utf-8") as f:
        key = f.read().strip()
    submit(urls, key, site_url(cfg), cfg["crawler"]["user_agent"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
