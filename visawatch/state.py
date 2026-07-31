"""Everything VisaWatch remembers between runs, in one JSON file.

Contains no personal data: only Reddit item IDs, timestamps, and the
publicly-published visa wait times.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_STATE_PATH = Path(
    os.environ.get("VISAWATCH_STATE", Path(__file__).resolve().parent.parent / "state.json")
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class State:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else DEFAULT_STATE_PATH
        self.data = {
            "seen": {},          # item uid -> ISO timestamp first seen
            "digest_queue": [],  # matches waiting for the 9am digest
            "sources": {},       # source name -> health info
            "waittimes": {},     # last scraped table
            "backoff": {},       # source name -> unix ts until which we stay away
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass  # corrupt or unreadable state must never crash the alerter
        for key in ("seen", "sources", "waittimes", "backoff"):
            self.data.setdefault(key, {})
        self.data.setdefault("digest_queue", [])

    # ---------- deduplication ----------

    def has_seen(self, uid: str) -> bool:
        return uid in self.data["seen"]

    def mark_seen(self, uid: str, when: datetime | None = None) -> None:
        self.data["seen"][uid] = _iso(when or _now())

    def forget_old(self, days: int) -> None:
        cutoff = _now() - timedelta(days=days)
        # An unparseable timestamp expires rather than living forever, otherwise
        # one corrupt write would pin an entry in the file permanently.
        self.data["seen"] = {
            uid: ts
            for uid, ts in self.data["seen"].items()
            if _safe_parse(ts, default=datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
        }

    # ---------- digest ----------

    MAX_DIGEST_QUEUE = 300

    def queue_for_digest(self, entry: dict) -> None:
        queue = self.data["digest_queue"]
        queue.append(entry)
        # Hard cap so a stuck digest can never grow the state file without bound.
        if len(queue) > self.MAX_DIGEST_QUEUE:
            del queue[: len(queue) - self.MAX_DIGEST_QUEUE]

    def drain_digest(self) -> list[dict]:
        entries = list(self.data["digest_queue"])
        self.data["digest_queue"] = []
        return entries

    # ---------- source health ----------

    def record_success(self, name: str, when: datetime | None = None) -> None:
        rec = self.data["sources"].setdefault(name, {})
        rec["last_success"] = _iso(when or _now())
        rec["last_error"] = ""
        self.data["backoff"].pop(name, None)

    def record_failure(self, name: str, error: str, when: datetime | None = None) -> None:
        rec = self.data["sources"].setdefault(name, {})
        rec.setdefault("last_success", _iso(when or _now()))
        rec["last_error"] = error
        rec["last_error_at"] = _iso(when or _now())

    def set_backoff(self, name: str, until_unix: float) -> None:
        if until_unix:
            self.data["backoff"][name] = until_unix

    def in_backoff(self, name: str, now_unix: float) -> bool:
        return float(self.data["backoff"].get(name, 0)) > now_unix

    def sources_down(
        self,
        after_minutes: int,
        repeat_minutes: int,
        now: datetime | None = None,
        only: list[str] | None = None,
    ) -> list[dict]:
        """Sources whose last success is older than the threshold and which we
        have not already nagged about recently.

        `only` limits the check to the sources this run is actually responsible
        for. Without it, the once-a-day wait-times source would look permanently
        "down" to the five-minute poller, and a source deleted from config.ini
        would nag forever.
        """
        now = now or _now()
        down = []
        for name, rec in self.data["sources"].items():
            if only is not None and name not in only:
                continue
            last_ok = _safe_parse(rec.get("last_success"), default=None)
            if last_ok is None:
                continue
            stale_minutes = (now - last_ok).total_seconds() / 60.0
            if stale_minutes < after_minutes:
                continue
            last_notice = _safe_parse(rec.get("last_down_notice"), default=None)
            if last_notice and (now - last_notice).total_seconds() / 60.0 < repeat_minutes:
                continue
            down.append(
                {
                    "name": name,
                    "stale_minutes": int(stale_minutes),
                    "error": rec.get("last_error", ""),
                }
            )
        return down

    def mark_down_notified(self, name: str, when: datetime | None = None) -> None:
        self.data["sources"].setdefault(name, {})["last_down_notice"] = _iso(when or _now())

    # ---------- persistence ----------

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        # Compact: this file is rewritten every five minutes.
        tmp.write_text(
            json.dumps(self.data, separators=(",", ":"), sort_keys=True), encoding="utf-8"
        )
        tmp.replace(self.path)


def _safe_parse(raw, default):
    if not raw:
        return default
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return default
