"""The four things VisaWatch does: poll, digest, wait-times, test."""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone

import requests

from .matcher import match
from .notify import IST, Notifier, in_quiet_hours
from .sources import fetch_feed
from . import waittimes as wt
from . import windows as win


# Reddit rate-limits data-centre IPs hard: measured live, the FIRST request of a
# cycle succeeds and the second gets HTTP 429 even six seconds later. So we make
# exactly one request per cycle.
#
# That is a hard budget of 12 requests an hour, so it has to be spent where the
# time-critical reports are. The comments feed carries the megathread slot
# reports, so it takes three cycles out of every four - a read every ~7 minutes.
# The fourth cycle rotates through the other three feeds, so each of those is
# read about once an hour. That is fine: they carry whole posts rather than
# live comments, and a post found an hour late belongs in the digest anyway.
PRIORITY_SOURCE = "reddit_comments"
PRIORITY_SHARE = 3       # out of every PRIORITY_CYCLE cycles
PRIORITY_CYCLE = 4
FEEDS_PER_CYCLE = 1
SECONDS_BETWEEN_REQUESTS = 6


def select_sources(cfg, state) -> dict:
    """Pick which feed to read this cycle."""
    per_cycle = int(getattr(cfg, "feeds_per_cycle", FEEDS_PER_CYCLE))
    names = list(cfg.sources)
    if per_cycle <= 0 or per_cycle >= len(names):
        return dict(cfg.sources)

    cycle = int(state.data.get("cycle", 0))
    state.data["cycle"] = cycle + 1

    others = [n for n in names if n != PRIORITY_SOURCE]
    has_priority = PRIORITY_SOURCE in names

    chosen: list[str] = []
    if has_priority and (cycle % PRIORITY_CYCLE) < PRIORITY_SHARE:
        chosen.append(PRIORITY_SOURCE)
    elif others:
        chosen.append(others[(cycle // PRIORITY_CYCLE) % len(others)])

    # Top up if the caller asked for more than one feed per cycle.
    pool = [n for n in names if n not in chosen]
    while len(chosen) < per_cycle and pool:
        chosen.append(pool.pop(0))
    return {n: cfg.sources[n] for n in chosen}


MIN_FAILURES_BEFORE_ALARM = 3


def _parse_ts(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def failing_sources(cfg, state, now: datetime) -> list[dict]:
    """Sources that are genuinely broken.

    A feed is 'down' only when every recent attempt to read it FAILED - not when
    it simply has not come up in the rotation yet. The old rule fired whenever a
    feed had not been read for an hour, which with a rotating schedule meant a
    constant stream of false 'source is down' alerts for feeds that were fine.
    """
    down = []
    for name in cfg.sources:
        rec = state.data.get("sources", {}).get(name, {})
        fails = int(rec.get("consecutive_failures", 0))
        since = _parse_ts(rec.get("failing_since"))
        if fails < MIN_FAILURES_BEFORE_ALARM or since is None:
            continue
        broken_minutes = (now - since).total_seconds() / 60.0
        if broken_minutes < cfg.source_down_after_minutes:
            continue
        last_notice = _parse_ts(rec.get("last_down_notice"))
        if last_notice and (now - last_notice).total_seconds() / 60.0 < cfg.source_down_repeat_minutes:
            continue
        down.append(
            {
                "name": name,
                "stale_minutes": int(broken_minutes),
                "error": f"{rec.get('last_error', 'unknown')} ({fails} failed attempts in a row)",
            }
        )
    return down


def send_headsup(cfg, state, notifier: Notifier, now_ist: datetime | None = None) -> bool:
    """Warn just before a likely release window, so you are logged in and
    refreshing rather than reacting to an alert that arrives too late."""
    wcfg = getattr(cfg, "_window_config", None) or win.load_window_config()
    cfg._window_config = wcfg

    now_ist = now_ist or datetime.now(IST)
    window = win.due_window(wcfg, state, now_ist)
    if window is None:
        return False

    # The morning window sits inside normal quiet hours. Suppressing it would
    # defeat the point, so heads-ups bypass quiet hours by default - but that is
    # a config switch, because being woken at 05:40 every day is a real cost.
    if not wcfg.bypass_quiet_hours and in_quiet_hours(cfg, now_ist):
        print(f"Quiet hours - holding heads-up for {window.label()}.")
        return False

    title, body = win.message(window, cfg, now_ist, wcfg.lead_minutes)
    try:
        notifier._push(title, body, cfg.urgent_priority, "alarm_clock", click=cfg.portal_link)
        win.mark_sent(state, window, now_ist, wcfg.lead_minutes)
        print(f"Heads-up sent for {window.label()}.")
        return True
    except Exception as exc:
        print(f"Heads-up push failed: {exc}")
        return False


def poll(cfg, state, notifier: Notifier, now: datetime | None = None) -> dict:
    """Read every feed once, alert on fresh matches, queue stale ones."""
    now = now or datetime.now(timezone.utc)
    now_unix = _time.time()
    session = requests.Session()
    stats = {"fetched": 0, "new": 0, "urgent": 0, "queued": 0, "requests": 0,
             "failed": [], "cold_start": False}

    # First ever run: the feeds hand us ~100 back-dated items at once. Learn them
    # silently instead of firing a burst of alerts for reports already gone.
    # The flag is only set once a fetch has actually succeeded - if the first run
    # fails outright, the next one is still a cold start.
    cold_start = not state.data.get("initialized")
    stats["cold_start"] = cold_start
    any_success = False

    for name, url in select_sources(cfg, state).items():
        if state.in_backoff(name, now_unix):
            print(f"{name}: still backing off, skipping this cycle.")
            continue

        if stats["requests"]:
            _time.sleep(getattr(cfg, "seconds_between_requests", SECONDS_BETWEEN_REQUESTS))
        stats["requests"] += 1

        result = fetch_feed(name, url, session=session)
        rec = state.data.setdefault("sources", {}).setdefault(name, {})
        if not result.ok:
            state.record_failure(name, result.error, now)
            rec = state.data["sources"][name]
            rec["consecutive_failures"] = int(rec.get("consecutive_failures", 0)) + 1
            rec.setdefault("failing_since", now.isoformat())
            state.set_backoff(name, result.backoff_until)
            stats["failed"].append(f"{name}: {result.error}")
            print(f"{name}: FAILED - {result.error}")
            continue

        state.record_success(name, now)
        rec = state.data["sources"][name]
        rec["consecutive_failures"] = 0
        rec.pop("failing_since", None)
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

            # Feed the timing histogram so the windows can be re-tested against
            # fresh data later rather than trusting one measurement forever.
            if item.published_known:
                win.record_observation(state, item.published.astimezone(IST).hour)

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
            # Second safety net: a question or a write-up is never worth a
            # max-priority push, however fresh it is.
            if age <= cfg.urgent_max_age_minutes and not m.is_question:
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

    send_headsup(cfg, state, notifier)

    for down in failing_sources(cfg, state, now):
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
