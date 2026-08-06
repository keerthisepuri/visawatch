"""The :00/:30 check metronome - the part that tolerates latency."""

from datetime import datetime, timedelta

import pytest

from conftest import make_item, stub_fetch
from visawatch import runner, windows as win
from visawatch.notify import IST, local_zone


ZONE = local_zone()


def at(h, m=0, day=4):
    """A moment in YOUR timezone - the metronome runs on the local clock."""
    return datetime(2026, 8, day, h, m, tzinfo=ZONE)


@pytest.fixture
def ccfg():
    return win.load_window_config()


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def test_config_is_read_from_config_ini(ccfg):
    assert ccfg.enabled is True
    assert ccfg.ticks == [0, 30], "the reported cancellation cadence"
    assert ccfg.lead_minutes == 5
    assert ccfg.priority < 5, "check pings must not shout as loud as a real report"


def test_bad_config_never_crashes_the_poller():
    assert win.parse_ticks("garbage") == [0, 30]
    assert win.parse_ticks("99, 30, -4") == [30]
    assert win.parse_ticks("0,30,30") == [0, 30]
    assert win.parse_days("nonsense") == set(range(7))
    assert win.parse_days("mon, wed") == {0, 2}
    assert win.parse_active("rubbish") == (win.time(9, 0), win.time(21, 0))


# --------------------------------------------------------------------------
# When it fires
# --------------------------------------------------------------------------

def test_fires_shortly_before_each_tick(ccfg, state):
    assert win.due_window(ccfg, state, at(10, 55)) is not None, "no :00 ping"
    assert win.due_window(ccfg, state, at(10, 25)) is not None, "no :30 ping"


def test_does_not_fire_between_ticks(ccfg, state):
    for m in (5, 12, 20, 40, 48):
        assert win.due_window(ccfg, state, at(14, m)) is None, f"spurious ping at :{m}"


def test_silent_outside_active_hours(ccfg, state):
    assert win.due_window(ccfg, state, at(3, 55)) is None, "pinged in the small hours"
    assert win.due_window(ccfg, state, at(23, 25)) is None, "pinged after the day ended"
    assert win.due_window(ccfg, state, at(8, 25)) is None, "pinged before active hours"


def test_the_edges_of_the_active_window_are_included(ccfg, state):
    assert win.due_window(ccfg, state, at(8, 55)) is not None, "09:00 tick was dropped"
    assert win.due_window(ccfg, state, at(20, 55)) is not None, "21:00 tick was dropped"


def test_a_late_cycle_still_pings(ccfg, state):
    """A polling cycle that runs a minute or two behind must not silently lose
    the ping - GitHub's scheduler wobbles constantly."""
    assert win.due_window(ccfg, state, at(11, 1)) is not None, "lost to a 1-min delay"
    assert win.due_window(ccfg, state, at(11, 31)) is not None


def test_a_very_late_cycle_does_not_ping(ccfg, state):
    """...but a ping that has gone stale is worse than none: it would send you to
    the calendar at the wrong moment."""
    assert win.due_window(ccfg, state, at(11, 8)) is None


def test_each_tick_fires_only_once(ccfg, state):
    tick = win.due_window(ccfg, state, at(10, 55))
    win.mark_sent(state, tick, at(10, 55))
    assert win.due_window(ccfg, state, at(10, 57)) is None, "double ping for one tick"
    assert win.due_window(ccfg, state, at(11, 25)) is not None, "next tick was swallowed"


def test_disabled_means_silent(state):
    cfg = win.CheckConfig(enabled=False)
    assert win.due_window(cfg, state, at(10, 55)) is None


def test_days_are_respected(state):
    weekdays = win.CheckConfig(days={0, 1, 2, 3, 4})
    assert win.due_window(weekdays, state, at(10, 55, day=4)) is not None   # Tue
    assert win.due_window(weekdays, state, at(10, 55, day=8)) is None       # Sat


# --------------------------------------------------------------------------
# What it says
# --------------------------------------------------------------------------

def test_ping_names_a_real_clock_time_in_both_zones(ticking_cfg, state, notifier):
    runner.send_headsup(ticking_cfg, state, notifier, now_ist=at(10, 55))
    sent = notifier.sent[0]
    assert "11:00" in sent["body"], "must name the local moment"
    assert "IST" in sent["body"], "must name the India moment too"
    assert ticking_cfg.portal_link in sent["body"]


def test_ping_teaches_the_page_load_trick(ticking_cfg, state, notifier):
    """The 20-load budget is the real scarce resource. A ping that just says
    'check now' burns it; the dropdown re-query costs nothing."""
    runner.send_headsup(ticking_cfg, state, notifier, now_ist=at(10, 55))
    body = notifier.sent[0]["body"]
    assert "not reload" in body.lower()
    assert "dropdown" in body.lower()


def test_first_ping_of_the_day_carries_the_full_protocol(ticking_cfg, state, notifier):
    runner.send_headsup(ticking_cfg, state, notifier, now_ist=at(9, 55))
    first = notifier.sent[0]["body"]
    assert "reset" in first.lower(), "must say when the load budget resets"
    assert "rate limit" in first.lower()
    assert "verify" in first.lower(), "must not claim to have checked the portal"

    runner.send_headsup(ticking_cfg, state, notifier, now_ist=at(10, 25))
    later = notifier.sent[1]["body"]
    assert "rate limit" not in later.lower(), "protocol repeated on every ping"
    assert len(later) < len(first)


def test_ping_priority_is_below_a_real_slot_report(ticking_cfg, state, notifier):
    runner.send_headsup(ticking_cfg, state, notifier, now_ist=at(10, 55))
    assert notifier.sent[0]["priority"] < ticking_cfg.urgent_priority


def test_quiet_hours_suppress_and_do_not_fire_late(cfg, state, notifier, monkeypatch):
    cfg.quiet_hours_enabled = True
    cfg._window_config = win.CheckConfig(bypass_quiet_hours=False)
    monkeypatch.setattr("visawatch.runner.in_quiet_hours", lambda *a, **k: True)

    assert runner.send_headsup(cfg, state, notifier, now_ist=at(10, 55)) is False
    assert notifier.sent == []

    # And it must not resurface the instant quiet hours end.
    monkeypatch.setattr("visawatch.runner.in_quiet_hours", lambda *a, **k: False)
    assert runner.send_headsup(cfg, state, notifier, now_ist=at(10, 58)) is False


# --------------------------------------------------------------------------
# Bookkeeping
# --------------------------------------------------------------------------

def test_a_full_day_produces_the_expected_number_of_pings(ticking_cfg, state, notifier):
    """09:00-21:00 at two ticks an hour = 25 pings. If this number ever drifts,
    it is drifting straight into the user's pocket."""
    t = at(0, 0)
    end = t + timedelta(days=1)
    while t < end:
        runner.send_headsup(ticking_cfg, state, notifier, now_ist=t)
        t += timedelta(minutes=5)
    assert len(notifier.sent) == 25


def test_state_cannot_grow_without_bound(state):
    t = datetime(2026, 8, 4, 9, 0, tzinfo=ZONE)
    for _ in range(500):
        win.mark_sent(state, t)
        t += timedelta(minutes=30)
    assert len(state.data["headsup_sent"]) <= 60


def test_polling_records_the_timing_histogram(cfg, state, notifier, monkeypatch):
    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    item = make_item(uid="t3_hist", title="Bulk slots dropped Hyderabad H1B", age_minutes=2)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))
    runner.poll(cfg, state, notifier)
    assert sum(state.data.get("hour_counts", {}).values()) == 1
