"""A deliberately polite, deliberately plain HTTP client.

- Identifies itself with one honest User-Agent that links to this repository.
- Reads robots.txt first and obeys it (rules and Crawl-delay), per host, on every run.
- Waits between requests to the same host and caps the overall request rate.
- Connects only to public internet addresses, follows at most a few redirects, reads at most a
  couple of megabytes, and never sends cookies, form data or anything but GET.
- Never retries a refusal (401/403/429) and never tries to get around a bot check.
"""
import gzip
import http.client
import ipaddress
import socket
import ssl
import threading
import time
import zlib
from urllib.parse import urljoin, urlsplit

from . import robots as robots_mod


class FetchError(Exception):
    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class Response:
    def __init__(self, url, status, headers, body, chain):
        self.url, self.status, self.headers, self.body, self.chain = url, status, headers, body, chain

    def text(self):
        ctype = self.headers.get("content-type", "")
        enc = "utf-8"
        if "charset=" in ctype.lower():
            enc = ctype.lower().split("charset=", 1)[1].split(";")[0].strip().strip('"') or "utf-8"
        try:
            return self.body.decode(enc, "replace")
        except LookupError:
            return self.body.decode("utf-8", "replace")


def public_addresses(host, port):
    """Resolve a host and insist that every address is a public internet address."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError("dns", str(e))
    addrs = []
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            raise FetchError("private_address", f"{host} resolves to {ip}")
        addrs.append((family, sockaddr[0]))
    if not addrs:
        raise FetchError("dns", "no addresses")
    return addrs


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an address we already checked, while verifying the certificate for the hostname."""

    def __init__(self, host, addr, family, timeout, context):
        super().__init__(host, 443, timeout=timeout, context=context)
        self._addr, self._family, self._ctx = addr, family, context

    def connect(self):
        sock = socket.socket(self._family, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self._addr, 443))
        self.sock = self._ctx.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, addr, family, timeout):
        super().__init__(host, 80, timeout=timeout)
        self._addr, self._family = addr, family

    def connect(self):
        sock = socket.socket(self._family, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self._addr, 80))
        self.sock = sock


