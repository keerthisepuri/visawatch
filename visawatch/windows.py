"""Release-window heads-up.

WHY THIS EXISTS
---------------
VisaWatch cannot win a race it is structurally too slow for. A slot opens, a
human notices, a human posts, Reddit indexes it, we poll. Batches are reported
to fill "within minutes". Reacting is a lottery.

What DOES work is being logged in and refreshing when a release is likely. That
is a signal a few minutes of lag cannot ruin.

THE EVIDENCE (measured 4 Aug 2026, not folklore)
------------------------------------------------
346 slot-drop posts across r/usvisascheduling, r/USVisaIndians and r/h1b over
362 days, compared against 1,200 general posts from the same subreddits to
control for "when are Indians simply awake and on Reddit".

    hour IST   share of slot posts / share of all posts      z
    06:00      3.73x                                      +5.3
    04:00      1.86x                                      +2.5
    22:00      1.54x                                      +2.4
    07:00      1.57x                                      +1.7

Chi-square vs baseline = 65.3 on 23 df (p < 0.01). The 06:00 result is the
strongest and the most credible: 06:00 is one of the QUIETEST hours on those
subreddits (1.1% of all posts) yet carries 4.0% of slot-drop posts. Nobody is
casually browsing at 6am - they are posting because something happened.

WHAT THE DATA DOES *NOT* SUPPORT
--------------------------------
Day of week. Chi-square 8.9 on 6 df - not significant. The community folklore
about "Wednesday midnight" and "Friday batches" is not visible in a year of
data, so this module deliberately makes no weekday claim.

IMPORTANT CAVEAT
----------------
This measures when people POST about slots, which lags the actual release by an
unknown amount - minutes to tens of minutes. So the real drop is probably a
little BEFORE these hours, which is why the heads-up fires ahead of the window
rather than at its start.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .notify import IST

# Measured lift vs baseline Reddit activity, by IST hour. Kept for reference and
# for the alert text; the windows below are derived from it.
MEASURED_LIFT = {4: 1.86, 6: 3.73, 7: 1.57, 22: 1.54}

# Deliberately centred on the STRONGEST evidence (06:00, 3.7x) rather than
# spanning every hour that showed a lift. Including 04:00 would mean a 03:40
# wake-up every single day for a 1.9x signal - a poor trade for sleep.
DEFAULT_WINDOWS = "05:30-07:30, 22:00-23:00"
DEFAULT_LEAD_MINUTES = 20
DEFAULT_ENABLED = True
DEFAULT_BYPASS_QUIET = True


@dataclass
class Window:
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int

    def start_on(self, day: datetime) -> datetime:
        return day.replace(
            hour=self.start_hour, minute=self.start_minute, second=0, microsecond=0
        )

    def label(self) -> str:
        return f"{self.start_hour:02d}:{self.start_minute:02d}-{self.end_hour:02d}:{self.end_minute:02d} IST"

    def key(self, day: datetime) -> str:
        return f"{day.date().isoformat()}@{self.start_hour:02d}{self.start_minute:02d}"


@dataclass
class WindowConfig:
    enabled: bool = DEFAULT_ENABLED
    lead_minutes: int = DEFAULT_LEAD_MINUTES
    bypass_quiet_hours: bool = DEFAULT_BYPASS_QUIET
    windows: list[Window] = None

    def __post_init__(self):
        if self.windows is None:
            self.windows = parse_windows(DEFAULT_WINDOWS)


def parse_windows(raw: str) -> list[Window]:
    """'04:00-07:00, 22:00-23:00' -> [Window, Window]. Bad entries are skipped
    rather than crashing the poller."""
    out: list[Window] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk or "-" not in chunk:
            continue
        start, _, end = chunk.partition("-")
        try:
            sh, sm = (int(x) for x in start.strip().split(":"))
            eh, em = (int(x) for x in end.strip().split(":"))
        except ValueError:
            continue
        if 0 <= sh <= 23 and 0 <= eh <= 23:
            out.append(Window(sh, sm, eh, em))
    return out


def load_window_config(path: str | Path | None = None) -> WindowConfig:
    """Read the [windows] section straight from config.ini, so every knob still
    lives in the one plain-text file."""
    path = Path(path) if path else Path(__file__).resolve().parent.parent / "config.ini"
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return WindowConfig()
    if not parser.has_section("windows"):
        return WindowConfig()
    s = parser["windows"]
    return WindowConfig(
        enabled=s.getboolean("enabled", DEFAULT_ENABLED),
        lead_minutes=s.getint("lead_minutes", DEFAULT_LEAD_MINUTES),
        bypass_quiet_hours=s.getboolean("bypass_quiet_hours", DEFAULT_BYPASS_QUIET),
        windows=parse_windows(s.get("windows", DEFAULT_WINDOWS)),
    )


def due_window(wcfg: WindowConfig, state, now_ist: datetime | None = None) -> Window | None:
    """The window whose heads-up should be sent right now, or None.

    Fires once per window per day, in the lead_minutes before it opens. Because
    polling is every ~5 minutes we accept anything inside the lead period rather
    than requiring an exact moment, and dedupe on a per-day key.
    """
    if not wcfg.enabled or not wcfg.windows:
        return None
    now_ist = now_ist or datetime.now(IST)
    sent = state.data.setdefault("headsup_sent", {})

    for w in wcfg.windows:
        for day_offset in (0, 1):     # tonight's window may belong to tomorrow
            day = now_ist + timedelta(days=day_offset)
            opens = w.start_on(day)
            lead_starts = opens - timedelta(minutes=wcfg.lead_minutes)
            if lead_starts <= now_ist < opens and w.key(day) not in sent:
                return w
    return None


def mark_sent(state, window: Window, now_ist: datetime | None = None) -> None:
    now_ist = now_ist or datetime.now(IST)
    day = now_ist if now_ist.hour <= window.start_hour else now_ist + timedelta(days=1)
    sent = state.data.setdefault("headsup_sent", {})
    sent[window.key(day)] = now_ist.isoformat()
    # Keep only the last 30 keys; this dict is written to the state branch.
    if len(sent) > 30:
        for k in sorted(sent)[: len(sent) - 30]:
            sent.pop(k, None)


def peak_hour(window: Window) -> tuple[int, float] | None:
    """The strongest measured hour inside a window - that is what the alert
    should quote, not whichever hour the window happens to start on."""
    inside = [
        (h, lift)
        for h, lift in MEASURED_LIFT.items()
        if window.start_hour <= h <= window.end_hour
    ]
    return max(inside, key=lambda x: x[1]) if inside else None


def message(window: Window, cfg) -> tuple[str, str]:
    peak = peak_hour(window)
    evidence = (
        f"Slot-drop chatter peaks at {peak[0]:02d}:00 IST - {peak[1]:.1f}x the "
        "normal rate for these subreddits."
        if peak
        else "Historically an above-average window for slot-drop reports."
    )
    title = f"Slot window opening - {window.label()}"
    body = "\n".join(
        [
            f"A likely release window starts at {window.start_hour:02d}:{window.start_minute:02d} IST.",
            "",
            evidence,
            "Measured over 346 slot-drop posts in a year, compared against normal",
            "posting activity. It is a tendency, not a schedule - some days nothing drops.",
            "",
            "Batches are reported to fill within minutes, so being logged in and",
            "refreshing beats reacting to any alert.",
            "",
            f"Log in here: {cfg.portal_link}",
        ]
    )
    return title, body


def record_observation(state, published_ist_hour: int) -> None:
    """Keep counting, so the windows can be re-checked against fresh data later
    instead of trusting a one-off measurement forever."""
    counts = state.data.setdefault("hour_counts", {})
    key = str(published_ist_hour)
    counts[key] = int(counts.get(key, 0)) + 1
