"""Load and validate the plain-text config.ini file."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"


def _split_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_hhmm(raw: str, label: str) -> time:
    raw = raw.strip()
    try:
        hh, mm = raw.split(":")
        return time(int(hh), int(mm))
    except Exception as exc:  # pragma: no cover - config error path
        raise ValueError(
            f"config.ini: {label} should look like 09:00 but was {raw!r}"
        ) from exc


@dataclass
class Config:
    group_a: list[str]
    group_b: list[str]
    group_c: list[str]
    boost: list[str]
    exclude: list[str]

    urgent_max_age_minutes: int
    digest_time_ist: time
    source_down_after_minutes: int
    source_down_repeat_minutes: int
    forget_seen_after_days: int

    quiet_hours_enabled: bool
    quiet_start: time
    quiet_end: time

    ntfy_topic: str
    ntfy_server: str
    urgent_priority: int
    digest_priority: int
    email_to: str

    sources: dict[str, str] = field(default_factory=dict)

    waittimes_enabled: bool = True
    waittimes_url: str = ""
    waittimes_posts: list[str] = field(default_factory=list)
    waittimes_column: str = "Petition-Based"

    @property
    def portal_link(self) -> str:
        """A plain informational link. Never fetched, never logged into."""
        return "https://www.usvisascheduling.com/en-US/"


def load_config(path: str | os.PathLike | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Could not find the config file at {path}")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")

    m = parser["matching"]
    t = parser["timing"]
    q = parser["quiet_hours"]
    n = parser["notifications"]
    w = parser["waittimes"] if parser.has_section("waittimes") else {}

    # A GitHub secret always wins over the file, so the topic can stay private.
    topic = os.environ.get("NTFY_TOPIC", "").strip() or n.get("ntfy_topic", "").strip()
    email_to = os.environ.get("EMAIL_TO", "").strip() or n.get("email_to", "").strip()

    cfg = Config(
        group_a=_split_list(m.get("group_a", "")),
        group_b=_split_list(m.get("group_b", "")),
        group_c=_split_list(m.get("group_c", "")),
        boost=_split_list(m.get("boost", "")),
        exclude=_split_list(m.get("exclude", "")),
        urgent_max_age_minutes=t.getint("urgent_max_age_minutes", 15),
        digest_time_ist=_parse_hhmm(t.get("digest_time_ist", "09:00"), "digest_time_ist"),
        source_down_after_minutes=t.getint("source_down_after_minutes", 60),
        source_down_repeat_minutes=t.getint("source_down_repeat_minutes", 360),
        forget_seen_after_days=t.getint("forget_seen_after_days", 7),
        quiet_hours_enabled=q.getboolean("enabled", True),
        quiet_start=_parse_hhmm(q.get("start", "23:00"), "quiet_hours start"),
        quiet_end=_parse_hhmm(q.get("end", "07:00"), "quiet_hours end"),
        ntfy_topic=topic,
        ntfy_server=n.get("ntfy_server", "https://ntfy.sh").rstrip("/"),
        urgent_priority=n.getint("urgent_priority", 5),
        digest_priority=n.getint("digest_priority", 3),
        email_to=email_to,
        sources=dict(parser["sources"]) if parser.has_section("sources") else {},
        waittimes_enabled=(
            parser.getboolean("waittimes", "enabled", fallback=True)
            if parser.has_section("waittimes")
            else False
        ),
        waittimes_url=w.get("url", "") if w else "",
        waittimes_posts=_split_list(w.get("posts", "")) if w else [],
        waittimes_column=w.get("column", "Petition-Based") if w else "Petition-Based",
    )

    for group, name in ((cfg.group_a, "group_a"), (cfg.group_b, "group_b"), (cfg.group_c, "group_c")):
        if not group:
            raise ValueError(f"config.ini: {name} is empty - nothing would ever match.")

    return cfg
