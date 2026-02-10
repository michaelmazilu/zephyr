# Zephyr

Zephyr is a weather-driven prediction market trading system focused on exploiting probability mispricing in event-based contracts.

Instead of “guessing” outcomes, Zephyr treats prediction market prices as implied probabilities and compares them to forecast probabilities derived from professional meteorological models.

---

## Core Idea

Prediction markets price contracts like:

- YES = $0.60 → market implies a 60% chance
- NO = $0.40 → market implies a 40% chance

Meanwhile, modern ensemble weather models (NOAA GEFS, ECMWF, HRRR) provide probabilistic forecasts.

Zephyr finds situations where:

> Forecast probability significantly differs from market probability

Example:

- Forecast says 80% chance of >5" snow
- Market is priced at 60%
- Edge = +20% expected value

Zephyr trades only when this gap is large and stable.

---

## Strategy Overview

### 1. Forecast → Probability

Zephyr converts ensemble outputs into probabilities:

\[
P(event) = \frac{\#runs\ exceeding\ threshold}{N}
\]

Example:

- 42 of 50 runs predict >5 inches snow  
  → Forecast probability = 84%

---

### 2. Market Price → Probability

Market price is treated directly as probability:

\[
P\_{market} = price
\]

---

### 3. Trade Only When Mispricing Is Large

Zephyr enters positions only if:

- Probability gap exceeds 10–20%
- Multiple models agree
- Forecast confidence is increasing

---

## Best Target Markets

Zephyr performs best on clean threshold contracts:

- Temperature cutoffs  
  “Will NYC exceed 85°F tomorrow?”
- Snowfall totals  
  “Will Boston get >3 inches this week?”
- Hurricane landfall events

These markets are more structured and forecastable than vague outcomes.

---

## Risk Management

Weather has variance, even with strong models.

Zephyr enforces strict bankroll controls:

- Max 2–3% exposure per contract
- Portfolio of many small edges
- No single-event oversized bets

Long-term profitability comes from repetition, not jackpots.

---

## Data Sources

Planned integrations include:

- NOAA GEFS ensemble forecasts
- ECMWF ensemble probabilities
- HRRR radar nowcasts
- Emergency bulletins and alerts
- Market pricing feeds (Polymarket)

---

## Roadmap

- [x] NOAA ingestion + ensemble probability computation (prototype for one test event)
- [x] Market price scraper + implied probability engine (Polymarket public quote pull)
- [x] Edge detection + trade signal generator
- [x] Backtesting framework (CSV-driven)
- [x] Automated execution + bankroll rules (paper-order logging + fractional Kelly + hard cap)

---

## Run The Prototype

This repository now includes a first working step for GEFS ingestion and event-probability computation:

`scripts/gefs_event_probability.py`

It pulls the latest GEFS ensemble run from NOAA NOMADS and computes:

\[
P(event) = \frac{runs\ exceeding\ threshold}{total\ runs}
\]

Default test event:

- NYC max 2m temperature tomorrow (America/New_York) >= 85F

Precipitation events are also supported in the pipeline (e.g., total precip >= 0.1 in),
and can be logged via `scripts/log_snapshots.py` when Polymarket markets match the filters.

Run:

```bash
python3 scripts/gefs_event_probability.py
```

Example with custom threshold:

```bash
python3 scripts/gefs_event_probability.py --threshold-f 30
```

---

## Generate A Trade Signal

Build a forecast probability from GEFS and compare it to a market implied probability.

Option A (manual market probability):

```bash
python3 scripts/generate_signal.py --market-probability 0.42
```

Option B (live Polymarket quote by market slug):

```bash
python3 scripts/generate_signal.py --polymarket-slug your-market-slug
```

Precipitation example:

```bash
python3 scripts/generate_signal.py \
  --event-type precip_total \
  --threshold-in 0.1 \
  --polymarket-slug your-market-slug
```

Paper-log orders when a trade is triggered:

```bash
python3 scripts/generate_signal.py \
  --market-probability 0.42 \
  --paper-ledger data/paper_orders.csv
```

---

## Run A Backtest

Run the built-in sample backtest:

```bash
python3 scripts/run_backtest.py
```

Show per-trade detail:

```bash
python3 scripts/run_backtest.py --show-trades
```

Use your own CSV:

```bash
python3 scripts/run_backtest.py --csv path/to/your_backtest.csv
```

CSV columns:

- `event_id`
- `contract_ticker`
- `forecast_probability`
- `market_probability`
- `outcome` (`1` for YES outcome, `0` for NO outcome)
- optional: `timestamp`

---

## Log Recent Snapshots (SQLite)

Discover Polymarket weather/temperature markets (filtered by volume, city, and date window),
compute GEFS probabilities, and store snapshots in SQLite:

```bash
python3 scripts/log_snapshots.py --db data/zephyr.sqlite
```

Use `data/market_universe.json` to tune cities, volume, and date window.

Record a resolved outcome:

```bash
python3 scripts/record_outcome.py --market-slug your-market-slug --outcome 1
```

Export joined snapshots + outcomes for backtesting:

```bash
python3 scripts/build_backtest_from_db.py --db data/zephyr.sqlite
```

Then run the backtest:

```bash
python3 scripts/run_backtest.py --csv data/backtest_from_db.csv
```

---

## Philosophy

Zephyr is built on one principle:

> Trade weather markets like quant probability arbitrage, not gambling.

Forecasts are data. Prices are probabilities. Profit is the gap.

---
