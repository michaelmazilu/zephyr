from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from zephyr.risk import RiskConfig, size_signal
from zephyr.strategy import build_signal


@dataclass(frozen=True)
class BacktestRow:
    event_id: str
    contract_ticker: str
    forecast_probability: float
    market_probability: float
    outcome: int
    timestamp: str | None = None


@dataclass(frozen=True)
class SettledTrade:
    event_id: str
    contract_ticker: str
    side: str
    forecast_probability: float
    market_probability: float
    edge: float
    stake_dollars: float
    pnl_dollars: float
    outcome: int
    bankroll_after: float
    timestamp: str | None = None


@dataclass(frozen=True)
class BacktestResult:
    starting_bankroll: float
    ending_bankroll: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    return_pct: float
    average_edge: float
    trades: list[SettledTrade]


def _settle_pnl(side: str, price_yes: float, stake: float, outcome: int) -> float:
    if stake <= 0.0:
        return 0.0
    if price_yes <= 0.0 or price_yes >= 1.0:
        return 0.0

    if side == "buy_yes":
        if outcome == 1:
            return stake * ((1.0 / price_yes) - 1.0)
        return -stake

    if side == "buy_no":
        price_no = 1.0 - price_yes
        if price_no <= 0.0:
            return 0.0
        if outcome == 0:
            return stake * ((1.0 / price_no) - 1.0)
        return -stake

    return 0.0


def run_backtest(
    rows: list[BacktestRow],
    *,
    starting_bankroll: float,
    min_edge: float = 0.10,
    risk_config: RiskConfig | None = None,
) -> BacktestResult:
    config = risk_config or RiskConfig()
    bankroll = starting_bankroll
    settled: list[SettledTrade] = []

    for row in rows:
        signal = build_signal(
            event_id=row.event_id,
            contract_ticker=row.contract_ticker,
            forecast_probability=row.forecast_probability,
            market_probability=row.market_probability,
            min_edge=min_edge,
        )
        if signal is None:
            continue

        sized = size_signal(signal, bankroll=bankroll, config=config)
        if sized is None:
            continue

        pnl = _settle_pnl(
            side=signal.side,
            price_yes=row.market_probability,
            stake=sized.stake_dollars,
            outcome=row.outcome,
        )
        bankroll += pnl
        settled.append(
            SettledTrade(
                event_id=row.event_id,
                contract_ticker=row.contract_ticker,
                side=signal.side,
                forecast_probability=row.forecast_probability,
                market_probability=row.market_probability,
                edge=signal.edge,
                stake_dollars=sized.stake_dollars,
                pnl_dollars=pnl,
                outcome=row.outcome,
                bankroll_after=bankroll,
                timestamp=row.timestamp,
            )
        )

    total_trades = len(settled)
    wins = sum(1 for trade in settled if trade.pnl_dollars > 0.0)
    losses = sum(1 for trade in settled if trade.pnl_dollars < 0.0)
    win_rate = (wins / total_trades) if total_trades else 0.0
    total_pnl = bankroll - starting_bankroll
    return_pct = ((bankroll / starting_bankroll) - 1.0) if starting_bankroll > 0.0 else 0.0
    average_edge = (
        sum(abs(trade.edge) for trade in settled) / total_trades if total_trades else 0.0
    )

    return BacktestResult(
        starting_bankroll=starting_bankroll,
        ending_bankroll=bankroll,
        total_trades=total_trades,
        winning_trades=wins,
        losing_trades=losses,
        win_rate=win_rate,
        total_pnl=total_pnl,
        return_pct=return_pct,
        average_edge=average_edge,
        trades=settled,
    )


def load_backtest_csv(path: str) -> list[BacktestRow]:
    rows: list[BacktestRow] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows.append(
                BacktestRow(
                    event_id=str(raw["event_id"]).strip(),
                    contract_ticker=str(raw.get("contract_ticker") or "").strip(),
                    forecast_probability=float(raw["forecast_probability"]),
                    market_probability=float(raw["market_probability"]),
                    outcome=int(raw["outcome"]),
                    timestamp=(str(raw["timestamp"]).strip() if raw.get("timestamp") else None),
                )
            )
    return rows

