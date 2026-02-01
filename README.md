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
- Market pricing feeds (Kalshi / Polymarket)

---

## Roadmap

- [x] NOAA ingestion + ensemble probability computation (prototype for one test event)
- [ ] Market price scraper + implied probability engine
- [ ] Edge detection + trade signal generator
- [ ] Backtesting framework
- [ ] Automated execution + bankroll rules

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

Run:

```bash
python3 scripts/gefs_event_probability.py
```

Example with custom threshold:

```bash
python3 scripts/gefs_event_probability.py --threshold-f 30
```

---

## Philosophy

Zephyr is built on one principle:

> Trade weather markets like quant probability arbitrage, not gambling.

Forecasts are data. Prices are probabilities. Profit is the gap.

---
