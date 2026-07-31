"""The four behaviours that must never regress."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import make_item, stub_fetch
from visawatch import runner
from visawatch.matcher import match

MATCHING_TITLE = "Slots dropped for Hyderabad H1B dropbox right now"


def only_one_source(cfg):
    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    return cfg


# --------------------------------------------------------------------------
# 1. A matching item fires once.
# --------------------------------------------------------------------------

def test_matching_item_fires_an_urgent_alert(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    item = make_item(uid="t3_fresh", title=MATCHING_TITLE, age_minutes=2)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))

    stats = runner.poll(cfg, state, notifier)

    assert stats["urgent"] == 1
    assert len(notifier.sent) == 1
    sent = notifier.sent[0]
    assert sent["priority"] == cfg.urgent_priority          # max priority
    assert "Hyderabad" in sent["body"]                       # matched keywords
    assert "Age: 2 min old" in sent["body"]                  # age of the report
    assert item.permalink in sent["body"]                    # direct permalink
    assert "usvisascheduling.com/en-US/" in sent["body"]      # plain booking link
    assert "HIGH PRIORITY" in sent["title"]                  # H1B boost applied


def test_non_matching_item_does_not_fire(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    item = make_item(uid="t3_noise", title="Got my passport back from Hyderabad today", age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))

    stats = runner.poll(cfg, state, notifier)

    assert stats["urgent"] == 0
    assert notifier.sent == []


def test_all_three_groups_are_required(cfg):
    assert match("Slots open in Hyderabad", cfg).matched is True
    assert match("Slots open today", cfg).matched is False           # no city
    assert match("Hyderabad appointment", cfg).matched is False      # no event word
    assert match("Hyderabad slots dropped", cfg).matched is True
    # punctuation and case are ignored
    assert match("SLOTS DROPPED - NEW DELHI - H-1B", cfg).high_priority is True


# --------------------------------------------------------------------------
# 2. The same item never fires twice.
# --------------------------------------------------------------------------

def test_same_item_never_alerts_twice(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    item = make_item(uid="t3_dupe", title=MATCHING_TITLE, age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))

    runner.poll(cfg, state, notifier)
    assert len(notifier.sent) == 1

    # Same feed, same item, three more polling cycles.
    for _ in range(3):
        runner.poll(cfg, state, notifier)

    assert len(notifier.sent) == 1, "duplicate alert sent for an already-seen item"


def test_dedup_survives_a_restart(cfg, state, notifier, monkeypatch, tmp_path):
    from visawatch.state import State

    only_one_source(cfg)
    item = make_item(uid="t3_persist", title=MATCHING_TITLE, age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))

    runner.poll(cfg, state, notifier)
    state.save()
    assert len(notifier.sent) == 1

    reloaded = State(state.path)          # as if the next GitHub Actions run started
    runner.poll(cfg, reloaded, notifier)

    assert len(notifier.sent) == 1


# --------------------------------------------------------------------------
# 3. A stale item goes to the digest instead of an urgent push.
# --------------------------------------------------------------------------

def test_stale_match_goes_to_digest_not_urgent(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    stale = make_item(uid="t3_stale", title=MATCHING_TITLE, age_minutes=90)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([stale]))

    stats = runner.poll(cfg, state, notifier)

    assert stats["urgent"] == 0
    assert stats["queued"] == 1
    assert notifier.sent == []
    assert len(state.data["digest_queue"]) == 1

    text = runner.build_digest_text(cfg, state.drain_digest(), {}, [])
    assert "t3_stale" in text
    assert "90 min old" in text


def test_urgency_boundary(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    limit = cfg.urgent_max_age_minutes
    just_inside = make_item(uid="t3_in", title=MATCHING_TITLE, age_minutes=limit - 1)
    just_outside = make_item(uid="t3_out", title=MATCHING_TITLE, age_minutes=limit + 1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([just_inside, just_outside]))

    stats = runner.poll(cfg, state, notifier)

    assert stats["urgent"] == 1
    assert stats["queued"] == 1


def test_digest_says_nothing_matched_when_empty(cfg):
    text = runner.build_digest_text(cfg, [], {}, [])
    assert "Nothing matched today" in text


# --------------------------------------------------------------------------
# 4. A failing source produces a source-down notice.
# --------------------------------------------------------------------------

def test_failing_source_produces_source_down_notice(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False       # so the notice is not held back

    # It worked 3 hours ago, and has been failing since.
    state.record_success("reddit_test", datetime.now(timezone.utc) - timedelta(hours=3))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([], ok=False, error="HTTP 500"))

    stats = runner.poll(cfg, state, notifier)

    assert stats["failed"] == ["reddit_test: HTTP 500"]
    assert len(notifier.sent) == 1
    assert "source is down" in notifier.sent[0]["title"]
    assert "180 minutes" in notifier.sent[0]["body"]


def test_source_down_notice_is_not_repeated_every_cycle(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False
    state.record_success("reddit_test", datetime.now(timezone.utc) - timedelta(hours=3))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([], ok=False, error="HTTP 500"))

    for _ in range(5):
        runner.poll(cfg, state, notifier)

    assert len(notifier.sent) == 1, "source-down notice repeated too often"


def test_brief_failure_does_not_trigger_a_notice(cfg, state, notifier, monkeypatch):
    """A source that failed 10 minutes ago is a blip, not an outage."""
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False
    state.record_success("reddit_test", datetime.now(timezone.utc) - timedelta(minutes=10))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([], ok=False, error="HTTP 500"))

    runner.poll(cfg, state, notifier)

    assert notifier.sent == []


def test_working_source_never_triggers_a_notice(cfg, state, notifier, monkeypatch):
    """A source that keeps succeeding must never produce a source-down notice,
    even after many cycles."""
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False
    state.record_success("reddit_test", datetime.now(timezone.utc) - timedelta(hours=5))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([]))   # succeeds, no items

    for _ in range(3):
        runner.poll(cfg, state, notifier)

    assert notifier.sent == [], "healthy source reported as down"


def test_recovery_clears_the_alarm(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False
    state.record_success("reddit_test", datetime.now(timezone.utc) - timedelta(hours=3))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([], ok=False, error="HTTP 500"))
    runner.poll(cfg, state, notifier)
    assert len(notifier.sent) == 1

    # Source comes back. No further notices, ever.
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([]))
    for _ in range(3):
        runner.poll(cfg, state, notifier)
    assert len(notifier.sent) == 1


def test_daily_source_is_not_reported_down_by_the_five_minute_poller(cfg, state, notifier, monkeypatch):
    """travel.state.gov is only read once a day. The poller must not treat that
    as an outage and nag about it four times a day forever."""
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False
    state.record_success("travel_state_gov", datetime.now(timezone.utc) - timedelta(hours=20))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([]))

    runner.poll(cfg, state, notifier)

    assert notifier.sent == []


def test_a_source_removed_from_config_stops_nagging(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    cfg.quiet_hours_enabled = False
    state.record_success("an_old_feed_i_deleted", datetime.now(timezone.utc) - timedelta(days=4))
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([]))

    runner.poll(cfg, state, notifier)

    assert notifier.sent == []


def test_digest_held_for_quiet_hours_keeps_its_items(cfg, state, notifier, monkeypatch):
    """A digest that lands inside quiet hours must not silently lose matches."""
    only_one_source(cfg)
    stale = make_item(uid="t3_held", title=MATCHING_TITLE, age_minutes=120)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([stale]))
    runner.poll(cfg, state, notifier)
    assert len(state.data["digest_queue"]) == 1

    monkeypatch.setattr("visawatch.notify.in_quiet_hours", lambda *a, **k: True)
    runner.send_digest(cfg, state, notifier)
    assert notifier.sent == []
    assert len(state.data["digest_queue"]) == 1, "queued matches were lost"

    monkeypatch.setattr("visawatch.notify.in_quiet_hours", lambda *a, **k: False)
    runner.send_digest(cfg, state, notifier)
    assert len(notifier.sent) == 1
    assert "t3_held" in notifier.sent[0]["body"]
    assert state.data["digest_queue"] == []


def test_first_ever_run_does_not_fire_a_burst_of_alerts(cfg, fresh_state, notifier, monkeypatch):
    """On the very first run the feeds hand over ~100 back-dated items at once.
    Those are learned silently; alerting starts from the next cycle."""
    only_one_source(cfg)
    backlog = [make_item(uid=f"t3_old{n}", title=MATCHING_TITLE, age_minutes=3) for n in range(20)]
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch(backlog))

    stats = runner.poll(cfg, fresh_state, notifier)

    assert stats["cold_start"] is True
    assert stats["new"] == 20
    assert notifier.sent == []
    assert fresh_state.data["digest_queue"] == []

    # Next cycle: the backlog is known, and a genuinely new report alerts normally.
    new_report = make_item(uid="t3_brandnew", title=MATCHING_TITLE, age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch(backlog + [new_report]))
    stats = runner.poll(cfg, fresh_state, notifier)

    assert stats["cold_start"] is False
    assert stats["urgent"] == 1
    assert len(notifier.sent) == 1


# --------------------------------------------------------------------------
# Failure handling around the push itself.
# --------------------------------------------------------------------------

def test_a_failed_push_is_retried_not_lost(cfg, state, notifier, monkeypatch):
    """If ntfy is down when a match arrives, the item must not be marked as
    delivered - otherwise dedup would silently swallow it forever."""
    only_one_source(cfg)
    item = make_item(uid="t3_pushfail", title=MATCHING_TITLE, age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))

    def boom(*a, **k):
        raise RuntimeError("ntfy returned HTTP 503")

    monkeypatch.setattr(notifier, "urgent", boom)
    stats = runner.poll(cfg, state, notifier)

    assert stats["urgent"] == 0
    assert any("push failed" in f for f in stats["failed"])
    assert not state.has_seen("t3_pushfail"), "item marked delivered despite a failed push"
    assert len(state.data["digest_queue"]) == 1, "failed push not captured for the digest"


def test_one_failed_push_does_not_abort_the_rest_of_the_cycle(cfg, state, notifier, monkeypatch):
    only_one_source(cfg)
    bad = make_item(uid="t3_bad", title=MATCHING_TITLE, age_minutes=1)
    good = make_item(uid="t3_good", title=MATCHING_TITLE, age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([bad, good]))

    real_urgent = notifier.urgent
    calls = {"n": 0}

    def flaky(item, result):
        calls["n"] += 1
        if item.uid == "t3_bad":
            raise RuntimeError("ntfy returned HTTP 503")
        return real_urgent(item, result)

    monkeypatch.setattr(notifier, "urgent", flaky)
    stats = runner.poll(cfg, state, notifier)

    assert calls["n"] == 2, "cycle aborted after the first push failure"
    assert stats["urgent"] == 1
    assert len(notifier.sent) == 1


def test_cold_start_flag_is_not_set_when_every_source_fails(cfg, fresh_state, notifier, monkeypatch):
    """If the very first run fails outright, the next run must still be a cold
    start - otherwise the backlog arrives as a burst of alerts."""
    only_one_source(cfg)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([], ok=False, error="HTTP 403"))

    stats = runner.poll(cfg, fresh_state, notifier)
    assert stats["cold_start"] is True
    assert fresh_state.data.get("initialized") is not True

    backlog = [make_item(uid=f"t3_b{n}", title=MATCHING_TITLE, age_minutes=2) for n in range(10)]
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch(backlog))
    stats = runner.poll(cfg, fresh_state, notifier)

    assert stats["cold_start"] is True
    assert notifier.sent == [], "backlog burst fired after a failed first run"


def test_item_with_no_timestamp_is_never_urgent(cfg, state, notifier, monkeypatch):
    from visawatch.sources import parse_feed

    only_one_source(cfg)
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>t1_nodate</id>
        <link href="https://www.reddit.com/r/usvisascheduling/comments/x/"/>
        <title>Bulk slots dropped Hyderabad H1B</title>
      </entry>
    </feed>"""
    items = parse_feed("reddit_test", atom)
    assert items[0].published_known is False

    monkeypatch.setattr(runner, "fetch_feed", stub_fetch(items))
    stats = runner.poll(cfg, state, notifier)

    assert stats["urgent"] == 0, "undated item treated as brand new"
    assert stats["queued"] == 1


def test_digest_stays_within_ntfy_size_limit(cfg):
    entries = [
        {
            "title": "BULK SLOTS DROPPED " + "x" * 200,
            "permalink": "https://www.reddit.com/r/usvisascheduling/comments/" + "y" * 40,
            "source": "reddit_comments",
            "age_minutes": 40,
            "keywords": "what: slots | event: dropped | where: Hyderabad",
            "high_priority": True,
        }
        for _ in range(400)
    ]
    text = runner.build_digest_text(cfg, entries, {"posts": {"Hyderabad": "3 Months"}}, [])
    assert len(text.encode("utf-8")) < 4096, "digest would be rejected by ntfy"
    assert "400 match(es)" in text


def test_digest_queue_cannot_grow_without_bound(cfg, state):
    for n in range(1000):
        state.queue_for_digest({"title": f"item {n}", "permalink": "", "source": "s",
                                "age_minutes": 30, "keywords": "", "high_priority": False})
    assert len(state.data["digest_queue"]) <= state.MAX_DIGEST_QUEUE
    # The most recent items are the ones kept.
    assert state.data["digest_queue"][-1]["title"] == "item 999"
