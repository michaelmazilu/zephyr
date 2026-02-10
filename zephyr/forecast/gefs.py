from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from zephyr.types import ForecastSnapshot

BASE_URL = "https://nomads.ncep.noaa.gov/dods/gefs"
FILL_VALUE = 9.999e20
NUMBER_PATTERN = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
MM_PER_INCH = 25.4


@dataclass(frozen=True)
class GEFSRun:
    run_date: date
    cycle_hour: int
    dataset_base: str


@dataclass(frozen=True)
class TemperatureEventRequest:
    lat: float = 40.7128
    lon: float = -74.0060
    threshold_f: float = 85.0
    timezone_name: str = "America/New_York"
    event_date: date | None = None
    location_label: str = "NYC"
    lookback_days: int = 2


@dataclass(frozen=True)
class PrecipEventRequest:
    lat: float = 40.7128
    lon: float = -74.0060
    threshold_in: float = 0.1
    timezone_name: str = "America/New_York"
    event_date: date | None = None
    location_label: str = "NYC"
    lookback_days: int = 2


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


def parse_dds_variable_names(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*\w+\s+([A-Za-z0-9_]+)\s*\[", line)
        if match:
            names.append(match.group(1))
    return names


def find_precip_variable(dds_text: str) -> str:
    names = parse_dds_variable_names(dds_text)
    if not names:
        raise RuntimeError("Could not parse any variables from GEFS dataset DDS.")

    lower_map = {name.lower(): name for name in names}
    for preferred in ("apcpsfc", "apcp"):
        if preferred in lower_map:
            return lower_map[preferred]

    for name in names:
        lower = name.lower()
        if "apcp" in lower or "precip" in lower:
            return name

    raise RuntimeError("Could not find a precipitation variable in GEFS dataset DDS.")


def ordinal_day_to_utc_datetime(value: float) -> datetime:
    whole_days = int(math.floor(value))
    fractional_days = value - whole_days
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


def inches_to_mm(value_in: float) -> float:
    return value_in * MM_PER_INCH


def _is_valid_value(value: float) -> bool:
    return math.isfinite(value) and value < (FILL_VALUE / 10.0)


def _is_cumulative_matrix(matrix: list[list[float]]) -> bool:
    for row in matrix:
        prev: float | None = None
        for value in row:
            if not _is_valid_value(value):
                continue
            if prev is not None and (value + 1e-6) < prev:
                return False
            prev = value
    return True


def _last_valid(values: list[float]) -> float | None:
    for value in reversed(values):
        if _is_valid_value(value):
            return value
    return None


def _first_valid(values: list[float]) -> float | None:
    for value in values:
        if _is_valid_value(value):
            return value
    return None


def compute_temperature_event_probability(request: TemperatureEventRequest) -> ForecastSnapshot:
    local_tz = ZoneInfo(request.timezone_name)
    run = find_latest_run(lookback_days=request.lookback_days)
    lat_idx, lon_idx = nearest_grid_indices(request.lat, request.lon)

    time_text = http_get_text(f"{run.dataset_base}.ascii?time")
    time_axis = parse_ascii_vector(time_text)
    if not time_axis:
        raise RuntimeError("No time values returned by GEFS dataset.")

    utc_times = [ordinal_day_to_utc_datetime(value) for value in time_axis]
    local_times = [utc_dt.astimezone(local_tz) for utc_dt in utc_times]

    target_local_date = (
        request.event_date
        if request.event_date is not None
        else (datetime.now(local_tz).date() + timedelta(days=1))
    )

    target_indices = [
        index
        for index, local_dt in enumerate(local_times)
        if local_dt.date() == target_local_date
    ]
    if not target_indices:
        raise RuntimeError(
            f"No GEFS timesteps available for local date {target_local_date}."
        )

    time_start, time_end = min(target_indices), max(target_indices)
    field_url = (
        f"{run.dataset_base}.ascii?"
        f"tmp2m[0:1:30][{time_start}:1:{time_end}][{lat_idx}][{lon_idx}]"
    )
    field_text = http_get_text(field_url)
    matrix = parse_member_time_matrix(field_text)

    threshold_k = fahrenheit_to_kelvin(request.threshold_f)
    member_maxima_k: list[float] = []
    for row in matrix:
        valid_values = [value for value in row if _is_valid_value(value)]
        if valid_values:
            member_maxima_k.append(max(valid_values))

    if not member_maxima_k:
        raise RuntimeError("No valid ensemble values found for the selected event window.")

    runs_exceeding = sum(1 for value in member_maxima_k if value >= threshold_k)
    total_runs = len(member_maxima_k)
    probability = runs_exceeding / total_runs
    grid_lat, grid_lon = grid_coords_from_indices(lat_idx, lon_idx)
    used_local_times = local_times[time_start : time_end + 1]

    event_id = (
        f"tmp2m_max::{request.location_label}::"
        f"{target_local_date.isoformat()}::ge_{request.threshold_f:.1f}F"
    )
    details: dict[str, object] = {
        "run_date": run.run_date.isoformat(),
        "run_cycle_hour_utc": run.cycle_hour,
        "location_label": request.location_label,
        "requested_lat": request.lat,
        "requested_lon": request.lon,
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
        "timezone": request.timezone_name,
        "target_local_date": target_local_date.isoformat(),
        "timesteps_local": [dt.isoformat() for dt in used_local_times],
        "threshold_f": request.threshold_f,
        "threshold_k": threshold_k,
        "runs_exceeding_threshold": runs_exceeding,
        "total_runs": total_runs,
        "dataset_base": run.dataset_base,
    }

    return ForecastSnapshot(
        event_id=event_id,
        model="NOAA_GEFS",
        probability=probability,
        generated_at_utc=datetime.now(timezone.utc),
        details=details,
    )


def compute_precip_event_probability(request: PrecipEventRequest) -> ForecastSnapshot:
    local_tz = ZoneInfo(request.timezone_name)
    run = find_latest_run(lookback_days=request.lookback_days)
    lat_idx, lon_idx = nearest_grid_indices(request.lat, request.lon)

    time_text = http_get_text(f"{run.dataset_base}.ascii?time")
    time_axis = parse_ascii_vector(time_text)
    if not time_axis:
        raise RuntimeError("No time values returned by GEFS dataset.")

    utc_times = [ordinal_day_to_utc_datetime(value) for value in time_axis]
    local_times = [utc_dt.astimezone(local_tz) for utc_dt in utc_times]

    target_local_date = (
        request.event_date
        if request.event_date is not None
        else (datetime.now(local_tz).date() + timedelta(days=1))
    )

    target_indices = [
        index
        for index, local_dt in enumerate(local_times)
        if local_dt.date() == target_local_date
    ]
    if not target_indices:
        raise RuntimeError(
            f"No GEFS timesteps available for local date {target_local_date}."
        )

    time_start, time_end = min(target_indices), max(target_indices)
    fetch_start = time_start - 1 if time_start > 0 else time_start
    window_offset = time_start - fetch_start

    dds_text = http_get_text(f"{run.dataset_base}.dds", timeout_seconds=12)
    precip_var = find_precip_variable(dds_text)

    field_url = (
        f"{run.dataset_base}.ascii?"
        f"{precip_var}[0:1:30][{fetch_start}:1:{time_end}][{lat_idx}][{lon_idx}]"
    )
    field_text = http_get_text(field_url)
    matrix = parse_member_time_matrix(field_text)

    threshold_mm = inches_to_mm(request.threshold_in)
    is_cumulative = _is_cumulative_matrix(matrix)

    member_totals_mm: list[float] = []
    for row in matrix:
        day_values = row[window_offset:]
        if not day_values:
            continue

        if is_cumulative:
            end_val = _last_valid(day_values)
            if window_offset > 0:
                base_val = _last_valid(row[:window_offset])
            else:
                base_val = _first_valid(day_values)
            if end_val is None or base_val is None:
                continue
            total = max(0.0, end_val - base_val)
        else:
            total = sum(value for value in day_values if _is_valid_value(value))

        member_totals_mm.append(total)

    if not member_totals_mm:
        raise RuntimeError("No valid ensemble precipitation totals found.")

    runs_exceeding = sum(1 for value in member_totals_mm if value >= threshold_mm)
    total_runs = len(member_totals_mm)
    probability = runs_exceeding / total_runs
    grid_lat, grid_lon = grid_coords_from_indices(lat_idx, lon_idx)
    used_local_times = local_times[time_start : time_end + 1]

    event_id = (
        f"precip_total::{request.location_label}::"
        f"{target_local_date.isoformat()}::ge_{request.threshold_in:.2f}in"
    )
    details: dict[str, object] = {
        "run_date": run.run_date.isoformat(),
        "run_cycle_hour_utc": run.cycle_hour,
        "location_label": request.location_label,
        "requested_lat": request.lat,
        "requested_lon": request.lon,
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
        "timezone": request.timezone_name,
        "target_local_date": target_local_date.isoformat(),
        "timesteps_local": [dt.isoformat() for dt in used_local_times],
        "threshold_in": request.threshold_in,
        "threshold_mm": threshold_mm,
        "precip_variable": precip_var,
        "precip_is_cumulative": is_cumulative,
        "runs_exceeding_threshold": runs_exceeding,
        "total_runs": total_runs,
        "dataset_base": run.dataset_base,
    }

    return ForecastSnapshot(
        event_id=event_id,
        model="NOAA_GEFS",
        probability=probability,
        generated_at_utc=datetime.now(timezone.utc),
        details=details,
    )
