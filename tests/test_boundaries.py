"""The non-negotiable rules, enforced as tests."""

import pytest

from visawatch.notify import IST, in_quiet_hours
from visawatch.sources import BlockedDomainError, assert_allowed, fetch_feed
from visawatch import waittimes as wt
from conftest import make_item, stub_fetch
from visawatch import runner
from datetime import datetime


@pytest.mark.parametrize(
    "url",
    [
        "https://www.usvisascheduling.com/en-US/",
        "https://usvisascheduling.com/anything",
        "https://www.ustraveldocs.com/in/",
        "http://ais.usvisa-info.com/en-in/niv",
    ],
)
def test_visa_portals_can_never_be_requested(url):
    with pytest.raises(BlockedDomainError):
        assert_allowed(url)
    with pytest.raises(BlockedDomainError):
        fetch_feed("bad", url)


def test_allowed_sources_pass(cfg):
    for url in cfg.sources.values():
        assert_allowed(url)
    assert_allowed(cfg.waittimes_url)


def test_portal_link_is_only_ever_text(cfg, state, notifier, monkeypatch):
    """The booking link appears in the message body, but is never fetched."""
    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    item = make_item(uid="t3_link", title="Slots dropped Hyderabad H1B", age_minutes=1)
    monkeypatch.setattr(runner, "fetch_feed", stub_fetch([item]))
    runner.poll(cfg, state, notifier)
    assert cfg.portal_link in notifier.sent[0]["body"]


def test_state_file_holds_no_personal_data(cfg, state, notifier, monkeypatch):
    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    monkeypatch.setattr(
        runner, "fetch_feed", stub_fetch([make_item(uid="t3_x", title="Slots open Delhi")])
    )
    runner.poll(cfg, state, notifier)
    blob = str(state.data).lower()
    for forbidden in ("password", "passport", "ds-160", "ds160", "username", "security answer"):
        assert forbidden not in blob


def test_urgent_alerts_ignore_quiet_hours(cfg, state, notifier, monkeypatch):
    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    cfg.quiet_hours_enabled = True
    monkeypatch.setattr(runner.Notifier, "__init__", runner.Notifier.__init__)
    # Force "we are inside quiet hours" for every check.
    monkeypatch.setattr("visawatch.notify.in_quiet_hours", lambda *a, **k: True)
    monkeypatch.setattr(
        runner, "fetch_feed", stub_fetch([make_item(uid="t3_q", title="Slots dropped Mumbai")])
    )

    runner.poll(cfg, state, notifier)

    assert len(notifier.sent) == 1, "urgent alert was suppressed by quiet hours"


def test_digest_respects_quiet_hours(cfg, notifier, monkeypatch):
    monkeypatch.setattr("visawatch.notify.in_quiet_hours", lambda *a, **k: True)
    notifier.digest("subject", "body")
    assert notifier.sent == []


def test_quiet_hours_window_wraps_midnight(cfg):
    cfg.quiet_hours_enabled = True
    def at(h, m=0):
        return datetime(2026, 7, 31, h, m, tzinfo=IST)
    assert in_quiet_hours(cfg, at(23, 30)) is True
    assert in_quiet_hours(cfg, at(3, 0)) is True
    assert in_quiet_hours(cfg, at(6, 59)) is True
    assert in_quiet_hours(cfg, at(7, 0)) is False
    assert in_quiet_hours(cfg, at(14, 0)) is False


def test_backoff_on_429_and_403(monkeypatch):
    import visawatch.sources as s

    class FakeResp:
        def __init__(self, code):
            self.status_code = code
            self.content = b""
            self.text = ""
            self.is_redirect = False
            self.is_permanent_redirect = False
            self.headers = {}

    class FakeSession:
        def __init__(self, code):
            self.code = code
            self.calls = 0

        def get(self, *a, **k):
            self.calls += 1
            return FakeResp(self.code)

    for code in (429, 403):
        session = FakeSession(code)
        result = s.fetch_feed("x", "https://www.reddit.com/r/x/.rss", session=session)
        assert result.ok is False
        assert session.calls == 1, "backed off should mean one request, never a retry"
        assert result.backoff_until > 0


def test_redirect_to_a_visa_portal_is_refused(monkeypatch):
    """A feed that redirects to a booking portal must be refused mid-chain,
    not followed silently."""
    import visawatch.sources as s

    class Resp:
        def __init__(self, code, location=None):
            self.status_code = code
            self.content = b""
            self.text = ""
            self.headers = {"Location": location} if location else {}
            self.is_redirect = location is not None
            self.is_permanent_redirect = False

    class RedirectingSession:
        def __init__(self):
            self.urls = []

        def get(self, url, **k):
            self.urls.append(url)
            return Resp(302, "https://www.ustraveldocs.com/in/")

    session = RedirectingSession()
    with pytest.raises(s.BlockedDomainError):
        s.fetch_feed("x", "https://www.reddit.com/r/x/.rss", session=session)
    assert session.urls == ["https://www.reddit.com/r/x/.rss"], "portal was actually requested"


def test_reddit_usernames_are_not_stored(cfg, state, notifier, monkeypatch):
    """Reddit comment titles read '/u/someone on Megathread'. That username is
    another person's data and must not end up in the saved state file."""
    from visawatch.sources import parse_feed

    cfg.sources = {"reddit_test": "https://www.reddit.com/r/usvisascheduling/new/.rss"}
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>t1_priv</id>
        <link href="https://www.reddit.com/r/usvisascheduling/comments/x/"/>
        <title>/u/RealPersonName123 on July Slot Megathread</title>
        <content type="html">Slots dropped Hyderabad</content>
        <published>2020-01-01T00:00:00+00:00</published>
      </entry>
    </feed>"""
    items = parse_feed("reddit_test", atom)
    assert items[0].title == "July Slot Megathread"

    monkeypatch.setattr(runner, "fetch_feed", stub_fetch(items))
    runner.poll(cfg, state, notifier)
    state.save()

    saved = state.path.read_text()
    assert "RealPersonName123" not in saved
    assert "/u/" not in saved
