#!/usr/bin/env python3
"""Log Polymarket + forecast snapshots into SQLite."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zephyr.forecast import (
    PrecipEventRequest,
    TemperatureEventRequest,
    compute_precip_event_probability,
    compute_temperature_event_probability,
)
from zephyr.market import PolymarketGammaClient
from zephyr.market.universe import (
    load_city_specs,
    load_universe_config,
    select_markets,
)
from zephyr.storage import MarketMetadata, SnapshotRow, connect_db, init_db, insert_snapshot, upsert_market


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log forecast + market snapshots to SQLite.")
    parser.add_argument(
        "--db",
        default="data/zephyr.sqlite",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--config",
        default="data/market_universe.json",
        help="Universe config JSON path.",
    )
    parser.add_argument(
        "--model",
        default="gefs",
        choices=["gefs"],
        help="Forecast model to use (ECMWF not implemented yet).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Pagination depth when scanning Polymarket markets.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Page size for Polymarket market listing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and compute, but do not write to SQLite.",
    )
    return parser.parse_args()


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    config = load_universe_config(args.config)
    cities = load_city_specs(config)
    if not cities:
        print("No cities configured; update your universe config.", file=sys.stderr)
        return 2

    min_volume = float(config.get("min_volume_usd", 50_000))
    window_days_min = int(config.get("window_days_min", 7))
    window_days_max = int(config.get("window_days_max", 14))
    max_markets = int(config.get("max_markets", 25))
    yes_label_default = str(config.get("yes_label_default", "Yes"))
    supported_event_types = list(config.get("supported_event_types", ["temp_max"]))

    now_utc = datetime.now(timezone.utc)
    end_min = _iso_utc(now_utc + timedelta(days=window_days_min))
    end_max = _iso_utc(now_utc + timedelta(days=window_days_max + 1))

    client = PolymarketGammaClient()

    raw_markets: list[dict[str, object]] = []
    offset = 0
    for _ in range(args.max_pages):
        params = {
            "closed": False,
            "limit": args.page_size,
            "offset": offset,
            "order": "volume",
            "ascending": False,
            "volume_num_min": min_volume,
            "end_date_min": end_min,
            "end_date_max": end_max,
        }
        page = client.list_markets(params=params)
        if not page:
            break
        raw_markets.extend(page)
        offset += args.page_size

    selected = select_markets(
        raw_markets,
        cities=cities,
        min_volume_usd=min_volume,
        window_days_min=window_days_min,
        window_days_max=window_days_max,
        max_markets=max_markets,
        supported_event_types=supported_event_types,
        yes_label_default=yes_label_default,
    )

    if not selected:
        print("No markets matched the universe filters.")
        return 0

    conn = connect_db(args.db)
    init_db(conn)

    inserted = 0
    skipped = 0
    for spec in selected:
        market_raw = next(
            (market for market in raw_markets if str(market.get("slug")) == spec.market_slug),
            None,
        )
        if market_raw is None:
            skipped += 1
            continue

        try:
            quote = client.quote_from_market(market_raw, yes_label=spec.yes_label)
        except Exception as exc:
            print(f"Skipping {spec.market_slug}: market quote error: {exc}")
            skipped += 1
            continue

        try:
            if spec.event_type == "temp_max":
                request = TemperatureEventRequest(
                    lat=spec.city.lat,
                    lon=spec.city.lon,
                    threshold_f=spec.threshold_value,
                    timezone_name=spec.city.timezone,
                    event_date=spec.event_date,
                    location_label=spec.city.label,
                )
                forecast = compute_temperature_event_probability(request)
            elif spec.event_type == "precip_total":
                request = PrecipEventRequest(
                    lat=spec.city.lat,
                    lon=spec.city.lon,
                    threshold_in=spec.threshold_value,
                    timezone_name=spec.city.timezone,
                    event_date=spec.event_date,
                    location_label=spec.city.label,
                )
                forecast = compute_precip_event_probability(request)
            else:
                skipped += 1
                continue
        except Exception as exc:
            print(f"Skipping {spec.market_slug}: forecast error: {exc}")
            skipped += 1
            continue

        details = {
            "forecast_details": forecast.details,
            "market_question": spec.question,
            "market_slug": spec.market_slug,
            "market_volume": spec.volume,
            "market_liquidity": spec.liquidity,
            "event_type": spec.event_type,
            "threshold_value": spec.threshold_value,
            "threshold_unit": spec.threshold_unit,
        }

        market_meta = MarketMetadata(
            market_slug=spec.market_slug,
            condition_id=spec.condition_id,
            question=spec.question,
            event_title=spec.event_title,
            event_type=spec.event_type,
            city_label=spec.city.label,
            event_date=spec.event_date.isoformat(),
            threshold_value=spec.threshold_value,
            threshold_unit=spec.threshold_unit,
            yes_label=spec.yes_label,
            volume=spec.volume,
            liquidity=spec.liquidity,
            last_seen_utc=_iso_utc(now_utc),
        )
        if not args.dry_run:
            upsert_market(conn, market_meta)

        snapshot = SnapshotRow(
            collected_at_utc=_iso_utc(now_utc),
            model=forecast.model,
            run_date=str(forecast.details.get("run_date")) if forecast.details else None,
            run_cycle_hour_utc=(
                int(forecast.details.get("run_cycle_hour_utc"))
                if forecast.details and forecast.details.get("run_cycle_hour_utc") is not None
                else None
            ),
            market_slug=spec.market_slug,
            contract_ticker=quote.contract_ticker,
            event_id=forecast.event_id,
            forecast_probability=forecast.probability,
            market_probability=quote.yes_probability,
            edge=forecast.probability - quote.yes_probability,
            details=details,
        )

        if args.dry_run:
            inserted += 1
            continue

        if insert_snapshot(conn, snapshot):
            inserted += 1
        else:
            skipped += 1

    print(
        f"Snapshots complete. Selected={len(selected)} Inserted={inserted} Skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
