"""When to be sitting on the calendar.

WHY THIS REPLACED THE OLD "RELEASE WINDOW" MODEL
------------------------------------------------
VisaWatch used to claim two daily release windows in IST (05:30-07:30 and
22:00-23:00), derived from when slot-drop posts clustered on Reddit against a
baseline of ordinary posts.

On 6 Aug 2026 that analysis was re-run on a fresh sample of a year of posts and
it DID NOT REPLICATE. Two things went wrong with the original:

  1. Almost nothing in the sample was a real slot-drop report. Of 131 posts in a
     year whose titles matched "slot" + an availability word, 57 were questions,
     63 were narrative, and only a handful were live reports - people ASKING
     about slots, not announcing them. The old measurement was therefore a
     measurement of when people get frustrated and post, not of when slots open.
  2. The daily calendar-refresh budget resets on the IST day boundary, which
     gives everyone - in India and abroad alike - a reason to check hardest in
     the Indian morning. That confound survives the "control for baseline
     activity" check and survives the US-vs-India cross-check too, because the
     reset is anchored to IST for every applicant on earth.

Re-tested against the fresh sample: chi-square 30.3 on 23 df for questions and
19.2 for the rest, both below the 35.2 needed for p<0.05. No hour-of-day effect.
The 06:00 IST peak is not there.

WHAT THIS MODULE DOES INSTEAD
-----------------------------
It stops predicting releases, which VisaWatch cannot observe, and instead keeps
time against the one mechanism that is documented to repeat: cancelled
appointments return to the pool around minute :00 and :30 of every hour.

That is portal behaviour rather than crowd behaviour, which is why it is worth
acting on. It is also NOT something VisaWatch can verify - checking would mean
polling the booking portal, which is forbidden. Reddit post timing is the wrong
instrument for it: a post is written minutes after the fact, which smears
minute-of-hour into noise. Measured anyway on the fresh sample, slot posts sat
1.17x above chance in the :00/:30 +/-4min band - the right direction, far short
of significance at n=57. So this is taken on the community's authority, and
labelled as such in the alert.

The honest framing: this module tells you WHEN TO LOOK, not when slots exist.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

from .notify import IST, local_zone

DEFAULT_ACTIVE = "09:00-21:00"
DEFAULT_TICKS = "00, 30"
DEFAULT_LEAD_MINUTES = 5
DEFAULT_GRACE_MINUTES = 2
DEFAULT_DAYS = "mon, tue, wed, thu, fri, sat, sun"
DEFAULT_ENABLED = True
DEFAULT_PRIORITY = 4          # high, but below the max reserved for real reports
DEFAULT_BYPASS_QUIET = False

# The portal allows 20 full calendar page loads per applicant per day, and the
# count resets on the IST day boundary. Quoted in the alert so the budget is
# always in view - it is the real scarce resource, not time.
DAILY_PAGE_LOADS = 20

_DAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class CheckConfig:
    enabled: bool = DEFAULT_ENABLED
    active_start: time = field(default_factory=lambda: time(9, 0))
    active_end: time = field(default_factory=lambda: time(21, 0))
    ticks: list = None
    lead_minutes: int = DEFAULT_LEAD_MINUTES
    grace_minutes: int = DEFAULT_GRACE_MINUTES
    days: set = None
    priority: int = DEFAULT_PRIORITY
    bypass_quiet_hours: bool = DEFAULT_BYPASS_QUIET

    def __post_init__(self):
        if self.ticks is None:
            self.ticks = parse_ticks(DEFAULT_TICKS)
        if self.days is None:
            self.days = parse_days(DEFAULT_DAYS)


def parse_ticks(raw: str) -> list:
    """'00, 30' -> [0, 30]. Rubbish is skipped rather than crashing the poller."""
    out = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk.isdigit():
            continue
        m = int(chunk)
        if 0 <= m <= 59 and m not in out:
            out.append(m)
    return sorted(out) or [0, 30]


def parse_days(raw: str) -> set:
    out = set()
    for chunk in (raw or "").split(","):
        key = chunk.strip().lower()[:3]
        if key in _DAY_NAMES:
            out.add(_DAY_NAMES[key])
    return out or set(range(7))


def parse_hhmm(raw: str, fallback: time) -> time:
    try:
        h, m = (int(x) for x in raw.strip().split(":"))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(h, m)
    except (AttributeError, ValueError):
        pass
    return fallback


def parse_active(raw: str) -> tuple:
    start, _, end = (raw or "").partition("-")
    return parse_hhmm(start, time(9, 0)), parse_hhmm(end, time(21, 0))


def load_window_config(path: str | Path | None = None) -> CheckConfig:
    """Read [checking] straight from config.ini, so every knob still lives in the
    one plain-text file. Falls back to defaults if the section is missing."""
    path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.ini"
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return CheckConfig()
    if not parser.has_section("checking"):
        return CheckConfig()
    s = parser["checking"]
    start, end = parse_active(s.get("active_hours", DEFAULT_ACTIVE))
    return CheckConfig(
        enabled=s.getboolean("enabled", DEFAULT_ENABLED),
        active_start=start,
        active_end=end,
        ticks=parse_ticks(s.get("ticks", DEFAULT_TICKS)),
        lead_minutes=s.getint("lead_minutes", DEFAULT_LEAD_MINUTES),
        grace_minutes=s.getint("grace_minutes", DEFAULT_GRACE_MINUTES),
        days=parse_days(s.get("days", DEFAULT_DAYS)),
        priority=s.getint("priority", DEFAULT_PRIORITY),
        bypass_quiet_hours=s.getboolean("bypass_quiet_hours", DEFAULT_BYPASS_QUIET),
    )


def _in_active_hours(ccfg: CheckConfig, moment: datetime) -> bool:
    t = moment.time()
    if ccfg.active_start <= ccfg.active_end:
        return ccfg.active_start <= t <= ccfg.active_end
    return t >= ccfg.active_start or t <= ccfg.active_end   # wraps midnight


def tick_key(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def due_window(ccfg: CheckConfig, state, now=None):
    """The :00 or :30 moment we should be warning about right now, or None.

    Returns the tick instant itself (an aware datetime in YOUR timezone), so the
    message can name a real clock time rather than a vague window.

    The acceptance band is [tick - lead, tick + grace). Polling runs about every
    five minutes and is at the mercy of GitHub's scheduler, so an exact-moment
    test would silently drop pings; the grace period means a slightly late cycle
    still fires. Each tick is deduped on its own minute, so a run that polls
    twice inside the band still only pings once.
    """
    if not ccfg.enabled or not ccfg.ticks:
        return None
    zone = local_zone()
    now = (now or datetime.now(zone)).astimezone(zone)
    sent = state.data.setdefault("headsup_sent", {})

    for hour_offset in (-1, 0, 1):
        base = (now + timedelta(hours=hour_offset)).replace(second=0, microsecond=0)
        for minute in ccfg.ticks:
            tick = base.replace(minute=minute)
            opens = tick - timedelta(minutes=ccfg.lead_minutes)
            closes = tick + timedelta(minutes=ccfg.grace_minutes)
            if not (opens <= now < closes):
                continue
            if tick.weekday() not in ccfg.days:
                continue
            if not _in_active_hours(ccfg, tick):
                continue
            if tick_key(tick) in sent:
                continue
            return tick
    return None


def mark_sent(state, tick, now=None, lead_minutes: int = DEFAULT_LEAD_MINUTES) -> None:
    sent = state.data.setdefault("headsup_sent", {})
    sent[tick_key(tick)] = (now or tick).isoformat()
    # Keep only the last 60 keys - a day and a bit at two ticks an hour. This
    # dict is written to the state branch on every cycle, so it has to stay small.
    if len(sent) > 60:
        for k in sorted(sent)[: len(sent) - 60]:
            sent.pop(k, None)


def budget_resets_at(zone) -> str:
    """The 20-load counter resets on the IST day boundary. For anyone outside
    India that lands at a genuinely surprising local hour, so spell it out."""
    tomorrow_ist = (datetime.now(IST) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow_ist.astimezone(zone).strftime("%H:%M")


def is_first_of_day(state, tick) -> bool:
    day = tick.date().isoformat()
    return state.data.get("last_protocol_day") != day


def message(tick, cfg, now=None, lead_minutes: int = DEFAULT_LEAD_MINUTES,
            first_of_day: bool = False) -> tuple:
    """Short by design. This fires up to 24 times a day; a wall of text would be
    ignored within a week, and an ignored alert is worse than no alert."""
    zone = local_zone()
    tick_ist = tick.astimezone(IST)
    minutes = int(round((tick - (now or datetime.now(zone)).astimezone(zone)).total_seconds() / 60))

    when = "now" if minutes <= 0 else f"in {minutes} min"
    title = f"Check the calendar - :{tick.minute:02d} {when}"

    lines = [
        f"Cancellations go back into the pool around {tick.strftime('%H:%M')} "
        f"{tick.tzname()} ({tick_ist.strftime('%H:%M IST')}).",
        "",
        "Do NOT reload the page. Change the location in the dropdown and",
        "change it back - that re-queries availability and costs you none",
        f"of your {DAILY_PAGE_LOADS} daily calendar loads.",
    ]

    if first_of_day:
        lines += [
            "",
            f"First check of the day. Your {DAILY_PAGE_LOADS} calendar page",
            f"loads reset at {budget_resets_at(zone)} {tick.tzname()} (midnight IST).",
            "",
            "Slow down between clicks - a burst of them is what triggers the",
            "1015 rate limit, and it will hit you on the click that matters.",
            "",
            "Reported cadence, not something VisaWatch can verify - it never",
            "touches the portal.",
        ]

    lines += ["", f"Log in here: {cfg.portal_link}"]
    return title, "\n".join(lines)


def record_observation(state, published_ist_hour: int) -> None:
    """Still counting hour-of-day, purely so the abandoned release-window theory
    can be re-tested later against VisaWatch's own data rather than Reddit
    search results. Nothing reads this yet, and nothing should until there are
    enough genuine live reports in it to be worth a test."""
    counts = state.data.setdefault("hour_counts", {})
    key = str(published_ist_hour)
    counts[key] = int(counts.get(key, 0)) + 1
