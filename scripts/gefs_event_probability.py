#!/usr/bin/env python3
"""Compute a GEFS ensemble event probability for one test market."""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE_URL = "https://nomads.ncep.noaa.gov/dods/gefs"
FILL_VALUE = 9.999e20
NUMBER_PATTERN = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


@dataclass(frozen=True)
class GEFSRun:
    run_date: date
    cycle_hour: int
    dataset_base: str


def http_get_text(url: str, timeout_seconds: int = 25) -> str:
    request = Request(url, headers={"User-Agent": "zephyr-gefs-probability/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8")


def find_latest_run(lookback_days: int = 2) -> GEFSRun:
    now_utc = datetime.now(timezone.utc)
    for day_offset in range(lookback_days + 1):
        run_day = (now_utc - timedelta(days=day_offset)).date()
        for cycle_hour in (18, 12, 6, 0):
            dataset_base = (
                f"{BASE_URL}/gefs{run_day:%Y%m%d}/gefs_pgrb2ap5_all_{cycle_hour:02d}z"
            )
            try:
                dds = http_get_text(f"{dataset_base}.dds", timeout_seconds=12)
            except (HTTPError, URLError, TimeoutError):
                continue
            if dds.lstrip().startswith("Dataset {"):
                return GEFSRun(run_day, cycle_hour, dataset_base)
    raise RuntimeError("Could not find a recent GEFS dataset on NOMADS.")


def parse_ascii_vector(text: str) -> list[float]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("Unexpected OPeNDAP ASCII vector response.")
    values_blob = " ".join(lines[1:])
    return [float(token) for token in re.findall(NUMBER_PATTERN, values_blob)]


def parse_member_time_matrix(text: str) -> list[list[float]]:
    lines = text.splitlines()
    if not lines:
        raise ValueError("Empty OPeNDAP response.")

    dims = [int(token) for token in re.findall(r"\[(\d+)\]", lines[0])]
    if len(dims) < 2:
        raise ValueError("Could not read matrix dimensions from OPeNDAP response.")

    ensemble_count, time_count = dims[0], dims[1]
    matrix = [[math.nan] * time_count for _ in range(ensemble_count)]
    row_pattern = re.compile(rf"^\s*((?:\[\d+\])+)\s*,\s*({NUMBER_PATTERN})\s*$")

    for line in lines[1:]:
        match = row_pattern.match(line.strip())
        if not match:
            continue
        indices = [int(token) for token in re.findall(r"\[(\d+)\]", match.group(1))]
        if len(indices) < 2:
            continue
        ens_idx, time_idx = indices[0], indices[1]
        if ens_idx >= ensemble_count or time_idx >= time_count:
            continue
        matrix[ens_idx][time_idx] = float(match.group(2))

    return matrix


def ordinal_day_to_utc_datetime(value: float) -> datetime:
    whole_days = int(math.floor(value))
    fractional_days = value - whole_days
    # GEFS uses "days since 1-1-1 00:00:0.0", where day 1 is 0001-01-01.
    base = datetime.fromordinal(whole_days)
    return (base + timedelta(days=fractional_days)).replace(tzinfo=timezone.utc)


def nearest_grid_indices(lat: float, lon: float) -> tuple[int, int]:
    if lat < -90.0 or lat > 90.0:
        raise ValueError("Latitude must be between -90 and 90.")

    lon_360 = lon % 360.0
    lat_idx = int(round((lat + 90.0) / 0.5))
    lon_idx = int(round(lon_360 / 0.5))
    lat_idx = min(360, max(0, lat_idx))
    lon_idx = min(719, max(0, lon_idx))
    return lat_idx, lon_idx


def grid_coords_from_indices(lat_idx: int, lon_idx: int) -> tuple[float, float]:
    lat = -90.0 + (0.5 * lat_idx)
    lon_360 = 0.5 * lon_idx
    lon_180 = ((lon_360 + 180.0) % 360.0) - 180.0
    return lat, lon_180


def fahrenheit_to_kelvin(temp_f: float) -> float:
    return (temp_f - 32.0) * (5.0 / 9.0) + 273.15


def build_market_event_description(
    location_label: str, local_date: date, timezone_name: str, threshold_f: float
) -> str:
    return (
        f"{location_label} max 2m temperature on {local_date.isoformat()} "
        f"({timezone_name}) >= {threshold_f:.1f}F"
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
        local_tz = ZoneInfo(args.timezone)
    except Exception as exc:
        print(f"Invalid timezone '{args.timezone}': {exc}", file=sys.stderr)
        return 2

    try:
        run = find_latest_run(lookback_days=args.lookback_days)
        lat_idx, lon_idx = nearest_grid_indices(args.lat, args.lon)

        time_text = http_get_text(f"{run.dataset_base}.ascii?time")
        time_axis = parse_ascii_vector(time_text)
        if not time_axis:
            raise RuntimeError("No time values returned by GEFS dataset.")

        utc_times = [ordinal_day_to_utc_datetime(v) for v in time_axis]
        local_times = [utc_dt.astimezone(local_tz) for utc_dt in utc_times]

        if args.event_date:
            target_local_date = date.fromisoformat(args.event_date)
        else:
            target_local_date = datetime.now(local_tz).date() + timedelta(days=1)

        target_indices = [
            idx
            for idx, local_dt in enumerate(local_times)
            if local_dt.date() == target_local_date
        ]
        if not target_indices:
            raise RuntimeError(
                f"No GEFS timesteps available for local date {target_local_date}."
            )

        time_start, time_end = min(target_indices), max(target_indices)
        variable = "tmp2m"
        field_url = (
            f"{run.dataset_base}.ascii?"
            f"{variable}[0:1:30][{time_start}:1:{time_end}][{lat_idx}][{lon_idx}]"
        )
        field_text = http_get_text(field_url)
        matrix = parse_member_time_matrix(field_text)

        threshold_k = fahrenheit_to_kelvin(args.threshold_f)
        member_maxima_k: list[float] = []
        for row in matrix:
            valid_values = [
                value for value in row if math.isfinite(value) and value < (FILL_VALUE / 10.0)
            ]
            if valid_values:
                member_maxima_k.append(max(valid_values))

        if not member_maxima_k:
            raise RuntimeError("No valid ensemble values found for the selected event window.")

        runs_exceeding = sum(1 for value in member_maxima_k if value >= threshold_k)
        total_runs = len(member_maxima_k)
        probability = runs_exceeding / total_runs

        grid_lat, grid_lon = grid_coords_from_indices(lat_idx, lon_idx)
        used_local_times = local_times[time_start : time_end + 1]
        event_description = build_market_event_description(
            args.location_label,
            target_local_date,
            args.timezone,
            args.threshold_f,
        )

        print(f"GEFS run: {run.run_date.isoformat()} {run.cycle_hour:02d}Z")
        print(f"Event: {event_description}")
        print(
            "Nearest GEFS grid point: "
            f"lat={grid_lat:.1f}, lon={grid_lon:.1f} (requested lat={args.lat}, lon={args.lon})"
        )
        print(f"Threshold: {threshold_k:.2f} K ({args.threshold_f:.1f} F)")
        print(
            "Timesteps used: "
            + ", ".join(local_dt.strftime("%Y-%m-%d %H:%M %Z") for local_dt in used_local_times)
        )
        print(f"Runs exceeding threshold: {runs_exceeding}/{total_runs}")
        print(f"Probability: {probability:.4f} ({probability * 100:.1f}%)")
        return 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
