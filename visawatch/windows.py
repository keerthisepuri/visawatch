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

from .notify import IST, local_zone

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

    def end_on(self, day: datetime) -> datetime:
        end = day.replace(
            hour=self.end_hour, minute=self.end_minute, second=0, microsecond=0
        )
        if end <= self.start_on(day):        # a window that runs past midnight
            end += timedelta(days=1)
        return end

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


def active_day(window: Window, now_ist: datetime, lead_minutes: int) -> datetime | None:
    """Which calendar day's occurrence of this window covers now_ist, or None.

    'Covers' spans the lead period AND the window itself - see due_window for why
    that matters. The three offsets handle a window whose lead period or tail
    falls on the other side of midnight.
    """
    for offset in (0, -1, 1):
        day = now_ist + timedelta(days=offset)
        if window.start_on(day) - timedelta(minutes=lead_minutes) <= now_ist < window.end_on(day):
            return day
    return None


def due_window(wcfg: WindowConfig, state, now_ist: datetime | None = None) -> Window | None:
    """The window whose heads-up should be sent right now, or None.

    Fires once per window per day, and fires anywhere from lead_minutes before
    the window opens until it closes.

    WHY THE WHOLE WINDOW AND NOT JUST THE LEAD PERIOD: the ping can only be sent
    while a GitHub Actions run happens to be alive, and GitHub's schedule is
    best-effort - measured on this repo, a */5 cron fired 46 times in three days
    instead of ~860. A 20-minute trigger band is narrow enough that an ordinary
    scheduling gap would silently swallow the alert for that day. Firing late is
    far better than not firing: 'the window is open now' is still actionable,
    'you missed it entirely' is not.
    """
    if not wcfg.enabled or not wcfg.windows:
        return None
    now_ist = now_ist or datetime.now(IST)
    sent = state.data.setdefault("headsup_sent", {})

    for w in wcfg.windows:
        day = active_day(w, now_ist, wcfg.lead_minutes)
        if day is not None and w.key(day) not in sent:
            return w
    return None


def mark_sent(state, window: Window, now_ist: datetime | None = None,
              lead_minutes: int = DEFAULT_LEAD_MINUTES) -> None:
    now_ist = now_ist or datetime.now(IST)
    day = active_day(window, now_ist, lead_minutes)
    if day is None:      # marking outside the window at all; fall back to the next one
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


def upcoming_start(window: Window, now_ist: datetime) -> datetime:
    """The next moment this window opens, at or after now."""
    opens = window.start_on(now_ist)
    if opens < now_ist:
        opens = window.start_on(now_ist + timedelta(days=1))
    return opens


def message(window: Window, cfg, now_ist: datetime | None = None,
            lead_minutes: int = DEFAULT_LEAD_MINUTES) -> tuple[str, str]:
    now_ist = now_ist or datetime.now(IST)
    day = active_day(window, now_ist, lead_minutes)
    opens_ist = window.start_on(day) if day is not None else upcoming_start(window, now_ist)
    already_open = now_ist >= opens_ist
    minutes = int(round(abs((opens_ist - now_ist).total_seconds()) / 60))

    zone = local_zone()
    local_line = ""
    if zone is not IST:
        opens_local = opens_ist.astimezone(zone)
        # "today"/"tomorrow" from the reader's point of view, not India's.
        same_day = opens_local.date() == now_ist.astimezone(zone).date()
        when = "today" if same_day else opens_local.strftime("%a")
        local_line = (
            f"That is {opens_local.strftime('%H:%M')} {when} your time "
            f"({opens_local.tzname()})."
        )

    peak = peak_hour(window)
    evidence = (
        f"Slot-drop chatter peaks at {peak[0]:02d}:00 IST - {peak[1]:.1f}x the "
        "normal rate. It shows up in both India-based and US-based subreddits, "
        "so it is a real release pattern, not just when people are awake."
        if peak
        else "Historically an above-average window for slot-drop reports."
    )

    start_txt = f"{window.start_hour:02d}:{window.start_minute:02d} IST"
    if already_open:
        title = f"Slot window OPEN NOW - {window.label()}"
        opening = f"A likely release window is open now - it started at {start_txt}, {minutes} min ago."
    else:
        title = f"Slot window opening - {window.label()}"
        opening = f"A likely release window starts at {start_txt}, in {minutes} min."

    lines = [opening]
    if local_line:
        lines.append(local_line)
    lines += [
        "",
        evidence,
        "A tendency, not a schedule - some days nothing drops.",
        "",
        "Batches are reported to fill within minutes, so being logged in and",
        "refreshing beats reacting to any alert.",
        "",
        f"Log in here: {cfg.portal_link}",
    ]
    return title, "\n".join(lines)


def record_observation(state, published_ist_hour: int) -> None:
    """Keep counting, so the windows can be re-checked against fresh data later
    instead of trusting a one-off measurement forever."""
    counts = state.data.setdefault("hour_counts", {})
    key = str(published_ist_hour)
    counts[key] = int(counts.get(key, 0)) + 1
