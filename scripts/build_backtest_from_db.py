#!/usr/bin/env python3
"""Export snapshots + outcomes into a backtest CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zephyr.storage import connect_db, init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build backtest CSV from SQLite data.")
    parser.add_argument(
        "--db",
        default="data/zephyr.sqlite",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--output",
        default="data/backtest_from_db.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional forecast model filter (e.g., NOAA_GEFS).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    init_db(conn)

    query = """
        SELECT
            s.collected_at_utc AS timestamp,
            s.event_id AS event_id,
            s.contract_ticker AS contract_ticker,
            s.forecast_probability AS forecast_probability,
            s.market_probability AS market_probability,
            o.outcome AS outcome
        FROM snapshots s
        JOIN outcomes o ON o.market_slug = s.market_slug
    """
    params: list[object] = []
    if args.model:
        query += " WHERE s.model = ?"
        params.append(args.model)
    query += " ORDER BY s.collected_at_utc ASC"

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print("No joined snapshot/outcome rows found.")
        return 0

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp",
                "event_id",
                "contract_ticker",
                "forecast_probability",
                "market_probability",
                "outcome",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["timestamp"],
                    row["event_id"],
                    row["contract_ticker"],
                    row["forecast_probability"],
                    row["market_probability"],
                    row["outcome"],
                ]
            )

    print(f"Wrote {len(rows)} rows to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
