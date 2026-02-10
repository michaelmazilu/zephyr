from __future__ import annotations

from zephyr.types import Signal


def expected_value_per_dollar(side: str, forecast_probability: float, yes_price: float) -> float:
    if side == "buy_yes":
        if yes_price <= 0.0 or yes_price >= 1.0:
            return 0.0
        return (forecast_probability / yes_price) - 1.0

    if side == "buy_no":
        no_price = 1.0 - yes_price
        if no_price <= 0.0 or no_price >= 1.0:
            return 0.0
        return ((1.0 - forecast_probability) / no_price) - 1.0

    return 0.0


def build_signal(
    *,
    event_id: str,
    contract_ticker: str,
    forecast_probability: float,
    market_probability: float,
    min_edge: float = 0.10,
) -> Signal | None:
    edge = forecast_probability - market_probability
    if edge >= min_edge:
        side = "buy_yes"
    elif edge <= -min_edge:
        side = "buy_no"
    else:
        return None

    ev = expected_value_per_dollar(side, forecast_probability, market_probability)
    if ev <= 0.0:
        return None

    rationale = (
        f"Forecast={forecast_probability:.3f}, Market={market_probability:.3f}, "
        f"Edge={edge:+.3f}, EV=$ {ev:+.3f} per $1 staked."
    )
    return Signal(
        event_id=event_id,
        contract_ticker=contract_ticker,
        side=side,
        forecast_probability=forecast_probability,
        market_probability=market_probability,
        edge=edge,
        expected_value_per_dollar=ev,
        rationale=rationale,
    )

