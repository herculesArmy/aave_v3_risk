# Database Schema & Usage Guide

Complete reference for all PostgreSQL tables in the Aave V3 risk analysis system.

---

## Overview

The database contains **9 tables** across three layers:

| Layer | Tables | Purpose |
|-------|--------|---------|
| **Position Data** | `users`, `positions`, `asset_prices` | Current Aave V3 state |
| **Risk Metrics** | `historical_prices`, `asset_volatility`, `asset_covariance` | Volatility & correlation |
| **Simulation** | `simulation_runs`, `scenario_results`, `simulated_prices` | Monte Carlo outputs |

---

## Table Schemas

### `users` (1,000 rows)

Aggregate metrics for each borrower.

```sql
CREATE TABLE users (
    user_address VARCHAR PRIMARY KEY,
    total_debt_usd NUMERIC,
    total_collateral_usd NUMERIC,
    health_factor NUMERIC,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields:**
- `health_factor` - Liquidation risk: HF < 1.0 = liquidatable

**Sample Query:**
```sql
SELECT user_address, total_debt_usd, health_factor
FROM users
WHERE health_factor < 1.0
ORDER BY total_debt_usd DESC;
```

---

### `positions` (3,325 rows)

Individual asset positions (collateral or debt) for each user.

```sql
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    user_address VARCHAR,
    asset_address VARCHAR,
    symbol VARCHAR,
    side VARCHAR,  -- 'collateral' or 'debt'
    amount NUMERIC,
    amount_usd NUMERIC,
    price_usd NUMERIC,
    price_timestamp TIMESTAMP,
    liquidation_threshold NUMERIC,
    base_ltv_as_collateral NUMERIC,
    liquidation_bonus NUMERIC,
    debt_ceiling NUMERIC,
    borrowable_in_isolation BOOLEAN,
    emode_category_id INTEGER,
    is_frozen BOOLEAN,
    borrow_cap NUMERIC,
    supply_cap NUMERIC,
    borrowing_enabled BOOLEAN,
    is_active BOOLEAN,
    usage_as_collateral_enabled BOOLEAN,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields:**
- `side` - Either `'collateral'` or `'debt'`
- `usage_as_collateral_enabled` - Only `true` positions count toward Health Factor
- `liquidation_threshold` - Max % borrowable (e.g., 0.81 = 81%)

---

### `asset_prices` (57 rows)

Current USD prices for all assets.

```sql
CREATE TABLE asset_prices (
    asset_address VARCHAR PRIMARY KEY,
    symbol VARCHAR,
    price_usd NUMERIC,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Query:**
```sql
SELECT symbol, price_usd FROM asset_prices WHERE price_usd > 0 ORDER BY price_usd DESC;
```

---

### `historical_prices` (2,170 rows)

90 days of daily closing prices (24 assets × 90 days).

```sql
CREATE TABLE historical_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    date DATE NOT NULL,
    close_price NUMERIC NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
