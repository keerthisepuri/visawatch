import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from visawatch import windows as win              # noqa: E402
from visawatch.config import load_config          # noqa: E402
from visawatch.notify import Notifier             # noqa: E402
from visawatch.sources import FetchResult, Item   # noqa: E402
from visawatch.state import State                 # noqa: E402


@pytest.fixture
def cfg():
    """The real config, but with the :00/:30 metronome switched off.

    THE FLAKE THIS KILLS: runner.poll() fires a check ping as a side effect,
    using the real wall clock. The ping band covers roughly a quarter of the
    active day, so a quarter of the time every test that polls picked up a
    stray notification and assertions like `len(notifier.sent) == 1` failed -
    passing on one machine and failing on another purely because of the hour.
    Tests that want the metronome build their own CheckConfig.
    """
    c = load_config(Path(__file__).resolve().parent.parent / "config.ini")
    c._window_config = win.CheckConfig(enabled=False)
    return c


@pytest.fixture
def ticking_cfg():
    """The real config with the metronome ON, for the tests that are about it."""
    return load_config(Path(__file__).resolve().parent.parent / "config.ini")


@pytest.fixture
def state(tmp_path):
    """A state file that has already been through its first-run warm-up, which
    is the normal condition. Cold start is exercised in its own test."""
    s = State(tmp_path / "state.json")
    s.data["initialized"] = True
    return s


@pytest.fixture
def fresh_state(tmp_path):
    """A brand new state file, as on the very first GitHub Actions run."""
    return State(tmp_path / "fresh.json")


@pytest.fixture
def notifier(cfg):
    """A notifier that records messages instead of sending them."""
    return Notifier(cfg, dry_run=True)


def make_item(uid="t3_abc", title="", body="", age_minutes=1, source="reddit_test"):
    return Item(
        uid=uid,
        source=source,
        title=title,
        body=body,
        permalink=f"https://www.reddit.com/r/usvisascheduling/comments/{uid}/",
        published=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )


def stub_fetch(items, ok=True, error=""):
    """Replace sources.fetch_feed with something that returns fixed items."""
    def _fetch(name, url, session=None):
        return FetchResult(name, ok, list(items) if ok else [], error)
    return _fetch
