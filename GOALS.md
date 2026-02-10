# Zephyr Goals

## End Goal
Build a profitable, repeatable strategy that identifies and trades weather- and temperature-related Polymarket contracts when forecast-implied probabilities differ materially from market-implied probabilities.

## What “Works” Means
- Positive, risk-adjusted profitability over a meaningful sample (months, not days).
- Edge is driven by forecast-vs-market probability gaps, not random variance.
- Strategy remains profitable after reasonable frictions (slippage, fees, latency).
- Position sizing is conservative and survivable across adverse runs.

## Current Milestone
Prove the pipeline works end-to-end before automation:
1. Pull Polymarket weather/temperature markets.
2. Match each market to a well-defined forecast event spec.
3. Compute forecast probability from reputable weather sources.
4. Compare to market-implied probability and size a paper trade.
5. Log outcomes and verify edge over time.

## Strategy Principles
- Forecasts are probabilities; market prices are probabilities.
- Only trade when the probability gap is large and stable.
- Prefer ensemble-based forecasts and cross-model agreement.
- Preserve capital: small positions, diversified events, strict caps.

## Reputable Weather Sources to Use
- NOAA GEFS ensembles (already implemented).
- ECMWF ensemble probabilities.
- HRRR nowcasts for near-term events.
- Official alerts/bulletins for high-impact events.

## Required Components (Minimum Viable Version)
- Market ingestion: Polymarket API client for weather/temperature contracts.
- Event mapping: deterministic mapping from market to forecast event spec.
- Forecast probability: ensemble-based computation with timestamps.
- Signal engine: edge detection + EV check.
- Risk engine: fractional Kelly + per-contract cap.
- Paper execution: logging trades + outcomes for backtesting.

## Validation Plan
- Run daily paper trades for a defined set of markets.
- Store all forecast snapshots and market prices.
- Evaluate PnL and edge consistency monthly.
- Stop or tighten thresholds if drawdowns exceed predefined limits.

## Non-Goals (For Now)
- Fully automated live trading.
- Multi-venue arbitrage.
- Complex ML models before the baseline proves edge.

## Risks to Monitor
- Bad market-to-forecast mapping (date, location, threshold mismatches).
- Data latency and model update timing.
- Overfitting on small samples.
- Changing market structure or liquidity.

## Success Criteria to Unlock Automation
- Statistically meaningful positive edge with stable risk controls.
- Clear evidence that the edge persists out of sample.
- Robust monitoring and stop-loss rules.
