from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ForecastSnapshot:
    event_id: str
    model: str
    probability: float
    generated_at_utc: datetime
    details: dict[str, object]


@dataclass(frozen=True)
class MarketQuote:
    source: str
    contract_ticker: str
    event_ticker: str | None
    title: str | None
    subtitle: str | None
    yes_probability: float
    yes_bid: float | None
    yes_ask: float | None
    last_price: float | None
    fetched_at_utc: datetime


@dataclass(frozen=True)
class Signal:
    event_id: str
    contract_ticker: str
    side: str
    forecast_probability: float
    market_probability: float
    edge: float
    expected_value_per_dollar: float
    rationale: str


@dataclass(frozen=True)
class SizedSignal:
    signal: Signal
    fraction_of_bankroll: float
    stake_dollars: float

