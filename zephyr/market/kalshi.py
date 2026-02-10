from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from zephyr.types import MarketQuote


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_probability(
    dollars_value: object | None,
    cents_value: object | None,
) -> float | None:
    if dollars_value is not None:
        parsed = _to_float(dollars_value)
        if parsed is not None and 0.0 <= parsed <= 1.0:
            return parsed
    if cents_value is not None:
        parsed = _to_float(cents_value)
        if parsed is not None:
            if 0.0 <= parsed <= 1.0:
                return parsed
            if 0.0 <= parsed <= 100.0:
                return parsed / 100.0
    return None


class KalshiPublicClient:
    def __init__(self, base_url: str = "https://api.elections.kalshi.com/trade-api/v2"):
        self.base_url = base_url.rstrip("/")

    def _get_json(self, path: str, params: dict[str, object] | None = None) -> dict:
        query = ""
        if params:
            encoded = urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            if encoded:
                query = f"?{encoded}"

        url = f"{self.base_url}{path}{query}"
        request = Request(
            url,
            headers={
                "User-Agent": "zephyr-kalshi-client/1.0",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_market(self, contract_ticker: str) -> MarketQuote:
        payload = self._get_json(f"/markets/{contract_ticker}")
        market = payload.get("market")
        if not isinstance(market, dict):
            raise RuntimeError(f"Market not found for ticker '{contract_ticker}'.")
        quote = self._to_quote(market)
        if quote.yes_probability <= 0.0 or quote.yes_probability >= 1.0:
            raise RuntimeError(
                "Could not derive a tradable probability from Kalshi quote data."
            )
        return quote

    def fetch_event_markets(self, event_ticker: str, limit: int = 200) -> list[MarketQuote]:
        payload = self._get_json("/markets", params={"event_ticker": event_ticker, "limit": limit})
        markets = payload.get("markets", [])
        quotes: list[MarketQuote] = []
        for market in markets:
            if isinstance(market, dict):
                quote = self._to_quote(market)
                if 0.0 < quote.yes_probability < 1.0:
                    quotes.append(quote)
        return quotes

    def _to_quote(self, market: dict[str, object]) -> MarketQuote:
        yes_bid = _normalize_probability(market.get("yes_bid_dollars"), market.get("yes_bid"))
        yes_ask = _normalize_probability(market.get("yes_ask_dollars"), market.get("yes_ask"))
        last_price = _normalize_probability(
            market.get("last_price_dollars"), market.get("last_price")
        )

        tradable_prices = [price for price in (yes_bid, yes_ask, last_price) if price is not None and price > 0.0]
        if yes_bid is not None and yes_ask is not None and yes_bid > 0.0 and yes_ask > 0.0:
            yes_probability = (yes_bid + yes_ask) / 2.0
        elif yes_ask is not None and yes_ask > 0.0:
            yes_probability = yes_ask
        elif yes_bid is not None and yes_bid > 0.0:
            yes_probability = yes_bid
        elif last_price is not None and last_price > 0.0:
            yes_probability = last_price
        elif tradable_prices:
            yes_probability = tradable_prices[0]
        else:
            yes_probability = 0.0

        return MarketQuote(
            source="kalshi",
            contract_ticker=str(market.get("ticker", "")),
            event_ticker=(
                str(market.get("event_ticker"))
                if market.get("event_ticker") is not None
                else None
            ),
            title=str(market.get("title")) if market.get("title") is not None else None,
            subtitle=(
                str(market.get("subtitle"))
                if market.get("subtitle") is not None
                else None
            ),
            yes_probability=yes_probability,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            last_price=last_price,
            fetched_at_utc=datetime.now(timezone.utc),
        )

