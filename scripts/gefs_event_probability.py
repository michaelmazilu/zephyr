#!/usr/bin/env python3
"""Compute a GEFS ensemble event probability for one test market."""

from __future__ import annotations

import argparse
import sys
from datetime import date
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pull GEFS ensemble data from NOAA NOMADS and compute "
            "P(event) = runs_exceeding_threshold / total_runs."
        )
    )
    parser.add_argument("--lat", type=float, default=40.7128, help="Latitude.")
    parser.add_argument("--lon", type=float, default=-74.0060, help="Longitude.")
    parser.add_argument(
        "--threshold-f",
        type=float,
        default=85.0,
        help="Event threshold in Fahrenheit.",
    )
    parser.add_argument(
        "--threshold-in",
        type=float,
        default=0.1,
        help="Event threshold in inches (for precipitation).",
    )
    parser.add_argument(
        "--event-type",
        default="temp_max",
        choices=["temp_max", "precip_total"],
        help="Event type to compute.",
    )
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="IANA timezone for the event date window.",
    )
    parser.add_argument(
        "--event-date",
        default=None,
        help="Target local date (YYYY-MM-DD). Defaults to tomorrow in --timezone.",
    )
    parser.add_argument(
        "--location-label",
        default="NYC",
        help="Human-readable location label for output.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=2,
        help="How many days back to search for the latest GEFS run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
                lookback_days=args.lookback_days,
            )
            snapshot = compute_temperature_event_probability(request)
            threshold_label = f"{request.threshold_f:.1f}F"
            threshold_k = float(snapshot.details["threshold_k"])
            threshold_line = f"Threshold: {threshold_k:.2f} K ({request.threshold_f:.1f} F)"
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
                lookback_days=args.lookback_days,
            )
            snapshot = compute_precip_event_probability(request)
            threshold_label = f"{request.threshold_in:.2f}in"
            threshold_mm = float(snapshot.details["threshold_mm"])
            threshold_line = (
                f"Threshold: {threshold_mm:.2f} mm ({request.threshold_in:.2f} in)"
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    details = snapshot.details
    print(
        "GEFS run: "
        f"{details['run_date']} {int(details['run_cycle_hour_utc']):02d}Z"
    )
    if args.event_type == "temp_max":
        event_desc = (
            f"{request.location_label} max 2m temperature on {details['target_local_date']} "
            f"({request.timezone_name}) >= {threshold_label}"
        )
    else:
        event_desc = (
            f"{request.location_label} total precipitation on {details['target_local_date']} "
            f"({request.timezone_name}) >= {threshold_label}"
        )
    print(f"Event: {event_desc}")
    print(
        "Nearest GEFS grid point: "
        f"lat={float(details['grid_lat']):.1f}, lon={float(details['grid_lon']):.1f} "
        f"(requested lat={request.lat}, lon={request.lon})"
    )
    print(threshold_line)

    timesteps = details.get("timesteps_local", [])
    if isinstance(timesteps, list) and timesteps:
        print("Timesteps used: " + ", ".join(str(value) for value in timesteps))

    runs_exceeding = int(details["runs_exceeding_threshold"])
    total_runs = int(details["total_runs"])
    print(f"Runs exceeding threshold: {runs_exceeding}/{total_runs}")
    print(f"Probability: {snapshot.probability:.4f} ({snapshot.probability * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
