"""Command line entry point.

  python -m visawatch test-alert   send a test notification to your phone
  python -m visawatch poll         one polling cycle over the Reddit feeds
  python -m visawatch waittimes    read the State Dept table (needs a browser)
  python -m visawatch digest       send the daily digest now
  python -m visawatch daily        wait-times + digest, in that order

Add --dry-run to any command to print instead of sending.
"""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .notify import Notifier
from .state import State
from . import runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="visawatch", description="VisaWatch alerting service")
    parser.add_argument(
        "command",
        choices=["test-alert", "poll", "waittimes", "digest", "daily"],
    )
    parser.add_argument("--config", default=None, help="path to config.ini")
    parser.add_argument("--state", default=None, help="path to state.json")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    state = State(args.state)
    notifier = Notifier(cfg, dry_run=args.dry_run)

    try:
        if args.command == "test-alert":
            notifier.test()
            print("Test alert sent. Check your phone.")

        elif args.command == "poll":
            stats = runner.poll(cfg, state, notifier)
            print(
                f"Read {stats['requests']} of {len(cfg.sources)} feeds this cycle "
                f"(one per cycle, to stay inside Reddit's rate limit): "
                f"{stats['fetched']} items, {stats['new']} new, "
                f"{stats['urgent']} urgent, {stats['queued']} queued."
            )
            if stats["cold_start"]:
                print(
                    "First run: learned the existing items quietly so you don't get a "
                    "burst of alerts for reports that are already over. Alerts start "
                    "from the next cycle."
                )
            for failure in stats["failed"]:
                print("  failure:", failure)

        elif args.command == "waittimes":
            changes = runner.check_waittimes(cfg, state, notifier)
            print("Wait-time changes:", changes or "none")

        elif args.command == "digest":
            print(runner.send_digest(cfg, state, notifier))

        elif args.command == "daily":
            changes = runner.check_waittimes(cfg, state, notifier)
            print(runner.send_digest(cfg, state, notifier, changes))

    finally:
        if args.command != "test-alert":
            state.save()

    return 0


if __name__ == "__main__":
    sys.exit(main())
