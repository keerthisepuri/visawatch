"""The four things VisaWatch does: poll, digest, wait-times, test."""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone

import requests

from .matcher import match
from .notify import IST, Notifier
from .sources import fetch_feed
from . import waittimes as wt


def poll(cfg, state, notifier: Notifier, now: datetime | None = None) -> dict:
    """Read every feed once, alert on fresh matches, queue stale ones."""
    now = now or datetime.now(timezone.utc)
    now_unix = _time.time()
    session = requests.Session()
    stats = {"fetched": 0, "new": 0, "urgent": 0, "queued": 0, "failed": [], "cold_start": False}

    # First ever run: the feeds hand us ~100 back-dated items at once. Learn them
    # silently instead of firing a burst of alerts for reports already gone.
    # The flag is only set once a fetch has actually succeeded - if the first run
    # fails outright, the next one is still a cold start.
    cold_start = not state.data.get("initialized")
    stats["cold_start"] = cold_start
    any_success = False

    for name, url in cfg.sources.items():
        if state.in_backoff(name, now_unix):
            print(f"{name}: still backing off, skipping this cycle.")
            continue

        result = fetch_feed(name, url, session=session)
        if not result.ok:
            state.record_failure(name, result.error, now)
            state.set_backoff(name, result.backoff_until)
            stats["failed"].append(f"{name}: {result.error}")
            print(f"{name}: FAILED - {result.error}")
            continue

        state.record_success(name, now)
        any_success = True
        stats["fetched"] += len(result.items)

        for item in result.items:
            if state.has_seen(item.uid):
                continue          # deduplication: never alert on the same item twice
            state.mark_seen(item.uid, now)
            stats["new"] += 1

            m = match(item.text, cfg)
            if not m.matched:
                continue

            age = item.age_minutes(now)
            if cold_start:
                continue
            entry = {
                "title": item.title,
                "permalink": item.permalink,
                "source": item.source,
                "age_minutes": int(age),
                "keywords": m.summary(),
                "high_priority": m.high_priority,
            }
            if age <= cfg.urgent_max_age_minutes:
                try:
                    notifier.urgent(item, m)
                    stats["urgent"] += 1
                except Exception as exc:
                    # The push failed, so this item was never actually delivered.
                    # Un-see it and fall back to the digest, rather than losing it
                    # or aborting the rest of the cycle.
                    state.data["seen"].pop(item.uid, None)
                    state.queue_for_digest(entry)
                    stats["queued"] += 1
                    stats["failed"].append(f"push failed for {item.uid}: {exc}")
                    print(f"Push failed for {item.uid}: {exc}")
            else:
                state.queue_for_digest(entry)
                stats["queued"] += 1

    if any_success:
        state.data["initialized"] = True

    # Source-down notices, limited to the feeds this job actually polls.
    for down in state.sources_down(
        cfg.source_down_after_minutes,
        cfg.source_down_repeat_minutes,
        now,
        only=list(cfg.sources.keys()),
    ):
        try:
            notifier.source_down(down["name"], down["stale_minutes"], down["error"])
            state.mark_down_notified(down["name"], now)
        except Exception as exc:
            print(f"Could not send source-down notice: {exc}")

    state.forget_old(cfg.forget_seen_after_days)
    return stats


def check_waittimes(cfg, state, notifier: Notifier) -> list[str]:
    """Once a day. Returns the list of changes found."""
    if not cfg.waittimes_enabled:
        return []
    try:
        current = wt.fetch(cfg.waittimes_url, cfg.waittimes_posts)
    except Exception as exc:
        state.record_failure("travel_state_gov", str(exc))
        print(f"travel.state.gov: FAILED - {exc}")
        return []

    state.record_success("travel_state_gov")
    previous = state.data.get("waittimes") or {}
    changes = wt.compare(previous, current)
    state.data["waittimes"] = current.to_dict()

    # Changes are reported inside the daily digest that runs straight after this,
    # so nothing is lost if quiet hours hold the digest back.
    return changes


# ntfy rejects messages over 4 KiB, and a rejected digest would fail the whole
# daily job. Keep well inside that.
DIGEST_MAX_ENTRIES = 12
DIGEST_MAX_CHARS = 3500


def build_digest_text(cfg, entries: list[dict], waittimes: dict, changes: list[str]) -> str:
    lines = [f"VisaWatch daily digest - {datetime.now(IST).strftime('%d %b %Y, %H:%M IST')}", ""]

    if entries:
        entries = sorted(entries, key=lambda e: (not e.get("high_priority"), e.get("age_minutes", 0)))
        lines.append(f"{len(entries)} match(es) that were too old to alert on live:")
        shown = entries[:DIGEST_MAX_ENTRIES]
        for e in shown:
            star = "* " if e.get("high_priority") else "  "
            lines.append(f"{star}{e['title'][:110]}")
            lines.append(f"    {e['keywords']}")
            lines.append(f"    {e['age_minutes']} min old when seen - {e['permalink']}")
        if len(entries) > len(shown):
            lines.append(
                f"  ...and {len(entries) - len(shown)} more, newest shown first."
            )
    else:
        lines.append("Nothing matched today. VisaWatch is running normally.")

    lines.append("")
    posts = (waittimes or {}).get("posts") or {}
    if posts:
        lines.append(f"Petition-based (H/L/O/P/Q) next available - last updated "
                     f"{(waittimes or {}).get('last_updated') or 'unknown'}:")
        for post, value in posts.items():
            lines.append(f"  {post}: {value}")
    else:
        lines.append("Wait-time table: not read yet.")

    if changes:
        lines.append("")
        lines.append("Changes since yesterday:")
        lines.extend(f"  {c}" for c in changes)

    lines.append("")
    lines.append(f"Book here yourself: {cfg.portal_link}")

    text = "\n".join(lines)
    if len(text) > DIGEST_MAX_CHARS:
        text = text[:DIGEST_MAX_CHARS].rsplit("\n", 1)[0] + "\n[digest truncated]"
    return text


def send_digest(cfg, state, notifier: Notifier, changes: list[str] | None = None) -> str:
    entries = state.drain_digest()
    text = build_digest_text(cfg, entries, state.data.get("waittimes") or {}, changes or [])
    try:
        sent = notifier.digest("VisaWatch daily digest", text)
    except Exception as exc:
        print(f"Digest push failed: {exc}")
        sent = False
    if not sent:
        # Held for quiet hours - put the items back so nothing is lost.
        for entry in entries:
            state.queue_for_digest(entry)
    return text
