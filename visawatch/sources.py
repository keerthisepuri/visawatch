"""Fetching public, unauthenticated feeds.

Hard rules enforced in code, not just by convention:
  * BLOCKED_DOMAINS can never be requested. Any attempt raises.
  * The User-Agent identifies this app honestly.
  * HTTP 429 and 403 cause a back-off, never a retry storm.
"""

from __future__ import annotations

import re
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests

USER_AGENT = (
    "VisaWatch/1.0 (personal read-only Reddit alert bot; "
    "+https://github.com/visawatch; contact via GitHub issues)"
)

# Never touched. Not by this module, not by anything else in the project.
BLOCKED_DOMAINS = (
    "usvisascheduling.com",
    "ustraveldocs.com",
    "ais.usvisa-info.com",
    "usvisa-info.com",
)

REQUEST_TIMEOUT = 25
# How long to stay away from a source after it tells us to slow down.
BACKOFF_SECONDS = {429: 30 * 60, 403: 30 * 60}
MAX_BACKOFF_SECONDS = 6 * 60 * 60


def _retry_after_seconds(resp) -> float:
    """Honour the server's own Retry-After when it sends one."""
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            return max(0.0, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
        except Exception:
            return 0.0


class BlockedDomainError(RuntimeError):
    """Raised if any code path tries to contact a visa booking portal."""


def assert_allowed(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    for blocked in BLOCKED_DOMAINS:
        if host == blocked or host.endswith("." + blocked):
            raise BlockedDomainError(
                f"Refusing to contact {host}. VisaWatch never sends requests to visa "
                f"booking portals - it only reads public discussion feeds."
            )


UNKNOWN_AGE_MINUTES = 10_000.0  # treated as old, so it goes to the digest


@dataclass
class Item:
    uid: str
    source: str
    title: str
    body: str
    permalink: str
    published: datetime
    published_known: bool = True

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"

    def age_minutes(self, now: datetime | None = None) -> float:
        # An item with no timestamp must never be treated as brand new, or every
        # malformed entry would fire a max-priority push.
        if not self.published_known:
            return UNKNOWN_AGE_MINUTES
        now = now or datetime.now(timezone.utc)
        return max(0.0, (now - self.published).total_seconds() / 60.0)


@dataclass
class FetchResult:
    name: str
    ok: bool
    items: list[Item]
    error: str = ""
    backoff_until: float = 0.0


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


AUTHOR_PREFIX_RE = re.compile(r"^/?u/[^\s]+\s+on\s+", re.IGNORECASE)


def strip_author(title: str) -> str:
    """Reddit comment titles read '/u/someuser on Slot Megathread'. The username
    is somebody else's personal data and VisaWatch has no reason to store it."""
    return AUTHOR_PREFIX_RE.sub("", title or "").strip()


def _entry_published(entry) -> tuple[datetime, bool]:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key) if hasattr(entry, "get") else getattr(entry, key, None)
        if parsed:
            return datetime.fromtimestamp(_time.mktime(parsed), tz=timezone.utc), True
    return datetime.now(timezone.utc), False


def parse_feed(name: str, raw: bytes | str) -> list[Item]:
    """Parse an Atom/RSS payload into Items. Pure function - easy to test."""
    parsed = feedparser.parse(raw)
    items: list[Item] = []
    for entry in parsed.entries:
        link = entry.get("link", "") or ""
        uid = entry.get("id") or link
        if not uid:
            continue
        body = ""
        if entry.get("content"):
            body = _strip_html(entry["content"][0].get("value", ""))
        elif entry.get("summary"):
            body = _strip_html(entry.get("summary", ""))
        published, known = _entry_published(entry)
        items.append(
            Item(
                uid=uid,
                source=name,
                title=strip_author(_strip_html(entry.get("title", ""))),
                body=body,
                permalink=link,
                published=published,
                published_known=known,
            )
        )
    return items


MAX_REDIRECTS = 4


def fetch_feed(name: str, url: str, session: requests.Session | None = None) -> FetchResult:
    """One request. No retries, no proxies, no header games.

    Redirects are followed by hand so that every hop is checked against
    BLOCKED_DOMAINS - a feed that redirected to a visa portal would otherwise
    sail straight past the guard.
    """
    session = session or requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, */*",
    }
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            assert_allowed(current)
            resp = session.get(
                current, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=False
            )
            if resp.is_redirect or resp.is_permanent_redirect:
                location = resp.headers.get("Location", "")
                if not location:
                    return FetchResult(name, False, [], "redirect with no destination")
                current = requests.compat.urljoin(current, location)
                continue
            break
        else:
            return FetchResult(name, False, [], "too many redirects")
    except BlockedDomainError:
        raise
    except Exception as exc:
        return FetchResult(name, False, [], f"network error: {exc}")

    if resp.status_code in BACKOFF_SECONDS:
        wait = max(BACKOFF_SECONDS[resp.status_code], _retry_after_seconds(resp))
        wait = min(wait, MAX_BACKOFF_SECONDS)
        return FetchResult(
            name,
            False,
            [],
            f"HTTP {resp.status_code} - backing off {int(wait / 60)} min, not retrying",
            backoff_until=_time.time() + wait,
        )
    if resp.status_code != 200:
        return FetchResult(name, False, [], f"HTTP {resp.status_code}")

    try:
        return FetchResult(name, True, parse_feed(name, resp.content))
    except Exception as exc:
        return FetchResult(name, False, [], f"could not parse feed: {exc}")