class Client:
    def __init__(self, user_agent, token, min_host_delay=3.0, max_crawl_delay=30.0, global_rps=2.5,
                 max_bytes=2_000_000, timeout=25, clock=time.monotonic, sleep=time.sleep):
        self.ua, self.token = user_agent, token
        self.min_host_delay, self.max_crawl_delay = min_host_delay, max_crawl_delay
        self.global_gap = 1.0 / global_rps if global_rps else 0.0
        self.max_bytes, self.timeout = max_bytes, timeout
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._host_next = {}      # host -> earliest monotonic time of its next request
        self._host_delay = {}     # host -> seconds between requests (robots Crawl-delay or the default)
        self._global_next = 0.0
        self._robots = {}         # host -> (Robots, note)
        self._ctx = ssl.create_default_context()
        self.requests_made = 0

    # --- pacing ---------------------------------------------------------------------------------
    def _wait_turn(self, host):
        with self._lock:
            now = self._clock()
            at = max(now, self._host_next.get(host, 0.0), self._global_next)
            self._global_next = at + self.global_gap
            self._host_next[host] = at + self._host_delay.get(host, self.min_host_delay)
            self.requests_made += 1
        delay = at - now
        if delay > 0:
            self._sleep(delay)

    # --- one request, no redirects ----------------------------------------------------------------
    def _once(self, url):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise FetchError("bad_url", url)
        if parts.username or parts.password or (parts.port and parts.port not in (80, 443)):
            raise FetchError("bad_url", "credentials or unusual port")
        host = parts.hostname.lower()
        try:
            host.encode("ascii")
        except UnicodeError:
            host = host.encode("idna").decode("ascii")
        port = 443 if parts.scheme == "https" else 80
        family, addr = public_addresses(host, port)[0]
        self._wait_turn(host)
        if parts.scheme == "https":
            conn = _PinnedHTTPSConnection(host, addr, family, self.timeout, self._ctx)
        else:
            conn = _PinnedHTTPConnection(host, addr, family, self.timeout)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        try:
            conn.request("GET", path, headers={
                "Host": host, "User-Agent": self.ua, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                "Accept-Encoding": "gzip", "Accept-Language": "en", "Connection": "close"})
            r = conn.getresponse()
            headers = {k.lower(): v for k, v in r.getheaders()}
            deadline = self._clock() + self.timeout * 2
            chunks, size = [], 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                chunks.append(chunk)
                if size > self.max_bytes:
                    break  # keep what we have; pages are analysed from their first megabytes
                if self._clock() > deadline:
                    raise FetchError("timeout", "body took too long")
            body = b"".join(chunks)
            if headers.get("content-encoding", "").lower() == "gzip":
                try:
                    body = gzip.decompress(body)
                except (OSError, EOFError, zlib.error):
                    try:  # a truncated gzip stream: decode what arrived
                        body = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(body)
                    except zlib.error:
                        raise FetchError("bad_encoding", "gzip")
            return r.status, headers, body
        except FetchError:
            raise
        except ssl.SSLError as e:
            raise FetchError("tls", str(e)[:200])
        except socket.timeout:
            raise FetchError("timeout", "no response in time")
        except (OSError, http.client.HTTPException) as e:
            raise FetchError("network", f"{type(e).__name__}: {e}"[:200])
        finally:
            conn.close()

    # --- robots -------------------------------------------------------------------------------------
    def robots_for(self, url):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        key = (parts.scheme, host)
        with self._lock:
            cached = self._robots.get(key)
        if cached:
            return cached
        try:
            status, headers, body = self._once(f"{parts.scheme}://{host}/robots.txt")
            hops = 0
            while status in (301, 302, 303, 307, 308) and headers.get("location") and hops < 3:
                target = urljoin(f"{parts.scheme}://{host}/robots.txt", headers["location"])
                status, headers, body = self._once(target)
                hops += 1
            text = body[:500_000].decode("utf-8", "replace") if status == 200 else ""
            if status == 200 and "<html" in text[:2000].lower():
                # A web page served in place of robots.txt (a soft 404 or a bot check): not a rule set.
                result = (robots_mod.DISALLOW_ALL, "unavailable (HTML instead of robots.txt)") \
                    if _looks_like_challenge(text) else (robots_mod.ALLOW_ALL, "none published (HTML page)")
            else:
                result = robots_mod.from_response(status, text)
        except FetchError as e:
            result = (robots_mod.DISALLOW_ALL, f"unavailable ({e.kind})")
        delay = result[0].crawl_delay(self.token)
        with self._lock:
            self._robots[key] = result
            if delay is not None:
                self._host_delay[host] = min(max(delay, self.min_host_delay), self.max_crawl_delay)
        return result

    # --- a robots-checked page fetch that follows redirects ---------------------------------------
    def get(self, url, max_redirects=4):
        """Fetch a page if robots.txt allows it. Returns a Response; raises FetchError otherwise."""
        chain = []
        for _ in range(max_redirects + 1):
            rb, note = self.robots_for(url)
            if not rb.allowed(url, self.token):
                raise FetchError("robots_disallowed", note if note.startswith("unavailable") else url)
            status, headers, body = self._once(url)
            if status in (301, 302, 303, 307, 308) and headers.get("location"):
                chain.append(url)
                url = urljoin(url, headers["location"].strip())
                continue
            return Response(url, status, headers, body, chain)
        raise FetchError("redirect_limit", url)


def _looks_like_challenge(text):
    low = text[:4000].lower()
    return any(k in low for k in ("just a moment", "captcha", "verify you are human", "access denied",
                                  "attention required", "cf-chl", "challenge-platform"))
