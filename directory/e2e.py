"""Load the built site in headless Chrome and check that the search actually works.

  python3 -m directory.e2e [_site]

Serves the build at the same path it has on the web, opens the home page, a filtered search and the
embeddable widget, and compares what the browser rendered with the data file. Skips (exit 0, with a
warning) when no Chrome is installed, so it never blocks a machine that cannot run it; GitHub's
runners have Chrome.
"""
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import quote, urlsplit

from .common import ROOT, load_config, site_url
from .og import find_chrome


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def dump(chrome, url, profile):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--mute-audio", f"--user-data-dir={profile}",
           "--virtual-time-budget=9000", "--dump-dom", url]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = os.path.abspath(argv[0] if argv else os.path.join(ROOT, "_site"))
    chrome = find_chrome()
    if not chrome:
        print("::warning::e2e skipped: no Chrome found")
        return 0
    base = urlsplit(site_url(load_config())).path.strip("/")
    with open(os.path.join(site_dir, "assets", "programs.json"), encoding="utf-8") as f:
        programs = json.load(f)["programs"]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        web = os.path.join(tmp, "web")
        os.makedirs(os.path.dirname(os.path.join(web, base)) if base else web, exist_ok=True)
        if base:
            os.symlink(site_dir, os.path.join(web, base))
        else:
            os.rmdir(web)
            os.symlink(site_dir, web)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=web))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        root = f"http://127.0.0.1:{srv.server_address[1]}/{base + '/' if base else ''}"
        try:
            n = 0

            def page(path):
                nonlocal n
                n += 1
                return dump(chrome, root + path, os.path.join(tmp, f"profile{n}"))

            def cards(html, container):
                m = re.search(rf'<ul class="cards" id="{container}">(.*?)</ul>', html, re.S)
                return re.findall(r'<li class="card" id="([^"]+)"', m.group(1)) if m else []

            home = page("")
            got = cards(home, "results")
            m = re.search(r'id="count"[^>]*>(\d[\d,]*) programs?', home)
            if not got:
                problems.append("home: the finder rendered no cards")
            if not m or int(m.group(1).replace(",", "")) != len(programs):
                problems.append(f"home: count shows {m.group(1) if m else 'nothing'}, data has {len(programs)}")
            if 'id="finder" hidden' in home:
                problems.append("home: the finder stayed hidden")
            pick = programs[len(programs) // 2]
            word = max(re.findall(r"[A-Za-z0-9]+", pick["b"]) or [pick["h"]], key=len)
            want = [p["id"] for p in programs if word.lower() in
                    f'{p["b"]} {p["h"]}'.lower()]
            found = cards(page("?q=" + quote(word)), "results")
            if pick["id"] not in found or not set(found) >= set(want[:48]) and len(want) <= 48:
                problems.append(f"search for {word!r}: expected {pick['id']} among {len(want)} matches, got {len(found)} cards")
            if len(found) >= len(programs) and len(programs) > 60:
                problems.append(f"search for {word!r} did not narrow the list")
            cat = pick["c"]
            in_cat = [p["id"] for p in programs if p["c"] == cat]
            found = cards(page("?cat=" + quote(cat)), "results")
            if not found or not set(found) <= set(in_cat):
                problems.append(f"category filter {cat!r}: cards outside the category, or none")
            widget = cards(page(f"embed/widget/?category={quote(cat)}&n=5"), "embed-list")
            if not widget or len(widget) > 5 or not set(widget) <= set(in_cat):
                problems.append(f"embed widget: expected up to 5 {cat} cards, got {len(widget)}")
        finally:
            srv.shutdown()
    for p in problems:
        print("E2E", p)
    print(f"e2e: home, search, category filter and embed checked in Chrome; {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
