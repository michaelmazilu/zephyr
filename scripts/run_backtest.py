#!/usr/bin/env python3
"""Run a bankroll-aware backtest from CSV event snapshots."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zephyr.backtest import load_backtest_csv, run_backtest
from zephyr.risk import RiskConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Zephyr backtest on CSV rows with forecast/market/outcome."
    )
    parser.add_argument(
        "--csv",
        default="data/sample_backtest.csv",
        help="CSV path with event_id,contract_ticker,forecast_probability,market_probability,outcome.",
    )
    parser.add_argument(
        "--starting-bankroll",
        type=float,
        default=10000.0,
        help="Initial bankroll in dollars.",
    )
    parser.add_argument(
        "--min-edge",
        type=float,
        default=0.10,
        help="Minimum edge required to place a trade.",
    )
    parser.add_argument(
        "--max-fraction-per-contract",
        type=float,
        default=0.03,
        help="Maximum bankroll fraction per contract.",
    )
    parser.add_argument(
        "--kelly-scale",
        type=float,
        default=0.25,
        help="Fractional Kelly multiplier.",
    )
    parser.add_argument(
        "--show-trades",
        action="store_true",
        help="Print each settled trade in addition to aggregate metrics.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rows = load_backtest_csv(args.csv)
    except Exception as exc:
        print(f"Error loading CSV: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("No rows found in CSV; nothing to backtest.")
        return 0

    risk = RiskConfig(
        max_fraction_per_contract=args.max_fraction_per_contract,
        kelly_scale=args.kelly_scale,
    )
    result = run_backtest(
        rows,
        starting_bankroll=args.starting_bankroll,
        min_edge=args.min_edge,
        risk_config=risk,
    )

    print("Backtest results:")
    print(f"  Starting bankroll:   ${result.starting_bankroll:.2f}")
    print(f"  Ending bankroll:     ${result.ending_bankroll:.2f}")
    print(f"  Total PnL:           ${result.total_pnl:.2f}")
    print(f"  Return:              {result.return_pct * 100:.2f}%")
    print(f"  Trades:              {result.total_trades}")
    print(f"  Win rate:            {result.win_rate * 100:.2f}%")
    print(f"  Avg abs edge:        {result.average_edge:.4f}")

    if args.show_trades and result.trades:
        print("\nSettled trades:")
        for trade in result.trades:
            label = trade.timestamp if trade.timestamp else trade.event_id
            print(
                f"  {label}: {trade.side} {trade.contract_ticker} "
                f"edge={trade.edge:+.3f} stake=${trade.stake_dollars:.2f} "
                f"pnl=${trade.pnl_dollars:+.2f} bankroll=${trade.bankroll_after:.2f}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
