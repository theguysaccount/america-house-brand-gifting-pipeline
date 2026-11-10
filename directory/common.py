"""Shared helpers: paths, config, time, JSON files, slugs."""
import json
import os
import re
import unicodedata
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CONFIG = os.path.join(ROOT, "config", "site.json")


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def site_url(cfg=None):
    """The one base-URL setting: env SITE_URL (set by the workflow or a repo variable) or the config default."""
    cfg = cfg or load_config()
    return (os.environ.get("SITE_URL") or cfg["default_url"]).rstrip("/")


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, obj, compact=False):
    """Write JSON atomically, so a crash never leaves a half-written data file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def human_date(dt):
    """'November 10, 2026' (no zero padding, same on every platform)."""
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


_TWO_LEVEL = {"co.uk", "org.uk", "com.au", "net.au", "org.au", "co.nz", "co.za", "com.br", "co.in", "co.jp", "com.sg",
              "com.mx", "com.hk", "co.il", "com.my", "com.ph", "com.tr", "com.pk", "co.kr", "com.tw", "com.co", "com.ar"}


def site_key(host):
    """Registrable-domain approximation: 'shop.brand.co.uk' -> 'brand.co.uk'."""
    labels = (host or "").lower().strip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])
