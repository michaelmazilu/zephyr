from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

MONTH_PATTERN = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
DATE_PATTERN = re.compile(rf"{MONTH_PATTERN}\s+(\d{{1,2}})(?:,?\s*(\d{{4}}))?", re.I)
TEMP_THRESHOLD_PATTERN = re.compile(r"(-?\d{2,3})\s*°?\s*F", re.I)
PRECIP_THRESHOLD_PATTERN = re.compile(
    r"(?:at least|>=|\u2265|over|more than|greater than)\s*"
    r"(\d+(?:\.\d+)?)\s*(?:(?:inches|inch|in\.|in)\b|\")",
    re.I,
)


@dataclass(frozen=True)
class CitySpec:
    label: str
    name: str
    aliases: list[str]
    lat: float
    lon: float
    timezone: str


@dataclass(frozen=True)
class MarketSpec:
    market_slug: str
    condition_id: str | None
    question: str
    event_type: str
    threshold_value: float
    threshold_unit: str
    event_date: date
    city: CitySpec
    yes_label: str
    volume: float | None
    liquidity: float | None
    event_title: str | None = None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_universe_config(path: str) -> dict[str, object]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_city_specs(config: dict[str, object]) -> list[CitySpec]:
    cities: list[CitySpec] = []
    raw = config.get("cities", [])
    if not isinstance(raw, list):
        return cities
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            cities.append(
                CitySpec(
                    label=str(item["label"]),
                    name=str(item["name"]),
                    aliases=[str(alias) for alias in item.get("aliases", [])],
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                    timezone=str(item["timezone"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return cities


def match_city(question: str, cities: list[CitySpec]) -> CitySpec | None:
    for city in cities:
        for alias in city.aliases:
            if not alias:
                continue
            pattern = re.compile(rf"\b{re.escape(alias)}\b", re.I)
            if pattern.search(question):
                return city
    return None


def parse_question_date(question: str, today: date) -> date | None:
    match = DATE_PATTERN.search(question)
    if not match:
        return None
    month_name = match.group(1)
    day = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else today.year
    try:
        parsed = datetime.strptime(f"{month_name} {day} {year}", "%b %d %Y").date()
    except ValueError:
        try:
            parsed = datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y").date()
        except ValueError:
            return None
    if not match.group(3) and parsed < today:
        parsed = parsed.replace(year=parsed.year + 1)
    return parsed


def parse_temperature_threshold(question: str) -> float | None:
    match = TEMP_THRESHOLD_PATTERN.search(question)
    if not match:
        return None
    return float(match.group(1))


def parse_precip_threshold(question: str) -> float | None:
    match = PRECIP_THRESHOLD_PATTERN.search(question)
    if not match:
        return None
    return float(match.group(1))


def infer_event_date(question: str, market: dict[str, object], today: date) -> date | None:
    from_question = parse_question_date(question, today)
    if from_question is not None:
        return from_question
    end_date = _parse_iso_datetime(market.get("endDate") or market.get("end_date"))
    if end_date is None:
        return None
    return end_date.date()


def is_within_window(target: date, *, today: date, min_days: int, max_days: int) -> bool:
    delta = (target - today).days
    return min_days <= delta <= max_days


def select_markets(
    markets: list[dict[str, object]],
    *,
    cities: list[CitySpec],
    min_volume_usd: float,
    window_days_min: int,
    window_days_max: int,
    max_markets: int,
    supported_event_types: list[str],
    yes_label_default: str = "Yes",
) -> list[MarketSpec]:
    today = datetime.now(timezone.utc).date()
    selected: list[MarketSpec] = []

    for market in markets:
        if len(selected) >= max_markets:
            break

        if market.get("closed") is True:
            continue

        question = str(market.get("question") or market.get("title") or "").strip()
        if not question:
            continue

        outcomes = market.get("outcomes")
        if not outcomes:
            continue
        if isinstance(outcomes, str):
            try:
                outcomes_list = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes_list = []
        elif isinstance(outcomes, list):
            outcomes_list = outcomes
        else:
            outcomes_list = []
        outcomes_list = [str(item) for item in outcomes_list]
        if len(outcomes_list) != 2:
            continue
        yes_label = None
        for outcome in outcomes_list:
            if outcome.strip().lower() == yes_label_default.lower():
                yes_label = yes_label_default
                break
        if yes_label is None:
            continue

        volume = _to_float(market.get("volume") or market.get("volume_num"))
        if volume is None or volume < min_volume_usd:
            continue

        city = match_city(question, cities)
        if city is None:
            continue

        event_date = infer_event_date(question, market, today)
        if event_date is None:
            continue
        if not is_within_window(
            event_date, today=today, min_days=window_days_min, max_days=window_days_max
        ):
            continue

        temp_threshold = parse_temperature_threshold(question)
        if temp_threshold is not None:
            event_type = "temp_max"
            threshold_value = temp_threshold
            threshold_unit = "F"
        else:
            precip_threshold = parse_precip_threshold(question)
            if precip_threshold is None:
                continue
            event_type = "precip_total"
            threshold_value = precip_threshold
            threshold_unit = "in"

        if event_type not in supported_event_types:
            continue

        market_slug = str(market.get("slug") or market.get("id") or "").strip()
        if not market_slug:
            continue

        selected.append(
            MarketSpec(
                market_slug=market_slug,
                condition_id=str(market.get("conditionId") or market.get("condition_id") or "")
                if (market.get("conditionId") or market.get("condition_id"))
                else None,
                question=question,
                event_type=event_type,
                threshold_value=threshold_value,
                threshold_unit=threshold_unit,
                event_date=event_date,
                city=city,
                yes_label=yes_label,
                volume=volume,
                liquidity=_to_float(market.get("liquidity") or market.get("liquidity_num")),
                event_title=str(market.get("eventTitle") or market.get("event_title") or "")
                if (market.get("eventTitle") or market.get("event_title"))
                else None,
            )
        )

    return selected
