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


def _parse_json_array(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
    return []


def _normalize_outcomes(value: object) -> list[str]:
    raw = _parse_json_array(value)
    return [str(item) for item in raw]


def _normalize_prices(value: object, expected_len: int) -> list[float]:
    raw = _parse_json_array(value)
    if expected_len and len(raw) != expected_len:
        raise RuntimeError("Outcome prices length does not match outcomes length.")
    prices: list[float] = []
    for item in raw:
        parsed = _to_float(item)
        if parsed is None:
            raise RuntimeError("Outcome prices contain non-numeric values.")
        prices.append(parsed)
    return prices


def _find_outcome_index(outcomes: list[str], label: str) -> int | None:
    target = label.strip().lower()
    for idx, outcome in enumerate(outcomes):
        if outcome.strip().lower() == target:
            return idx
    return None


class PolymarketGammaClient:
    def __init__(self, base_url: str = "https://gamma-api.polymarket.com") -> None:
        self.base_url = base_url.rstrip("/")

    def _get_json(self, path: str, params: dict[str, object] | None = None) -> object:
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
                "User-Agent": "zephyr-polymarket-client/1.0",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_market_by_slug(
        self,
        slug: str,
        *,
        yes_label: str = "Yes",
    ) -> MarketQuote:
        payload = self._get_json("/markets", params={"slug": slug})
        market = self._select_market(payload, slug=slug)
        quote = self._to_quote(market, yes_label=yes_label)
        if quote.yes_probability <= 0.0 or quote.yes_probability >= 1.0:
            raise RuntimeError(
                "Could not derive a tradable probability from Polymarket market data."
            )
        return quote

    def list_markets(self, params: dict[str, object] | None = None) -> list[dict[str, object]]:
        payload = self._get_json("/markets", params=params)
        if isinstance(payload, list):
            return [market for market in payload if isinstance(market, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("markets"), list):
            return [
                market
                for market in payload["markets"]
                if isinstance(market, dict)
            ]
        raise RuntimeError("Unexpected Polymarket markets payload shape.")

    @staticmethod
    def _select_market(payload: object, *, slug: str) -> dict[str, object]:
        if isinstance(payload, list):
            if not payload:
                raise RuntimeError(f"No Polymarket markets found for slug '{slug}'.")
            market = payload[0]
        elif isinstance(payload, dict):
            if isinstance(payload.get("markets"), list) and payload["markets"]:
                market = payload["markets"][0]
            elif isinstance(payload.get("market"), dict):
                market = payload["market"]
            else:
                market = payload
        else:
            raise RuntimeError("Unexpected Polymarket API response format.")

        if not isinstance(market, dict):
            raise RuntimeError("Unexpected Polymarket market payload shape.")
        return market

    @staticmethod
    def _to_quote(market: dict[str, object], *, yes_label: str) -> MarketQuote:
        outcomes = _normalize_outcomes(market.get("outcomes"))
        if not outcomes:
            raise RuntimeError("Polymarket market does not include outcomes.")
        prices = _normalize_prices(market.get("outcomePrices"), len(outcomes))
        outcome_index = _find_outcome_index(outcomes, yes_label)
        if outcome_index is None:
            raise RuntimeError(
                f"Outcome label '{yes_label}' not found in Polymarket outcomes: {outcomes}"
            )
        yes_probability = prices[outcome_index]

        condition_id = market.get("conditionId") or market.get("condition_id")
        market_id = market.get("id")
        market_slug = market.get("slug")
        event_slug = market.get("eventSlug") or market.get("event_slug")
        event_id = market.get("eventId") or market.get("event_id")

        contract_ticker = str(condition_id or market_id or market_slug or "")
        event_ticker = str(event_slug or event_id) if (event_slug or event_id) else None
        title = market.get("question") or market.get("title")

        return MarketQuote(
            source="polymarket",
            contract_ticker=contract_ticker,
            event_ticker=event_ticker,
            title=str(title) if title is not None else None,
            subtitle=None,
            yes_probability=yes_probability,
            yes_bid=None,
            yes_ask=None,
            last_price=None,
            fetched_at_utc=datetime.now(timezone.utc),
        )

    @staticmethod
    def quote_from_market(market: dict[str, object], *, yes_label: str = "Yes") -> MarketQuote:
        return PolymarketGammaClient._to_quote(market, yes_label=yes_label)
