# Aave V3 Protocol Value at Risk Analysis

Comprehensive Monte Carlo simulation framework for measuring protocol-level bad debt risk on Aave V3 Ethereum mainnet.

**For the complete risk analysis and assignment answers, see [`docs/ASSIGNMENT_ANSWERS.md`](./docs/ASSIGNMENT_ANSWERS.md)**

---

## Overview

This repository implements a full-stack risk analysis pipeline:

1. **Data Collection**: Fetch top 1,000 borrowers from The Graph
2. **Volatility Calculation**: 90-day historical volatility and covariance matrix (24 assets)
3. **Monte Carlo Simulation**: 10,000 correlated price scenarios
4. **VaR Calculation**: Measure protocol-level bad debt risk
5. **Visualization**: Generate comprehensive risk dashboards

**Key Result**: 99% VaR = **$1.43 billion** (6.09% of total collateral)

---

## Features

- GraphQL data fetching from The Graph Network (Aave V3 subgraph)
- CoinGecko API integration for current and historical prices
- PostgreSQL database with 9 tables (3-layer architecture)
- Multivariate normal distribution for correlated price shocks
- User-level bad debt calculation with liquidation threshold mechanics
- Comprehensive visualizations (10-panel dashboard, concentration analysis)
- Full SQL query interface for simulation results

---

## Quick Start

### Prerequisites

- Python 3.8+
- PostgreSQL 14+
- The Graph API key
- CoinGecko API key

### Installation

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd chaos_labs

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your API keys and database credentials

# 5. Setup database
python3 scripts/setup_database.py
```

### Run Complete Pipeline

```bash
# Step 1: Fetch top 1,000 borrowers (5-10 minutes)
python3 scripts/fetch_aave_positions_final.py

# Step 2: Fetch historical prices and calculate volatility (2-3 minutes)
python3 scripts/fetch_historical_prices.py

# Step 3: Run Monte Carlo simulation (2-3 minutes)
python3 scripts/monte_carlo_simulation.py

# Step 4: Generate visualizations
python3 scripts/create_visualizations.py
```

### Output Files

After running the pipeline:

**Visualizations** (`visualizations/`):
- `var_analysis.png` - 4-panel VaR summary
- `var_comprehensive_dashboard.png` - 10-panel risk dashboard
- `var_concentration_analysis.png` - Concentration analysis
- `var_hf_stress_analysis.png` - Health factor stress analysis
- `asset_composition_supplied_vs_borrowed.png` - Collateral vs Debt composition

**Data Exports** (`data/`):
- `top_1000_borrowed_users.csv` - User-level metrics
- `top_1000_borrowed_positions.csv` - Position details
- `top_10_asset_volatility.csv` - Volatility results
- `var_simulation_results.csv` - 10,000 scenario losses

**Documentation** (`docs/`):
- `ASSIGNMENT_ANSWERS.md` - Complete risk analysis report
- `DATABASE_SCHEMA.md` - Database documentation

**Database:**
- All data stored in PostgreSQL (see `docs/DATABASE_SCHEMA.md`)

---

## Database Architecture

The system uses PostgreSQL with 9 tables organized in 3 layers:

### Layer 1: Position Data
- `users` - Top 1,000 borrowers (aggregate metrics)
- `positions` - Individual collateral/debt positions (3,325 rows)
- `asset_prices` - Current USD prices (57 assets)

### Layer 2: Risk Metrics
- `historical_prices` - 90-day price history (2,170 rows)
- `asset_volatility` - Daily volatility calculations (24 rows)
- `asset_covariance` - Correlation matrix (576 rows: 24x24)

### Layer 3: Simulation Results
- `simulation_runs` - Monte Carlo run metadata
- `scenario_results` - Bad debt per scenario (10,000 rows per run)
- `simulated_prices` - Price trajectories (240,000 rows per run)

**For complete schema details, see [`docs/DATABASE_SCHEMA.md`](./docs/DATABASE_SCHEMA.md)**

---

## Project Structure

```
chaos_labs/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # Example environment config
│
├── scripts/                     # Python scripts
│   ├── setup_database.py        # Database initialization
│   ├── fetch_aave_positions_final.py  # Fetch top 1,000 borrowers
│   ├── fetch_historical_prices.py     # Historical prices + volatility
│   ├── monte_carlo_simulation.py      # VaR simulation
│   ├── create_visualizations.py       # Generate charts
│   ├── price_fetcher.py               # CoinGecko utility
│   ├── update_prices.py               # Price refresh script
│   └── query_positions.py             # Query utilities
│
├── data/                        # CSV exports
│   ├── top_1000_borrowed_users.csv
│   ├── top_1000_borrowed_positions.csv
│   ├── top_10_asset_volatility.csv
│   └── var_simulation_results.csv
│
├── visualizations/              # Generated charts
│   ├── var_comprehensive_dashboard.png
│   ├── var_analysis.png
│   └── ...
│
└── docs/                        # Documentation
    ├── ASSIGNMENT_ANSWERS.md    # Complete risk analysis
    └── DATABASE_SCHEMA.md       # Database documentation
