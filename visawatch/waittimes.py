"""Daily read of the State Department's public visa wait-times page.

The page builds its table with JavaScript, so it is opened in a headless
browser - the same thing a person does when they visit it. One visit per day,
honest User-Agent, no login, no CAPTCHA handling. If the page answers 403 or
429 the run gives up until tomorrow rather than trying anything else.

If you would rather VisaWatch did not read this page at all, set
`enabled = no` under [waittimes] in config.ini. Everything else keeps working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .sources import USER_AGENT, assert_allowed

LAST_UPDATED_RE = re.compile(r"Last\s+updated:?[ \t\"']*([A-Za-z0-9,/\- ]+)", re.IGNORECASE)

# The page mixes units: "5 Months", "3.5 Months", "< 0.5 Month", "45 Days", "2 Weeks".
WAIT_RE = re.compile(
    r"(?P<lt><\s*)?(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>month|week|day)", re.IGNORECASE
)
UNIT_DAYS = {"month": 30.0, "week": 7.0, "day": 1.0}

# Column order on the page:
#  0 City/Post | 1 B1/B2 avg | 2 B1/B2 next | 3 F/M/J next | 4 Petition-Based | 5 Crew/Transit
PETITION_COLUMN_INDEX = 4


@dataclass
class WaitTimes:
    last_updated: str
    posts: dict[str, str]

    def to_dict(self) -> dict:
        return {"last_updated": self.last_updated, "posts": self.posts}


def _norm_post(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def parse_days(value: str) -> float | None:
    """Convert any wait-time cell to a number of days so two of them can be
    compared. '5 Months' -> 150.0, '3.5 Months' -> 105.0, '45 Days' -> 45.0,
    '< 0.5 Month' -> 15.0. Returns None for 'NA' or anything without a number.
    """
    m = WAIT_RE.search(value or "")
    if m:
        days = float(m.group("num")) * UNIT_DAYS[m.group("unit").lower()]
        if m.group("lt"):
            # "< 0.5 Month" is strictly better than "0.5 Month".
            days -= 0.01
        return days
    return None


def describe_delta(old_days: float, new_days: float) -> str:
    diff = old_days - new_days
    if diff >= 30:
        return f"{diff / 30:.1f} months sooner".replace(".0 ", " ")
    return f"{diff:.0f} days sooner"


def extract(html_text: str, table_rows: list[list[str]], wanted_posts: list[str]) -> WaitTimes:
    """Pure parsing step, separated from the browser so it can be tested."""
    last_updated = ""
    m = LAST_UPDATED_RE.search(html_text or "")
    if m:
        last_updated = re.sub(r"\s+", " ", m.group(1)).strip().strip("\"'").rstrip(".,")[:60]

    wanted = {_norm_post(p): p for p in wanted_posts}
    found: dict[str, str] = {}
    for row in table_rows:
        if not row:
            continue
        key = _norm_post(row[0])
        # Tolerate the page writing "Mumbai" where config says "Mumbai (Bombay)".
        label = wanted.get(key)
        if label is None:
            for wkey, wlabel in wanted.items():
                base = wkey.split("(")[0].strip()
                if base and (key == base or key.startswith(base)):
                    label = wlabel
                    break
        if label is None:
            continue
        if len(row) > PETITION_COLUMN_INDEX:
            found[label] = re.sub(r"\s+", " ", row[PETITION_COLUMN_INDEX]).strip()
    return WaitTimes(last_updated, found)


def compare(previous: dict, current: WaitTimes) -> list[str]:
    """Human-readable list of what changed and improved."""
    changes: list[str] = []
    prev_updated = (previous or {}).get("last_updated", "")
    if prev_updated and current.last_updated and prev_updated != current.last_updated:
        changes.append(f'Page "Last updated" changed: {prev_updated} -> {current.last_updated}')

    prev_posts = (previous or {}).get("posts", {})
    for post, value in current.posts.items():
        old = prev_posts.get(post)
        if old is None:
            continue
        if old == value:
            continue
        old_days, new_days = parse_days(old), parse_days(value)
        if old_days is not None and new_days is not None and new_days < old_days:
            changes.append(
                f"IMPROVED  {post}: {old} -> {value} ({describe_delta(old_days, new_days)})"
            )
        else:
            changes.append(f"changed   {post}: {old} -> {value}")
    return changes


def fetch(url: str, wanted_posts: list[str]) -> WaitTimes:
    """Open the page once in headless Chromium and read the table."""
    assert_allowed(url)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if resp is not None and resp.status in (403, 429):
                raise RuntimeError(
                    f"HTTP {resp.status} from travel.state.gov - backing off until tomorrow."
                )
            page.wait_for_timeout(4000)
            rows = page.evaluate(
                """() => Array.from(document.querySelectorAll('table tr'))
                     .map(tr => Array.from(tr.querySelectorAll('th,td'))
                                     .map(c => (c.innerText || '').trim()))"""
            )
            body_text = page.evaluate("() => document.body.innerText")
        finally:
            browser.close()

    return extract(body_text, rows, wanted_posts)
