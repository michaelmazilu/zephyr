from __future__ import annotations

from dataclasses import dataclass

from zephyr.types import Signal, SizedSignal


@dataclass(frozen=True)
class RiskConfig:
    max_fraction_per_contract: float = 0.03
    kelly_scale: float = 0.25
    min_fraction_if_trade: float = 0.0


def _kelly_fraction_yes(forecast_probability: float, yes_price: float) -> float:
    if yes_price <= 0.0 or yes_price >= 1.0:
        return 0.0
    raw = (forecast_probability - yes_price) / (1.0 - yes_price)
    return max(0.0, raw)


def _kelly_fraction_no(forecast_probability: float, yes_price: float) -> float:
    if yes_price <= 0.0 or yes_price >= 1.0:
        return 0.0
    raw = (yes_price - forecast_probability) / yes_price
    return max(0.0, raw)


def size_signal(
    signal: Signal,
    bankroll: float,
    config: RiskConfig,
) -> SizedSignal | None:
    if bankroll <= 0.0:
        return None

    if signal.side == "buy_yes":
        raw_fraction = _kelly_fraction_yes(
            signal.forecast_probability, signal.market_probability
        )
    elif signal.side == "buy_no":
        raw_fraction = _kelly_fraction_no(
            signal.forecast_probability, signal.market_probability
        )
    else:
        return None

    scaled_fraction = raw_fraction * config.kelly_scale
    bounded_fraction = min(config.max_fraction_per_contract, scaled_fraction)
    if bounded_fraction < config.min_fraction_if_trade:
        return None

    stake = bankroll * bounded_fraction
    if stake <= 0.0:
        return None

    return SizedSignal(
        signal=signal,
        fraction_of_bankroll=bounded_fraction,
        stake_dollars=stake,
    )

