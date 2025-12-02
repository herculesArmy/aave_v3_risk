# Aave V3 Protocol Value at Risk Analysis

Comprehensive Monte Carlo simulation framework for measuring protocol-level bad debt risk on Aave V3 Ethereum mainnet.

**📊 For the complete risk analysis and assignment answers, see [`ASSIGNMENT_ANSWERS.md`](./ASSIGNMENT_ANSWERS.md)**

---

## Overview

This repository implements a full-stack risk analysis pipeline:

1. **Data Collection**: Fetch top 1,000 borrowers from The Graph
2. **Volatility Calculation**: 90-day historical volatility and covariance matrix
3. **Monte Carlo Simulation**: 10,000 correlated price scenarios
4. **VaR Calculation**: Measure protocol-level bad debt risk
5. **Visualization**: Generate comprehensive risk dashboards

**Key Result**: 99% VaR = **$3.20 billion** (15.30% of total collateral)

---

## Features

- ✅ GraphQL data fetching from The Graph Network (Aave V3 subgraph)
- ✅ CoinGecko API integration for current and historical prices
- ✅ PostgreSQL database with 9 tables (3-layer architecture)
- ✅ Multivariate normal distribution for correlated price shocks
- ✅ User-level bad debt calculation with liquidation threshold mechanics
- ✅ Comprehensive visualizations (7-panel dashboard, concentration analysis)
- ✅ Full SQL query interface for simulation results

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
python3 setup_database.py
```

### Run Complete Pipeline

```bash
# Step 1: Fetch top 1,000 borrowers (5-10 minutes)
python3 fetch_aave_positions_final.py

# Step 2: Fetch historical prices and calculate volatility (2-3 minutes)
python3 fetch_historical_prices.py

# Step 3: Run Monte Carlo simulation (2-3 minutes)
python3 monte_carlo_simulation.py

# Step 4: Generate visualizations
python3 create_enhanced_visualizations.py
```

### Output Files

After running the pipeline:

**Visualizations:**
- `var_analysis.png` - 4-panel VaR summary
- `var_comprehensive_dashboard.png` - 7-panel risk dashboard
- `var_concentration_analysis.png` - 4-panel concentration analysis

**Data Exports:**
- `top_1000_borrowed_users.csv` - User-level metrics
- `top1000_borrowed_positions.csv` - Position details
- `top10_supplied_assets_volatility.csv` - Volatility results
- `var_simulation_results.csv` - 10,000 scenario losses

**Reports:**
- `var_interpretation_report.txt` - Plain-language analysis

**Database:**
- All data stored in PostgreSQL (see `DATABASE_SCHEMA.md`)

---

## Database Architecture

The system uses PostgreSQL with 9 tables organized in 3 layers:

### Layer 1: Position Data
- `users` - Top 1,000 borrowers (aggregate metrics)
- `positions` - Individual collateral/debt positions (~5,000 rows)
- `asset_prices` - Current USD prices (10 assets)

### Layer 2: Risk Metrics
- `historical_prices` - 90-day price history (900 rows)
- `asset_volatility` - Daily volatility calculations (10 rows)
- `asset_covariance` - Correlation matrix (100 rows: 10×10)

### Layer 3: Simulation Results
- `simulation_runs` - Monte Carlo run metadata (1 row per run)
- `scenario_results` - Bad debt per scenario (10,000 rows)
- `simulated_prices` - Price trajectories (1,000 sampled rows)

**📘 For complete schema details, relationships, and 8+ query patterns, see [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md)**

---

## Usage Examples

### Query Top Borrowers

```bash
python3 query_positions.py
```

Or directly via SQL:

```sql
-- Top 10 users by debt
SELECT
    user_address,
    total_debt_usd,
    total_collateral_usd,
    health_factor
FROM users
ORDER BY total_debt_usd DESC
LIMIT 10;
```

### Query Simulation Results

```sql
-- Get latest VaR metrics
SELECT
    n_scenarios,
    var_95,
    var_99,
    var_99_9,
    mean_bad_debt
