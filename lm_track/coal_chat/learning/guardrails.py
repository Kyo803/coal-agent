"""Guardrails for autonomous learning: legality, safety, politeness.

Coal chooses its own sources, so it must police itself:
  * scheme allow-list (http/https only)
  * robots.txt honoured
  * per-host rate limiting (persisted)
  * blocked content domains/topics (malware, adult, piracy, weapons)
  * source trust scoring (so it prefers authoritative material)
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser

from . import paths

BLOCKED_DOMAINS = {
    "thepiratebay.org", "1337x.to", "rarbg.to", "torrentz2.eu",
    "pornhub.com", "xvideos.com", "xnxx.com", "redtube.com",
    "breachforums", "exploit.in", "darkweb", "onion",
}
BLOCKED_TERMS = (
    "how to make a bomb", "build an explosive", "make meth",
    "ransomware source", "keylogger download", "carding", "buy stolen",
    "child ", "csam", "genital", "porn", "warez", "crack download",
)
TRUST = {
    "wikipedia.org": 0.9, "wikimedia.org": 0.9,
    "arxiv.org": 0.95, "acm.org": 0.95, "ieee.org": 0.95,
    "github.com": 0.85, "gitlab.com": 0.8, "gutenberg.org": 0.9,
    "python.org": 0.95, "nodejs.org": 0.95, "rust-lang.org": 0.95,
    "developer.mozilla.org": 0.95, "kernel.org": 0.9, "gnu.org": 0.9,
    "stackoverflow.com": 0.75, "nature.com": 0.95, "science.org": 0.95,
    "mit.edu": 0.95, "stanford.edu": 0.95, "nist.gov": 0.95,
}
_RATE_FILE = "rate.json"
MIN_INTERVAL = 1.5  # seconds between requests to the same host


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def allowed_url(url: str) -> tuple:
    """Return (ok, reason) for a URL."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return False, "scheme not allowed"
    h = (p.hostname or "").lower()
    if not h:
        return False, "no host"
    for b in BLOCKED_DOMAINS:
        if b in h:
            return False, f"blocked domain: {b}"
    return True, "ok"


def allowed_text(text: str) -> tuple:
    low = (text or "").lower()
    for term in BLOCKED_TERMS:
        if term in low:
            return False, f"blocked term: {term}"
    return True, "ok"


def trust(url: str) -> float:
    h = _host(url)
    for dom, score in TRUST.items():
        if h == dom or h.endswith("." + dom) or dom in h:
            return score
    return 0.5


def robots_ok(url: str, user_agent: str = "Coal/1.0 (+local)") -> bool:
    try:
        rp = urllib.robotparser.RobotFileParser()
        p = urllib.parse.urlparse(url)
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True  # no robots / unreachable -> be permissive but polite


def _rate() -> dict:
    return paths.load_json(_RATE_FILE, {})


def polite_wait(url: str) -> None:
    """Sleep if we hit this host too recently."""
    h = _host(url)
    if not h:
        return
    r = _rate()
    last = float(r.get(h, 0))
    wait = MIN_INTERVAL - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    r[h] = time.time()
    # keep the file bounded
    if len(r) > 500:
        r = dict(sorted(r.items(), key=lambda kv: kv[1])[-200:])
    paths.save_json(_RATE_FILE, r)


def check(url: str, text: str | None = None) -> tuple:
    """Full gate before fetching/ingesting. Returns (ok, reason)."""
    ok, why = allowed_url(url)
    if not ok:
        return ok, why
    if text is not None:
        ok, why = allowed_text(text)
        if not ok:
            return ok, why
    return True, "ok"
