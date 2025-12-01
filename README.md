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

## Questions

### 1. Get the top 1,000 borrow positions on Aave v3 Ethereum main Deployment.

#### Top 1000 borrow positions
```sql
SELECT *
FROM positions
WHERE side = 'debt'
ORDER BY amount_usd DESC
LIMIT 1000;
```
#### Top 1000 Borrowers users by Total Debt
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


### 2. Calculate the volatility of the top 10 supplied assets on Aave. 

#### Explain how the volatility was measured and over which time period. You may use any public data source (e.g., Coingecko, Binance),Our goal is to build a simulation framework to estimate the value at risk of the protocol.

- In this case we use 90 days daily close prices historical data. The reason for this is that I beleive crypto market are in different regime over a long period. So using data point like 365 days might dilute the current regime which seems bearish post 10/10 (while we are more bullish earlier in the year). And 90 days provide enough data point for a Vol estimate. 180 days could work too

#### Top 10 supplied asset
````sql
   select symbol, sum(amount_usd) as total_supplied_usd
   from positions
   where side = 'collateral'
   group by 1
   order by total_supplied_usd DESC
   limit 10
````
- Things to note: All the data we have in the database ignored address that only supplied but does not borrow, this mean the actual top 10 asset lists and number might be slighlt differnet. As my understanding is that the root of our analysis here really pinned on debt and its also make data much smaller to work with. 

#### How daily volatility is calculated?

We use the **standard deviation of log returns** methodology, which is the industry standard for financial volatility estimation.

**Step-by-step process:**

1. **Fetch daily close prices** for 90 days from CoinGecko
   ```python
   python3 fetch_historical_prices.py
   ```

2. **Calculate log returns** for each day:
   ```python
   # Formula: rt = ln(Pt / Pt-1)
   df['returns'] = np.log(df['close_price'] / df['close_price'].shift(1))
   ```
   - Log returns are preferred over simple returns because they are:
     - Time-additive (can sum across periods)
     - More symmetric for price changes
     - Normally distributed (better for statistical analysis)

3. **Calculate daily volatility** using realized volatility formula:
   ```python
   # From fetch_historical_prices.py (lines 156-161)
   T = len(returns)
   mean_return = returns.mean()

   # Exact formula: σ_daily = √(1/(T-1) · Σ(rt - r̄)²)
   daily_volatility_manual = np.sqrt(((returns - mean_return) ** 2).sum() / (T - 1))
   daily_volatility = returns.std()  # pandas uses ddof=1, matches formula
   ```
   - `T` = number of observations (89 returns from 90 prices)
   - `rt` = log return at time t
   - `r̄` = mean of all log returns
   - `(T-1)` = degrees of freedom correction (Bessel's correction)

4. **Annualize the volatility** (optional, for easier interpretation):
   ```python
   # Formula: σ_annual = σ_daily · √365
   annualized_volatility = daily_volatility * np.sqrt(365)
   annualized_volatility_pct = annualized_volatility * 100
   ```

**Mathematical notation:**

```
σ_daily = √[ 1/(T-1) · Σ(rt - r̄)² ]

where:
  rt = ln(Pt / Pt-1)  [log return at time t]
  r̄ = (1/T) · Σ rt     [mean return]
  T = number of returns
```

**Why this method?**
- **Historical/Realized volatility**: Based on actual observed price movements
- **Standard deviation**: Measures dispersion of returns around the mean
- **Sample correction (T-1)**: Unbiased estimator for sample variance
- **Log returns**: Better statistical properties than arithmetic returns
- **90-day window**: Captures current market regime without dilution from distant past

**Results stored in database:**
```sql
SELECT symbol, daily_volatility, annualized_volatility_pct, days_analyzed
FROM asset_volatility
ORDER BY annualized_volatility_pct DESC;
```

Example output:
- **AAVE**: 93.45% annualized (highly volatile)
- **WETH**: 67.32% annualized (volatile)
- **USDC**: 0.15% annualized (stable)

**Covariance matrix:**

We also calculate the covariance matrix to capture correlation between assets:
```python
# From fetch_historical_prices.py (lines 219-222)
returns_df = pd.DataFrame(returns_dict)  # Each column = asset returns
cov_matrix = returns_df.cov()            # Σ = Cov(r)
corr_matrix = returns_df.corr()          # Normalized correlations
```

This matrix is essential for **portfolio-level risk calculations** in Monte Carlo simulation, as it captures how assets move together (e.g., WETH and weETH have 0.9997 correlation).

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
