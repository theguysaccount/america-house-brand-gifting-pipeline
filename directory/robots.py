"""A small robots.txt parser that follows RFC 9309 (the Robots Exclusion Protocol).

Python's urllib.robotparser does prefix matching only; shops commonly publish rules with `*` and `$`
(`Disallow: /*?*oseid=*`), so this module implements the standard matching: the longest matching
rule wins, and Allow wins a tie. It also reads Crawl-delay, which this crawler honours.
"""
import re
from urllib.parse import urlsplit


def _pattern(rule):
    """Compile a robots path pattern: `*` matches any run of characters, a final `$` anchors the end."""
    anchored = rule.endswith("$")
    if anchored:
        rule = rule[:-1]
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in rule)
    return re.compile(rx + ("$" if anchored else ""))


class Robots:
    def __init__(self, text=""):
        self.groups = []  # [(set of lowercase agent tokens, [(allow, rule, regex)], crawl_delay)]
        self._parse(text or "")

    def _parse(self, text):
        agents, rules, delay, in_rules = [], [], None, False

        def flush():
            if agents:
                self.groups.append((set(agents), list(rules), delay))

        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if in_rules:  # a user-agent line after rules starts a new group
                    flush()
                    agents, rules, delay, in_rules = [], [], None, False
                agents.append(value.lower())
            elif key in ("allow", "disallow"):
                in_rules = True
                if not agents:
                    continue
                if value == "":
                    # "Disallow:" (empty) allows everything; "Allow:" (empty) matches nothing.
                    continue
                if not value.startswith(("/", "*")):
                    value = "/" + value
                rules.append((key == "allow", value, _pattern(value)))
            elif key == "crawl-delay":
                in_rules = True
                try:
                    delay = float(value)
                except ValueError:
                    pass
        flush()

    def _rules_for(self, token):
        token = token.lower()
        exact = [g for g in self.groups if any(a != "*" and a and a in token for a in g[0])]
        chosen = exact or [g for g in self.groups if "*" in g[0]]
        rules = [r for g in chosen for r in g[1]]
        delays = [g[2] for g in chosen if g[2] is not None]
        return rules, (max(delays) if delays else None)

    def allowed(self, url, token):
        """May the crawler identified by `token` fetch this URL (or path)?"""
        parts = urlsplit(url)
        target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        if target.startswith("/robots.txt"):
            return True
        rules, _ = self._rules_for(token)
        best_len, best_allow = -1, True
        for allow, rule, rx in rules:
            if rx.match(target):
                n = len(rule)
                if n > best_len or (n == best_len and allow):
                    best_len, best_allow = n, allow
        return best_allow

    def crawl_delay(self, token):
        return self._rules_for(token)[1]


ALLOW_ALL = Robots("")
DISALLOW_ALL = Robots("User-agent: *\nDisallow: /\n")


def from_response(status, text):
    """Interpret a robots.txt fetch conservatively.

    200: parse it. 404/410: no rules published, so crawling is allowed. Anything else (401, 403,
    429, 5xx, a network error passed as status 0): treat the site as closed to us for this run.
    """
    if status == 200:
        return Robots(text), "parsed"
    if status in (404, 410):
        return ALLOW_ALL, "none published"
    return DISALLOW_ALL, f"unavailable ({status})"
