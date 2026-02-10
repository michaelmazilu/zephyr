from __future__ import annotations

import unittest

from zephyr.backtest import BacktestRow, run_backtest
from zephyr.risk import RiskConfig


class BacktestTests(unittest.TestCase):
    def test_backtest_executes_and_updates_bankroll(self) -> None:
        rows = [
            BacktestRow(
                event_id="evt-a",
                contract_ticker="C-A",
                forecast_probability=0.70,
                market_probability=0.50,
                outcome=1,
            ),
            BacktestRow(
                event_id="evt-b",
                contract_ticker="C-B",
                forecast_probability=0.30,
                market_probability=0.45,
                outcome=0,
            ),
            BacktestRow(
                event_id="evt-c",
                contract_ticker="C-C",
                forecast_probability=0.57,
                market_probability=0.50,
                outcome=1,
            ),
        ]
        result = run_backtest(
            rows,
            starting_bankroll=10000.0,
            min_edge=0.10,
            risk_config=RiskConfig(max_fraction_per_contract=0.03, kelly_scale=0.25),
        )
        self.assertEqual(result.total_trades, 2)
        self.assertGreater(result.ending_bankroll, 10000.0)
        self.assertGreater(result.win_rate, 0.0)


if __name__ == "__main__":
    unittest.main()

