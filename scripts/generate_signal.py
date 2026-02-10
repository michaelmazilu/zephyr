#!/usr/bin/env python3
"""Generate one trading signal from GEFS probability + market price."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zephyr.execution import PaperExecutor
from zephyr.forecast import (
    PrecipEventRequest,
    TemperatureEventRequest,
    compute_precip_event_probability,
    compute_temperature_event_probability,
)
from zephyr.market import PolymarketGammaClient
from zephyr.risk import RiskConfig, size_signal
from zephyr.strategy import build_signal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a trade signal by comparing GEFS forecast probability "
            "to market implied probability."
        )
    )
    parser.add_argument("--lat", type=float, default=40.7128, help="Latitude.")
    parser.add_argument("--lon", type=float, default=-74.0060, help="Longitude.")
    parser.add_argument(
        "--threshold-f", type=float, default=85.0, help="Temperature threshold (F)."
    )
    parser.add_argument(
        "--threshold-in",
        type=float,
        default=0.1,
        help="Precipitation threshold (inches).",
    )
    parser.add_argument(
        "--event-type",
        default="temp_max",
        choices=["temp_max", "precip_total"],
        help="Event type to model.",
    )
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="IANA timezone used for the event date window.",
    )
    parser.add_argument(
        "--event-date",
        default=None,
        help="Target local date in YYYY-MM-DD. Defaults to tomorrow in --timezone.",
    )
    parser.add_argument(
        "--location-label",
        default="NYC",
        help="Human-readable location label for output.",
    )
    parser.add_argument(
        "--polymarket-slug",
        default=None,
        help="Polymarket market slug (from the market URL).",
    )
    parser.add_argument(
        "--polymarket-yes-label",
        default="Yes",
        help="Outcome label to treat as the YES probability.",
    )
    parser.add_argument(
        "--market-probability",
        type=float,
        default=None,
        help="Manual market implied YES probability in [0,1] (overrides Polymarket pull).",
    )
    parser.add_argument(
        "--min-edge",
        type=float,
        default=0.10,
        help="Minimum probability edge required to enter a position.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=200.0,
        help="Current bankroll in dollars.",
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
        "--paper-ledger",
        default=None,
        help="Optional CSV path for paper order logging.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.market_probability is None and args.polymarket_slug is None:
        print(
            "Error: set either --market-probability or --polymarket-slug.",
            file=sys.stderr,
        )
        return 2

    try:
        if args.event_type == "temp_max":
            request = TemperatureEventRequest(
                lat=args.lat,
                lon=args.lon,
                threshold_f=args.threshold_f,
                timezone_name=args.timezone,
                event_date=(
                    date.fromisoformat(args.event_date) if args.event_date else None
                ),
                location_label=args.location_label,
            )
            forecast = compute_temperature_event_probability(request)
        else:
            request = PrecipEventRequest(
                lat=args.lat,
                lon=args.lon,
                threshold_in=args.threshold_in,
                timezone_name=args.timezone,
                event_date=(
                    date.fromisoformat(args.event_date) if args.event_date else None
                ),
                location_label=args.location_label,
            )
            forecast = compute_precip_event_probability(request)
    except Exception as exc:
        print(f"Error building forecast probability: {exc}", file=sys.stderr)
        return 1

    quote = None
    if args.market_probability is not None:
        market_probability = args.market_probability
        contract_ticker = "manual_probability"
    else:
        client = PolymarketGammaClient()
        try:
            quote = client.fetch_market_by_slug(
                args.polymarket_slug, yes_label=args.polymarket_yes_label
            )
        except Exception as exc:
            print(f"Error pulling Polymarket quote: {exc}", file=sys.stderr)
            return 1
        market_probability = quote.yes_probability
        contract_ticker = quote.contract_ticker

    if market_probability <= 0.0 or market_probability >= 1.0:
        print("Error: market probability must be in (0,1).", file=sys.stderr)
        return 2

    signal = build_signal(
        event_id=forecast.event_id,
        contract_ticker=contract_ticker,
        forecast_probability=forecast.probability,
        market_probability=market_probability,
        min_edge=args.min_edge,
    )
    if signal is None:
        edge = forecast.probability - market_probability
        print("No trade signal.")
        print(f"Forecast probability: {forecast.probability:.4f}")
        print(f"Market probability:   {market_probability:.4f}")
        print(f"Edge:                 {edge:+.4f}")
        print(f"Required edge:        +/-{args.min_edge:.4f}")
        return 0

    risk = RiskConfig(
        max_fraction_per_contract=args.max_fraction_per_contract,
        kelly_scale=args.kelly_scale,
    )
    sized = size_signal(signal, bankroll=args.bankroll, config=risk)
    if sized is None:
        print("Signal exists but risk engine sized to zero.")
        print(signal.rationale)
        return 0

    print("Trade signal:")
    print(f"  Side:                    {signal.side}")
    print(f"  Contract:                {signal.contract_ticker}")
    print(f"  Forecast probability:    {signal.forecast_probability:.4f}")
    print(f"  Market probability:      {signal.market_probability:.4f}")
    print(f"  Edge:                    {signal.edge:+.4f}")
    print(f"  EV per $1 staked:        {signal.expected_value_per_dollar:+.4f}")
    print(f"  Fraction of bankroll:    {sized.fraction_of_bankroll:.4f}")
    print(f"  Stake dollars:           ${sized.stake_dollars:.2f}")

    if quote is not None and quote.title:
        print(f"  Polymarket title:        {quote.title}")

    if args.paper_ledger:
        executor = PaperExecutor(args.paper_ledger)
        order = executor.execute(sized)
        print(f"Paper order appended: {order.contract_ticker} -> {args.paper_ledger}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
