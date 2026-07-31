"""Parsing a real-shaped Reddit Atom feed.

Reddit's .rss endpoints actually return Atom. This fixture mirrors the exact
structure of a r/usvisascheduling comments feed so parsing is verified even
where the network is unavailable (a CI sandbox, for example).
"""

from datetime import datetime, timezone

from visawatch.matcher import match
from visawatch.sources import parse_feed

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <category term="usvisascheduling" label="r/usvisascheduling"/>
  <updated>2026-07-31T04:10:11+00:00</updated>
  <title>Comments on r/usvisascheduling</title>
  <entry>
    <author><name>/u/someuser</name></author>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;BULK SLOTS just dropped for
      &lt;strong&gt;Hyderabad&lt;/strong&gt; H-1B, go go go&lt;/p&gt;&lt;/div&gt;</content>
    <id>t1_abc123</id>
    <link href="https://www.reddit.com/r/usvisascheduling/comments/xyz/megathread/abc123/"/>
    <updated>2026-07-31T04:09:30+00:00</updated>
    <published>2026-07-31T04:09:30+00:00</published>
    <title>/u/someuser on July 2026 Slot Megathread</title>
  </entry>
  <entry>
    <author><name>/u/otheruser</name></author>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Anyone know how long dropbox
      takes in Chennai these days?&lt;/p&gt;&lt;/div&gt;</content>
    <id>t1_def456</id>
    <link href="https://www.reddit.com/r/usvisascheduling/comments/xyz/megathread/def456/"/>
    <published>2026-07-31T03:55:00+00:00</published>
    <title>/u/otheruser on July 2026 Slot Megathread</title>
  </entry>
</feed>
"""


def test_parses_entries_with_ids_links_and_timestamps():
    items = parse_feed("reddit_comments", ATOM)
    assert len(items) == 2

    first = items[0]
    assert first.uid == "t1_abc123"
    assert first.permalink.endswith("/abc123/")
    assert first.published == datetime(2026, 7, 31, 4, 9, 30, tzinfo=timezone.utc)
    assert "BULK SLOTS just dropped" in first.body
    assert "<strong>" not in first.body      # HTML stripped
    assert "&lt;" not in first.body          # entities decoded


def test_matching_runs_correctly_over_parsed_entries(cfg):
    items = parse_feed("reddit_comments", ATOM)
    results = [match(i.text, cfg) for i in items]

    assert results[0].matched is True
    assert results[0].high_priority is True          # H-1B boost
    assert "Hyderabad" in results[0].group_c
    assert "bulk" in [k.lower() for k in results[0].group_b]

    assert results[1].matched is False               # a question, not a slot report


def test_uids_are_stable_across_reparsing():
    a = {i.uid for i in parse_feed("x", ATOM)}
    b = {i.uid for i in parse_feed("x", ATOM)}
    assert a == b and len(a) == 2


def test_empty_or_garbage_feed_does_not_crash():
    assert parse_feed("x", "") == []
    assert parse_feed("x", "<html><body>not a feed</body></html>") == []
