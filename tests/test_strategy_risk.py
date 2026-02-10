from __future__ import annotations

import unittest

from zephyr.risk import RiskConfig, size_signal
from zephyr.strategy import build_signal


class StrategyRiskTests(unittest.TestCase):
    def test_build_signal_buy_yes(self) -> None:
        signal = build_signal(
            event_id="evt-1",
            contract_ticker="C-1",
            forecast_probability=0.72,
            market_probability=0.54,
            min_edge=0.10,
        )
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.side, "buy_yes")
        self.assertGreater(signal.expected_value_per_dollar, 0.0)

    def test_build_signal_buy_no(self) -> None:
        signal = build_signal(
            event_id="evt-2",
            contract_ticker="C-2",
            forecast_probability=0.31,
            market_probability=0.48,
            min_edge=0.10,
        )
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.side, "buy_no")
        self.assertGreater(signal.expected_value_per_dollar, 0.0)

    def test_size_signal_capped(self) -> None:
        signal = build_signal(
            event_id="evt-3",
            contract_ticker="C-3",
            forecast_probability=0.80,
            market_probability=0.50,
            min_edge=0.10,
        )
        self.assertIsNotNone(signal)
        assert signal is not None
        sized = size_signal(
            signal,
            bankroll=10_000.0,
            config=RiskConfig(max_fraction_per_contract=0.03, kelly_scale=1.0),
        )
        self.assertIsNotNone(sized)
        assert sized is not None
        self.assertAlmostEqual(sized.fraction_of_bankroll, 0.03)
        self.assertAlmostEqual(sized.stake_dollars, 300.0)


if __name__ == "__main__":
    unittest.main()