FROM simulation_runs
ORDER BY run_id DESC
LIMIT 1;

-- Find worst scenarios
SELECT
    scenario_id,
    total_bad_debt
FROM scenario_results
WHERE run_id = (SELECT MAX(run_id) FROM simulation_runs)
ORDER BY total_bad_debt DESC
LIMIT 10;
```

### Update Prices

```bash
# Refresh current prices from CoinGecko
python3 update_prices.py
```

---

## Project Structure

```
chaos_labs/
├── ASSIGNMENT_ANSWERS.md              # Complete risk analysis report
├── DATABASE_SCHEMA.md                 # Database documentation
├── README.md                          # This file (setup & usage)
│
├── fetch_aave_positions_final.py      # Fetch top 1,000 borrowers
├── fetch_historical_prices.py         # Historical prices + volatility
├── monte_carlo_simulation.py          # VaR simulation (10,000 scenarios)
├── create_enhanced_visualizations.py  # Generate risk charts
│
├── price_fetcher.py                   # CoinGecko utility
├── setup_database.py                  # Database initialization
├── query_positions.py                 # Query utilities
├── update_prices.py                   # Price update script
├── check_subgraph_schema.py           # Schema debugging tool
│
├── requirements.txt                   # Python dependencies
├── .env.example                       # Example environment config
└── quickstart.sh                      # Automated setup script
```

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

### Key Parameters (monte_carlo_simulation.py)

```python
# Monte Carlo parameters
N_SIMULATIONS = 10_000      # Number of scenarios
RANDOM_SEED = 42             # For reproducibility
TIME_HORIZON = 1             # 1-day VaR (industry standard)

# Price shock generation
MEAN_RETURN = [0, 0, ..., 0]     # Zero drift
COV_MATRIX = empirical_cov        # From 90-day history
```

---

## Technical Details

### Methodology Overview

**1. Data Collection** (`fetch_aave_positions_final.py`)
- GraphQL query to The Graph for top 1,000 borrowers
- Fetch user positions with liquidation thresholds
- Store in PostgreSQL `users` and `positions` tables

**2. Volatility Calculation** (`fetch_historical_prices.py`)
- Fetch 90-day daily close prices from CoinGecko
- Calculate log returns: `r_t = ln(P_t / P_{t-1})`
- Daily volatility: `σ = √[1/(T-1) × Σ(r_t - r̄)²]`
- Build 10×10 covariance matrix: `Σ = Cov(returns)`

**3. Monte Carlo Simulation** (`monte_carlo_simulation.py`)
- Generate correlated returns: `r ~ MultivariateNormal(μ=0, Σ)`
- Convert to prices: `P_new = P_0 × exp(r)`
- For each scenario (10,000 total):
  - Calculate user-level bad debt: `max(0, Debt - Collateral×LT)`
  - Aggregate across 1,000 users → scenario loss
- Store results in `simulation_runs`, `scenario_results`, `simulated_prices`

**4. VaR Calculation**
- Sort 10,000 losses
- Extract percentiles: VaR(95%), VaR(99%), VaR(99.9%)
- Calculate Expected Shortfall: `ES = mean(losses > VaR)`

**5. Visualization** (`create_enhanced_visualizations.py`)
- 7-panel comprehensive dashboard
- Concentration risk analysis
- Correlation heatmaps

**📊 For complete methodology, results, and interpretation, see [`ASSIGNMENT_ANSWERS.md`](./ASSIGNMENT_ANSWERS.md)**

---

## Key Results Summary

| Metric | Value | % of Collateral |
|--------|-------|----------------|
| **Mean Bad Debt** | $3,057,608,242 | 14.62% |
| **95% VaR** | $3,154,903,458 | 15.09% |
| **99% VaR** | $3,198,965,308 | 15.30% |
| **99.9% VaR** | $3,248,522,494 | 15.53% |
| **Expected Shortfall (99%)** | $3,221,645,328 | 15.41% |
| **Standard Deviation** | $58,021,959 | 0.28% |

**Total Collateral**: $20,911,279,070 (top 1,000 borrowers)
**Total Debt**: $14,831,667,113

### Key Findings

1. **Modeled Liquidation Shortfall**: $3.06B baseline due to liquidation threshold mechanics
2. **Tight Distribution**: σ = $58M (1.9% of mean) due to high ETH/LST correlation
3. **Concentration Risk**: Top 10 users = 43.7% of total exposure
4. **ETH Dominance**: 72% of collateral is WETH/weETH/wstETH
5. **Limited Tail Risk**: Within Gaussian framework; actual tail risk may be higher during LST depegs

**📊 For detailed findings, assumptions, and limitations, see [`ASSIGNMENT_ANSWERS.md`](./ASSIGNMENT_ANSWERS.md)**

---

## Troubleshooting

### Common Issues

**1. Database Connection Error**
```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -d aave_positions

