#!/usr/bin/env python3
"""Record a resolved market outcome in SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zephyr.storage import connect_db, init_db, record_outcome


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a market outcome.")
    parser.add_argument(
        "--db",
        default="data/zephyr.sqlite",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--market-slug",
        required=True,
        help="Polymarket market slug.",
    )
    parser.add_argument(
        "--outcome",
        type=int,
        required=True,
        choices=[0, 1],
        help="Outcome (1 for YES, 0 for NO).",
    )
    parser.add_argument(
        "--event-date",
        default=None,
        help="Event date in YYYY-MM-DD (optional).",
    )
    parser.add_argument(
        "--resolved-at",
        default=None,
        help="Resolution timestamp in ISO format (optional).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    init_db(conn)
    record_outcome(
        conn,
        market_slug=args.market_slug,
        outcome=args.outcome,
        event_date=args.event_date,
        resolved_at_utc=args.resolved_at,
    )
    print(f"Outcome recorded for {args.market_slug}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
