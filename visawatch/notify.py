"""Sending notifications: ntfy push, plus optional email for the digest."""

from __future__ import annotations

import configparser
import os
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path

import requests

from .sources import USER_AGENT

IST = timezone(timedelta(hours=5, minutes=30))

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.ini"
_ZONE_CACHE: dict = {}


def local_zone(path=None):
    """YOUR timezone, from [you] timezone in config.ini.

    Two different clocks matter in this project and confusing them is a real bug:

      * Release windows are IST, because the consulates and their scheduling
        systems run on India time no matter where the applicant is sitting.
      * Quiet hours are LOCAL, because they are about when you are asleep.

    Getting this wrong inverts quiet hours for anyone outside India - for
    Phoenix, 23:00-07:00 IST is 10:30-18:30 local, i.e. the middle of the
    working day.
    """
    key = str(path or _CONFIG_PATH)
    if key in _ZONE_CACHE:
        return _ZONE_CACHE[key]
    zone = IST
    try:
        from zoneinfo import ZoneInfo

        parser = configparser.ConfigParser(interpolation=None)
        parser.read(key, encoding="utf-8")
        name = parser.get("you", "timezone", fallback="").strip()
        if name:
            zone = ZoneInfo(name)
    except Exception:
        zone = IST      # unknown or missing zone must never break alerting
    _ZONE_CACHE[key] = zone
    return zone


class NotifierError(RuntimeError):
    pass


def in_quiet_hours(cfg, now: datetime | None = None) -> bool:
    """Quiet hours are measured on YOUR clock, not India's."""
    if not cfg.quiet_hours_enabled:
        return False
    zone = local_zone()
    now = (now or datetime.now(zone)).astimezone(zone)
    current: time = now.time()
    start, end = cfg.quiet_start, cfg.quiet_end
    if start == end:
        return False
    if start < end:                       # e.g. 01:00 -> 06:00
        return start <= current < end
    return current >= start or current < end   # wraps midnight, e.g. 23:00 -> 07:00


@dataclass
class Notifier:
    cfg: object
    dry_run: bool = False
    sent: list[dict] = field(default_factory=list)
    session: requests.Session = field(default_factory=requests.Session)

    # ---------- low level ----------

    def _push(self, title: str, body: str, priority: int, tags: str, click: str | None = None) -> None:
        record = {"title": title, "body": body, "priority": priority, "tags": tags, "click": click}
        self.sent.append(record)
        if self.dry_run:
            print(f"[dry-run push p{priority}] {title}\n{body}\n")
            return
        if not self.cfg.ntfy_topic:
            raise NotifierError(
                "No ntfy topic set. Add NTFY_TOPIC as a GitHub secret, or fill in "
                "ntfy_topic under [notifications] in config.ini."
            )
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": str(priority),
            "Tags": tags,
            "User-Agent": USER_AGENT,
        }
        if click:
            headers["Click"] = click
        url = f"{self.cfg.ntfy_server}/{self.cfg.ntfy_topic}"
        resp = self.session.post(url, data=body.encode("utf-8"), headers=headers, timeout=20)
        if resp.status_code >= 400:
            raise NotifierError(f"ntfy returned HTTP {resp.status_code}: {resp.text[:200]}")

    # ---------- public API ----------

    def urgent(self, item, result) -> None:
        """URGENT alerts always send. Quiet hours are deliberately ignored."""
        age = int(round(item.age_minutes()))
        flag = "HIGH PRIORITY " if result.high_priority else ""
        title = f"{flag}Slot report - {', '.join(result.group_c[:2]) or 'India'}"
        body = "\n".join(
            [
                item.title[:220] or "(no title)",
                "",
                f"Matched: {result.summary()}",
                f"Age: {age} min old  |  source: {item.source}",
                "",
                f"Report: {item.permalink}",
                f"Book here yourself: {self.cfg.portal_link}",
            ]
        )
        self._push(title, body, self.cfg.urgent_priority, "rotating_light", click=item.permalink)

    def digest(self, subject: str, body: str) -> bool:
        """Digest respects quiet hours: if it lands inside them it is held, and
        the caller keeps the queued items for the next run. Returns True if sent."""
        if in_quiet_hours(self.cfg):
            print("Quiet hours - holding digest until they end.")
            return False
        self._push(subject, body, self.cfg.digest_priority, "calendar")
        self.email(subject, body)
        return True

    def source_down(self, name: str, stale_minutes: int, error: str) -> None:
        if in_quiet_hours(self.cfg):
            print(f"Quiet hours - holding source-down notice for {name}.")
            return
        self._push(
            "VisaWatch: a source is down",
            f"{name} has not been read for {stale_minutes} minutes.\n"
            f"Last error: {error or 'unknown'}\n"
            "Alerts from other sources are still running.",
            self.cfg.digest_priority,
            "warning",
        )

    def test(self) -> None:
        self._push(
            "VisaWatch test alert",
            "If you can read this on your phone, notifications are working.\n"
            f"Topic: {self.cfg.ntfy_topic or '(not set)'}\n"
            "Real alerts look like this but arrive at max priority.",
            self.cfg.urgent_priority,
            "white_check_mark",
        )

    # ---------- optional email ----------

    def email(self, subject: str, body: str) -> None:
        to_addr = getattr(self.cfg, "email_to", "")
        host = os.environ.get("SMTP_HOST", "")
        user = os.environ.get("SMTP_USER", "")
        password = os.environ.get("SMTP_PASS", "")
        if not (to_addr and host and user and password):
            return
        if self.dry_run:
            print(f"[dry-run email to {to_addr}] {subject}")
            return
        msg = EmailMessage()
        msg["Subject"] = f"[VisaWatch] {subject}"
        msg["From"] = os.environ.get("SMTP_FROM", user)
        msg["To"] = to_addr
        msg.set_content(body)
        port = int(os.environ.get("SMTP_PORT", "587"))
        try:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)
        except Exception as exc:
            print(f"Email digest failed (push digest was still sent): {exc}")