```

**Sample Query:**
```sql
SELECT date, close_price FROM historical_prices WHERE symbol = 'WETH' ORDER BY date DESC LIMIT 10;
```

---

### `asset_volatility` (24 rows)

Daily and annualized volatility for each asset.

```sql
CREATE TABLE asset_volatility (
    symbol VARCHAR PRIMARY KEY,
    current_price NUMERIC,
    min_price NUMERIC,
    max_price NUMERIC,
    price_range_pct NUMERIC,
    daily_volatility NUMERIC,
    annualized_volatility NUMERIC,
    annualized_volatility_pct NUMERIC,
    days_analyzed INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Query:**
```sql
SELECT symbol, annualized_volatility_pct FROM asset_volatility ORDER BY annualized_volatility_pct DESC;
```

**Sample Results:**
```
FXS:    134.81% (most volatile)
AAVE:   91.41%
WETH:   67.10%
USDC:   0.14% (stablecoin)
```

---

### `asset_covariance` (576 rows)

Pairwise covariance and correlation (24×24 matrix).

```sql
CREATE TABLE asset_covariance (
    asset1 VARCHAR NOT NULL,
    asset2 VARCHAR NOT NULL,
    covariance NUMERIC,
    correlation NUMERIC,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asset1, asset2)
);
```

**Sample Query:**
```sql
SELECT asset1, asset2, correlation
FROM asset_covariance
WHERE asset1 IN ('WETH', 'weETH', 'wstETH', 'rsETH')
  AND asset2 IN ('WETH', 'weETH', 'wstETH', 'rsETH')
ORDER BY asset1, asset2;
```

**Sample Results:**
```
WETH  ↔ weETH:  0.9997 (near-perfect correlation)
WETH  ↔ rsETH:  0.9981
rsETH ↔ ezETH:  0.9995
```

---

### `simulation_runs` (2 rows)

Metadata for each Monte Carlo simulation run.

```sql
CREATE TABLE simulation_runs (
    run_id SERIAL PRIMARY KEY,
    n_scenarios INTEGER NOT NULL,
    random_seed INTEGER,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    var_95 NUMERIC,
    var_99 NUMERIC,
    var_99_9 NUMERIC,
    mean_bad_debt NUMERIC,
    std_bad_debt NUMERIC
);
```

**Sample Query:**
```sql
SELECT run_id, n_scenarios, var_99, mean_bad_debt, run_timestamp
FROM simulation_runs ORDER BY run_id DESC LIMIT 1;
```

**Latest Results:**
```
run_id: 2
n_scenarios: 10,000
var_99: $1,431,782,054
mean_bad_debt: $1,352,047,741
```

---

### `scenario_results` (20,000 rows)

Bad debt for each scenario (10,000 per run × 2 runs).

```sql
CREATE TABLE scenario_results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER,
    scenario_id INTEGER NOT NULL,
    total_bad_debt NUMERIC,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Query:**
```sql
-- Find worst scenarios
SELECT scenario_id, total_bad_debt
FROM scenario_results
WHERE run_id = (SELECT MAX(run_id) FROM simulation_runs)
ORDER BY total_bad_debt DESC
LIMIT 5;
```

---

### `simulated_prices` (340,000 rows)

Price trajectories for all scenarios (10,000 scenarios × 24 assets × 2 runs).

```sql
CREATE TABLE simulated_prices (
    id SERIAL PRIMARY KEY,
    run_id INTEGER,
    scenario_id INTEGER NOT NULL,
    asset_symbol VARCHAR NOT NULL,
    current_price NUMERIC,
    simulated_price NUMERIC,
    return_pct NUMERIC,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Query:**
```sql
-- Get price trajectory for worst scenario
SELECT asset_symbol, current_price, simulated_price, return_pct
FROM simulated_prices
WHERE run_id = (SELECT MAX(run_id) FROM simulation_runs)
  AND scenario_id = 5469  -- Worst scenario
ORDER BY ABS(return_pct) DESC;
```

**Sample Results (Worst Case #5469):**
```
WETH:   $2,825 → $3,214 (+12.91%)
weETH:  $3,057 → $3,474 (+12.79%)
rsETH:  $2,990 → $3,387 (+12.47%)
```

---

## Row Count Summary

| Table | Rows | Description |
|-------|------|-------------|
| `users` | 1,000 | Top 1,000 borrowers |
| `positions` | 3,325 | All positions for top borrowers |
| `asset_prices` | 57 | Current prices (46 with valid data) |
| `historical_prices` | 2,170 | 90 days × 24 assets |
| `asset_volatility` | 24 | Volatility metrics per asset |
| `asset_covariance` | 576 | 24×24 correlation matrix |
| `simulation_runs` | 3 | Simulation metadata |
| `scenario_results` | 30,000 | 10,000 scenarios × 3 runs |
| `simulated_prices` | 580,000 | All price trajectories |

---

## Common Queries

### Calculate VaR from Scenario Results

```sql
SELECT
    percentile_cont(0.95) WITHIN GROUP (ORDER BY total_bad_debt) AS var_95,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY total_bad_debt) AS var_99,
    AVG(total_bad_debt) AS mean,
    STDDEV(total_bad_debt) AS std_dev
FROM scenario_results
WHERE run_id = (SELECT MAX(run_id) FROM simulation_runs);
```

### Find Users at Risk

```sql
SELECT user_address, total_debt_usd, total_collateral_usd, health_factor
FROM users
WHERE health_factor < 1.2 AND total_debt_usd > 1000000
ORDER BY health_factor ASC
LIMIT 20;
```

### Asset Exposure Analysis

```sql
SELECT
    symbol,
    SUM(amount_usd) as total_exposure,
    COUNT(*) as num_positions,
    AVG(liquidation_threshold) as avg_lt
FROM positions
WHERE side = 'collateral'
GROUP BY symbol
ORDER BY total_exposure DESC;
```

### Correlation Between Assets

```sql
SELECT asset1, asset2, correlation
FROM asset_covariance
WHERE correlation > 0.95 AND asset1 != asset2
ORDER BY correlation DESC;
```

---

## Data Pipeline

```
1. FETCH POSITIONS (fetch_aave_positions_final.py)
   └─▶ users, positions, asset_prices

2. FETCH PRICES (fetch_historical_prices.py)
   └─▶ historical_prices
   └─▶ asset_volatility
   └─▶ asset_covariance

3. RUN SIMULATION (monte_carlo_simulation.py)
   └─▶ simulation_runs
   └─▶ scenario_results
   └─▶ simulated_prices

4. VISUALIZE (create_visualizations.py)
   └─▶ var_comprehensive_dashboard.png
   └─▶ var_hf_stress_analysis.png
   └─▶ var_concentration_analysis.png
   └─▶ asset_composition_supplied_vs_borrowed.png
```

---

## Backup Commands

```bash
# Export full database
pg_dump -h localhost -U postgres aave_positions > backup.sql

# Export table to CSV
psql -h localhost -U postgres -d aave_positions \
  -c "\COPY scenario_results TO 'scenario_results.csv' CSV HEADER"
```

---

**Last Updated**: December 2, 2025
**Assets Tracked**: 24 (with CoinGecko prices)
**Simulation**: 10,000 scenarios × 1,000 users
