"""Open Graph share cards (1200x630 PNG), rendered with headless Chrome after directory.build.

  python3 -m directory.og [--site _site]
  python3 -m directory.og --default        # re-render static/og-default.png

GitHub's Ubuntu runners ship Google Chrome; locally the macOS app bundle is used. Without Chrome, or
if a render fails, a card falls back to a copy of static/og-default.png, so no page ever points at a
missing image and a Chrome problem never blocks a deploy.
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from html import escape as E

from .common import ROOT, load_config

CHROMES = [os.environ.get("CHROME", ""), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
DEFAULT = os.path.join(ROOT, "static", "og-default.png")
CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1200px;height:630px;overflow:hidden}
body{background:#0c3d35;color:#fff;font-family:"Inter","Segoe UI","Helvetica Neue",Arial,"DejaVu Sans",sans-serif;padding:60px 68px;display:flex;flex-direction:column}
.top{display:flex;align-items:center;gap:16px;font-size:28px;font-weight:700;color:#bfe9df}
.top i{display:grid;place-items:center;width:46px;height:46px;border-radius:11px;background:#5fd0b8;color:#06231d;font-style:normal;font-size:30px;font-weight:800}
h1{font-size:66px;line-height:1.07;letter-spacing:-1.6px;margin:auto 0 18px;max-height:290px;overflow:hidden}
.sub{font-size:30px;color:#bfe9df}
.foot{font-size:22px;color:#8fc7ba;margin-top:26px;border-top:2px solid #1d5a4f;padding-top:20px}
"""


def find_chrome():
    for c in CHROMES:
        if c and (os.path.exists(c) or shutil.which(c)):
            return shutil.which(c) or c
    return None


def render(chrome, name, title, subtitle, out_png):
    size = 66 if len(title) < 60 else 54 if len(title) < 90 else 46
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}h1{{font-size:{size}px}}</style></head><body>"
            f"<div class='top'><i>✓</i>{E(name)}</div><h1>{E(title)}</h1><div class='sub'>{E(subtitle)}</div>"
            f"<div class='foot'>Links to brands' own application pages · re-checked weekly · free</div></body></html>")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "card.html")
        with open(src, "w", encoding="utf-8") as f:
            f.write(html)
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--mute-audio",
               "--force-device-scale-factor=1", "--window-size=1200,630", f"--user-data-dir={os.path.join(d, 'profile')}",
               f"--screenshot={out_png}", "file://" + src]
        subprocess.run(cmd, check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(out_png) and os.path.getsize(out_png) > 1000


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--default", action="store_true")
    a = ap.parse_args(argv)
    name = load_config()["name"]
    chrome = find_chrome()
    if a.default:
        if not chrome:
            print("no Chrome found")
            return 1
        render(chrome, name, "Brands with open ambassador, creator and gifting applications", "Every page re-checked each week", DEFAULT)
        return 0
    jobs_path = os.path.join(a.site, "og-jobs.json")
    with open(jobs_path, encoding="utf-8") as f:
        jobs = {j[0]: j for j in json.load(f)}
    os.remove(jobs_path)
    out_dir = os.path.join(a.site, "og")
    os.makedirs(out_dir, exist_ok=True)
    made = 0

    def one(job):
        key, title, sub = job
        out = os.path.join(out_dir, key + ".png")
        try:
            if chrome and render(chrome, name, title, sub, out):
                return 1
        except Exception as e:  # a Chrome hiccup must not stop a deploy
            print(f"og: {key}: {type(e).__name__}")
        shutil.copyfile(DEFAULT, out)
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        made = sum(ex.map(one, jobs.values()))
    if not os.path.exists(os.path.join(out_dir, "home.png")):
        shutil.copyfile(DEFAULT, os.path.join(out_dir, "home.png"))
    print(f"og: {made} rendered, {len(jobs) - made} fell back to the default card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
