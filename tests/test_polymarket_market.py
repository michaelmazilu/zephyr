from __future__ import annotations

import unittest

from zephyr.market.polymarket import PolymarketGammaClient


class PolymarketMarketTests(unittest.TestCase):
    def test_to_quote_parses_string_arrays(self) -> None:
        market = {
            "conditionId": "cond-123",
            "slug": "test-market-slug",
            "question": "Will it rain tomorrow?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.62", "0.38"]',
        }

        quote = PolymarketGammaClient._to_quote(market, yes_label="Yes")

        self.assertEqual(quote.contract_ticker, "cond-123")
        self.assertAlmostEqual(quote.yes_probability, 0.62)
        self.assertEqual(quote.title, "Will it rain tomorrow?")


if __name__ == "__main__":
    unittest.main()
