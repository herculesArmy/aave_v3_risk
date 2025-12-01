# Aave V3 Position Tracker

Comprehensive data collection pipeline for fetching and analyzing top borrow positions on Aave V3 Ethereum Mainnet.

## Features

- ✅ Fetches top 1,000 borrowers from Aave V3 Ethereum mainnet
- ✅ Complete GraphQL data fetching from The Graph Network
- ✅ Real-time USD pricing from CoinGecko API
- ✅ Comprehensive Aave V3 protocol parameters:
  - Proper collateral filtering (usageAsCollateralEnabledOnUser)
  - Liquidation thresholds and LTV ratios
  - Isolation mode and E-mode support
  - Protocol limits (borrow/supply caps)
  - Asset status flags
- ✅ PostgreSQL storage with optimized schema
- ✅ Health factor calculations for liquidation risk

## Database Schema

### Tables
- **users**: Aggregate metrics per user (debt, collateral, health factor)
- **positions**: Individual collateral/debt positions with all Aave v3 fields
- **asset_prices**: USD price cache from CoinGecko

## Setup

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd chaos_labs
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials:
# - The Graph API key
# - CoinGecko API key
# - PostgreSQL credentials
```

5. **Setup database**
```bash
python3 setup_database.py
```

6. **Run data collection**
```bash
python3 fetch_aave_positions_final.py
```

## Usage

### Fetch Latest Data
```bash
python3 fetch_aave_positions_final.py
```

### Query Positions
```bash
python3 query_positions.py
```

### Update Prices
```bash
python3 update_prices.py
```

## SQL Queries

### Top 1,000 Individual Debt Positions
```sql
SELECT *
FROM positions
WHERE side = 'debt'
ORDER BY amount_usd DESC
LIMIT 1000;
```

### Top Borrowers by Total Debt
```sql
SELECT 
    user_address,
    total_debt_usd,
    total_collateral_usd,
    health_factor
FROM users
ORDER BY total_debt_usd DESC
LIMIT 1000;
```

### Risky Positions (Health Factor < 1.1)
```sql
SELECT *
FROM users
WHERE health_factor < 1.1
ORDER BY total_debt_usd DESC;
```

## Configuration

Edit `.env` file:
```
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

# Fetching Parameters
TOP_N_POSITIONS=1000
BATCH_SIZE=100
```

## Project Structure

```
chaos_labs/
├── fetch_aave_positions_final.py  # Main data fetcher (comprehensive)
├── price_fetcher.py               # CoinGecko price fetching
├── setup_database.py              # Database initialization
├── query_positions.py             # Analysis and query utilities
├── update_prices.py               # Price update script
├── check_subgraph_schema.py       # Schema introspection tool
├── requirements.txt               # Python dependencies
├── .env.example                   # Example environment config
└── README.md                      # This file
```

## Critical Fields Explained

- **usageAsCollateralEnabledOnUser**: User-level toggle - only deposits with this enabled count as collateral
- **liquidation_threshold**: Maximum % of collateral value that can be borrowed before liquidation (0-1)
- **base_ltv_as_collateral**: Initial loan-to-value ratio allowed
- **liquidation_bonus**: Incentive for liquidators (e.g., 0.05 = 5% bonus)
- **debt_ceiling**: Max total debt for isolated collateral assets
- **emode_category_id**: Efficiency mode category (higher LTV for correlated assets)
- **health_factor**: Liquidation risk = weighted_collateral / total_debt (< 1.0 = liquidatable)

## License

MIT