```

---

## Key Results Summary

| Metric | Value | % of Collateral |
|--------|-------|----------------|
| **Mean Bad Debt** | $1,352,047,741 | 5.75% |
| **95% VaR** | $1,406,009,063 | 5.98% |
| **99% VaR** | $1,431,782,054 | 6.09% |
| **99.9% VaR** | $1,459,925,904 | 6.21% |
| **Expected Shortfall (99%)** | $1,443,693,342 | 6.14% |
| **Standard Deviation** | $32,759,267 | 0.14% |

**Total Collateral**: $23,517,177,668 (top 1,000 borrowers)
**Total Debt**: $14,810,549,648
**Assets Tracked**: 24 (with CoinGecko prices)

### Key Findings

1. **Modeled Liquidation Shortfall**: $1.35B baseline due to liquidation threshold mechanics
2. **Tight Distribution**: Low variance due to high ETH/LST correlation (>0.99)
3. **Concentration Risk**: Top 10 users = ~40% of total exposure
4. **ETH Dominance**: ~62% of collateral is WETH/weETH/wstETH

**For detailed findings, assumptions, and limitations, see [`docs/ASSIGNMENT_ANSWERS.md`](./docs/ASSIGNMENT_ANSWERS.md)**

---

## Configuration

### Environment Variables (.env)

```bash
# The Graph Network
SUBGRAPH_URL=https://gateway-arbitrum.network.thegraph.com/api/YOUR_API_KEY/subgraphs/id/Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g

# CoinGecko
COINGECKO_API_KEY=your_key_here

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aave_positions
DB_USER=postgres
DB_PASSWORD=your_password
```

---

## Troubleshooting

### Common Issues

**1. Database Connection Error**
```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -d aave_positions

# Reset database
python3 scripts/setup_database.py
```

**2. The Graph API Rate Limit**
```bash
# Adjust pagination in scripts/fetch_aave_positions_final.py
BATCH_SIZE = 100  # Reduce if needed
```

**3. CoinGecko API Rate Limit**
```bash
# Scripts include 2-3 second delays for rate limiting
# Free tier: 50 calls/min
```

---

## Documentation

- **[docs/ASSIGNMENT_ANSWERS.md](./docs/ASSIGNMENT_ANSWERS.md)** - Complete risk analysis with methodology, results, and interpretation
- **[docs/DATABASE_SCHEMA.md](./docs/DATABASE_SCHEMA.md)** - Database tables, relationships, and query patterns
- **README.md** - This file (setup, installation, usage)

---

## Dependencies

Core packages (see `requirements.txt`):

```
psycopg2-binary    # PostgreSQL adapter
requests           # HTTP client (CoinGecko API)
python-dotenv      # Environment variables
numpy              # Numerical computing
pandas             # Data manipulation
scipy              # Statistical functions
matplotlib         # Visualization
seaborn            # Statistical plots
tqdm               # Progress bars
```

---

## License

MIT

---

**Last Updated**: December 2, 2025
**Analysis Date**: December 2, 2025
**Data Source**: Aave V3 Ethereum Mainnet (The Graph), CoinGecko API