# Reset database
python3 setup_database.py
```

**2. The Graph API Rate Limit**
```bash
# Adjust pagination in fetch_aave_positions_final.py
BATCH_SIZE = 100  # Reduce from 1000
```

**3. CoinGecko API Rate Limit**
```bash
# Add delays in fetch_historical_prices.py
time.sleep(1.2)  # Free tier: 50 calls/min
```

**4. Simulation Memory Issues**
```python
# Reduce scenarios in monte_carlo_simulation.py
N_SIMULATIONS = 1000  # Instead of 10,000
```

---

## Development

### Running Tests

```bash
# (Future) Add pytest tests
pytest tests/
```

### Database Maintenance

```bash
# Export database
pg_dump -h localhost -U postgres aave_positions > backup.sql

# Clean old simulation runs (keep latest 5)
psql -h localhost -U postgres -d aave_positions -c "
DELETE FROM simulation_runs
WHERE run_id NOT IN (
    SELECT run_id FROM simulation_runs
    ORDER BY run_id DESC LIMIT 5
);"
```

### Adding New Assets

1. Add asset symbol to `fetch_historical_prices.py`:
   ```python
   ASSET_SYMBOLS = ['WETH', 'WBTC', ..., 'NEW_ASSET']
   ```

2. Add CoinGecko ID mapping in `price_fetcher.py`:
   ```python
   SYMBOL_TO_COINGECKO = {
       'NEW_ASSET': 'new-asset-id',
       ...
   }
   ```

3. Re-run pipeline:
   ```bash
   python3 fetch_historical_prices.py
   python3 monte_carlo_simulation.py
   ```

---

## Documentation

- **[ASSIGNMENT_ANSWERS.md](./ASSIGNMENT_ANSWERS.md)** - Complete risk analysis with methodology, results, and interpretation
- **[DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)** - Database tables, relationships, and query patterns
- **README.md** - This file (setup, installation, usage)

---

## Dependencies

Core packages (see `requirements.txt`):

```
psycopg2-binary==2.9.9    # PostgreSQL adapter
requests==2.31.0          # HTTP client (CoinGecko API)
python-dotenv==1.0.0      # Environment variables
numpy==1.24.3             # Numerical computing
pandas==2.0.3             # Data manipulation
matplotlib==3.7.2         # Visualization
seaborn==0.12.2           # Statistical plots
```

---

## License

MIT

---

## Contact

For questions about the analysis methodology or implementation, see:
- **Assignment Answers**: `ASSIGNMENT_ANSWERS.md` (Questions 1-5, assumptions, limitations)
- **Database Queries**: `DATABASE_SCHEMA.md` (8+ common query patterns)
- **Issues**: [GitHub Issues](your-repo-url/issues)

---

**Last Updated**: December 2, 2025
**Analysis Date**: December 2, 2025
**Data Source**: Aave V3 Ethereum Mainnet (The Graph), CoinGecko API
