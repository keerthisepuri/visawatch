"""The release-window heads-up: the part that tolerates latency."""

from datetime import datetime, timedelta

import pytest

from conftest import make_item, stub_fetch
from visawatch import runner, windows as win
from visawatch.notify import IST


def at(h, m=0, day=4):
    return datetime(2026, 8, day, h, m, tzinfo=IST)


MORNING_LEAD = (5, 10)      # 20 min before the 05:30 window
EVENING_LEAD = (21, 50)     # 10 min before the 22:00 window


@pytest.fixture
def wcfg():
    return win.load_window_config()


def test_config_is_read_from_config_ini(wcfg):
    assert wcfg.enabled is True
    starts = {(w.start_hour, w.end_hour) for w in wcfg.windows}
    assert any(s <= 6 <= e for s, e in starts), "the 06:00 peak must be covered"
    assert (22, 23) in starts
    assert wcfg.lead_minutes == 20


def test_fires_in_the_lead_period_before_a_window(wcfg, state):
    assert win.due_window(wcfg, state, at(*MORNING_LEAD)) is not None
    assert win.due_window(wcfg, state, at(*EVENING_LEAD)) is not None


def test_does_not_fire_long_before_or_after(wcfg, state):
    assert win.due_window(wcfg, state, at(2, 0)) is None
    assert win.due_window(wcfg, state, at(12, 0)) is None
    assert win.due_window(wcfg, state, at(6, 30)) is None, "window already open"


def test_fires_once_per_window_per_day(wcfg, state):
    w = win.due_window(wcfg, state, at(*MORNING_LEAD))
    assert w is not None
    win.mark_sent(state, w, at(*MORNING_LEAD))
    assert win.due_window(wcfg, state, at(5, 15)) is None, "repeat ping same morning"
    # ...but the same window tomorrow is fair game.
    assert win.due_window(wcfg, state, at(*MORNING_LEAD, day=5)) is not None


def test_disabled_means_silent(state):
    cfg = win.WindowConfig(enabled=False)
    assert win.due_window(cfg, state, at(*MORNING_LEAD)) is None


def test_morning_ping_is_not_swallowed_by_quiet_hours(cfg, state, notifier):
    """05:10 IST is inside quiet hours (23:00-07:00). Suppressing the ping would
    defeat the entire point of the feature."""
    cfg.quiet_hours_enabled = True
    sent = runner.send_headsup(cfg, state, notifier, now_ist=at(*MORNING_LEAD))
    assert sent is True
    assert len(notifier.sent) == 1
    assert notifier.sent[0]["priority"] == cfg.urgent_priority


def test_quiet_hours_are_respected_when_the_user_asks(cfg, state, notifier, monkeypatch):
    cfg.quiet_hours_enabled = True
    cfg._window_config = win.WindowConfig(bypass_quiet_hours=False)
    monkeypatch.setattr("visawatch.runner.in_quiet_hours", lambda *a, **k: True)
    assert runner.send_headsup(cfg, state, notifier, now_ist=at(*MORNING_LEAD)) is False
    assert notifier.sent == []


def test_alert_states_the_window_in_the_users_own_clock(cfg, state, notifier):
    """An IST time is useless to someone in Phoenix. The alert must do the
    arithmetic for them."""
    from visawatch.notify import IST as _IST, local_zone

    runner.send_headsup(cfg, state, notifier, now_ist=at(*MORNING_LEAD))
    body = notifier.sent[0]["body"]
    assert "05:30 IST" in body
    if local_zone() is not _IST:
        assert "your time" in body
        # 05:30 IST is 17:00 in Phoenix the previous day.
        assert "17:00" in body


def test_message_carries_the_evidence_and_the_portal_link(cfg, state, notifier):
    runner.send_headsup(cfg, state, notifier, now_ist=at(*MORNING_LEAD))
    body = notifier.sent[0]["body"]
    assert "06:00 IST" in body, "must quote the 06:00 peak, not the window start"
    assert "3.7x" in body
    assert cfg.portal_link in body
    assert "not a schedule" in body, "must not overclaim certainty"


def test_polling_records_the_timing_histogram(cfg, state, notifier, monkeypatch):
    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    item = make_item(uid="t3_hist", title="Bulk slots dropped Hyderabad H1B", age_minutes=2)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))
    runner.poll(cfg, state, notifier)
    counts = state.data.get("hour_counts", {})
    assert sum(counts.values()) == 1, "matched item not recorded in the histogram"


def test_headsup_bookkeeping_cannot_grow_without_bound(state):
    w = win.parse_windows("06:00-07:00")[0]
    for d in range(1, 29):
        for month in (7, 8):
            win.mark_sent(state, w, datetime(2026, month, d, 5, 40, tzinfo=IST))
    assert len(state.data["headsup_sent"]) <= 30


def test_bad_window_config_does_not_crash_the_poller():
    assert win.parse_windows("garbage") == []
    assert win.parse_windows("99:00-100:00") == []
    assert len(win.parse_windows("04:00-07:00, oops, 22:00-23:00")) == 2
