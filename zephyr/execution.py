from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from zephyr.types import SizedSignal


@dataclass(frozen=True)
class PaperOrder:
    placed_at_utc: datetime
    event_id: str
    contract_ticker: str
    side: str
    forecast_probability: float
    market_probability: float
    edge: float
    expected_value_per_dollar: float
    fraction_of_bankroll: float
    stake_dollars: float


class PaperExecutor:
    def __init__(self, ledger_path: str = "data/paper_orders.csv") -> None:
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def execute(self, sized_signal: SizedSignal) -> PaperOrder:
        signal = sized_signal.signal
        order = PaperOrder(
            placed_at_utc=datetime.now(timezone.utc),
            event_id=signal.event_id,
            contract_ticker=signal.contract_ticker,
            side=signal.side,
            forecast_probability=signal.forecast_probability,
            market_probability=signal.market_probability,
            edge=signal.edge,
            expected_value_per_dollar=signal.expected_value_per_dollar,
            fraction_of_bankroll=sized_signal.fraction_of_bankroll,
            stake_dollars=sized_signal.stake_dollars,
        )
        self._append(order)
        return order

    def _append(self, order: PaperOrder) -> None:
        exists = self.ledger_path.exists()
        with self.ledger_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if not exists:
                writer.writerow(
                    [
                        "placed_at_utc",
                        "event_id",
                        "contract_ticker",
                        "side",
                        "forecast_probability",
                        "market_probability",
                        "edge",
                        "expected_value_per_dollar",
                        "fraction_of_bankroll",
                        "stake_dollars",
                    ]
                )
            writer.writerow(
                [
                    order.placed_at_utc.isoformat(),
                    order.event_id,
                    order.contract_ticker,
                    order.side,
                    f"{order.forecast_probability:.6f}",
                    f"{order.market_probability:.6f}",
                    f"{order.edge:.6f}",
                    f"{order.expected_value_per_dollar:.6f}",
                    f"{order.fraction_of_bankroll:.6f}",
                    f"{order.stake_dollars:.2f}",
                ]
            )

