import requests
import pandas as pd
import numpy as np
import psycopg2
from decimal import Decimal
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

class HistoricalPriceFetcher:
    def __init__(self):
        self.api_key = os.getenv('COINGECKO_API_KEY')
        self.base_url = "https://api.coingecko.com/api/v3"

        # Mapping of Aave symbols to CoinGecko IDs
        # Comprehensive list including LSTs, LRTs, and other DeFi assets
        self.asset_mapping = {
            # Major ETH assets
            'WETH': 'weth',
            'weETH': 'wrapped-eeth',
            'wstETH': 'wrapped-steth',
            # Restaked/Liquid Restaking Tokens (LRTs)
            'rsETH': 'kelp-dao-restaked-eth',
            'ezETH': 'renzo-restaked-eth',
            'osETH': 'stakewise-v3-oseth',
            'ETHx': 'stader-ethx',
            'tETH': 'treehouse-eth',
            # BTC assets
            'WBTC': 'wrapped-bitcoin',
            'cbBTC': 'coinbase-wrapped-btc',
            'LBTC': 'lombard-staked-btc',
            'FBTC': 'ignition-fbtc',
            'eBTC': 'ether-fi-staked-btc',
            # Stablecoins
            'USDC': 'usd-coin',
            'USDT': 'tether',
            'PYUSD': 'paypal-usd',
            'USDe': 'ethena-usde',
            'sUSDe': 'ethena-staked-usde',
            'crvUSD': 'crvusd',
            'sDAI': 'savings-dai',
            # DeFi tokens
            'AAVE': 'aave',
            'FXS': 'frax-share',
            'KNC': 'kyber-network-crystal',
            'XAUt': 'tether-gold',
        }

        # Database connection
        self.db_conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'aave_positions'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )

    def fetch_historical_data(self, symbol: str, coingecko_id: str, days: int = 90):
        """Fetch historical daily price data from CoinGecko and store in database"""

        print(f"Fetching {days} days of data for {symbol}...")

        # Rate limiting
        time.sleep(1.2)

        url = f"{self.base_url}/coins/{coingecko_id}/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': days,
            'interval': 'daily'
        }

        if self.api_key:
            params['x_cg_demo_api_key'] = self.api_key

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Extract prices
            prices = data['prices']

            # Convert to DataFrame
            df = pd.DataFrame(prices, columns=['timestamp', 'price'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['date'] = df['timestamp'].dt.date

            # Group by date and take the last price of each day (close price)
            df = df.groupby('date').agg({'price': 'last'}).reset_index()
            df.columns = ['date', 'close_price']
            df['symbol'] = symbol

            # Store in database
            self.store_historical_prices(df)

            print(f"✓ {symbol}: {len(df)} days of data stored in database")

        except Exception as e:
            print(f"✗ {symbol}: Error - {e}")

    def store_historical_prices(self, df: pd.DataFrame):
        """Store historical prices in database"""
        cursor = self.db_conn.cursor()

        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO historical_prices (symbol, date, close_price)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol, date)
                DO UPDATE SET close_price = EXCLUDED.close_price
            """, (row['symbol'], row['date'], Decimal(str(row['close_price']))))

        self.db_conn.commit()
        cursor.close()

    def fetch_all_assets(self, days: int = 90):
        """Fetch historical data for all assets"""

        print(f"\nFetching historical data for {len(self.asset_mapping)} assets...")

        for symbol, coingecko_id in self.asset_mapping.items():
            self.fetch_historical_data(symbol, coingecko_id, days)

    def calculate_volatility_from_db(self) -> pd.DataFrame:
        """Calculate volatility metrics using data from database"""

        print(f"\n{'='*80}")
        print("VOLATILITY CALCULATION FROM DATABASE")
        print(f"{'='*80}")
        print(f"Method: Annualized Standard Deviation of Daily Log Returns")
        print(f"{'='*80}\n")

        cursor = self.db_conn.cursor()

        # Get all unique symbols
        cursor.execute("SELECT DISTINCT symbol FROM historical_prices ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]

        volatility_metrics = []

        for symbol in symbols:
            # Fetch price data for this symbol
            cursor.execute("""
                SELECT date, close_price
                FROM historical_prices
                WHERE symbol = %s
                ORDER BY date ASC
            """, (symbol,))

            rows = cursor.fetchall()

            if len(rows) < 2:
                continue

            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=['date', 'close_price'])
            df['close_price'] = df['close_price'].astype(float)

            # Calculate daily returns (log returns)
            df['returns'] = np.log(df['close_price'] / df['close_price'].shift(1))

            # Remove NaN
            returns = df['returns'].dropna()

            if len(returns) < 2:
                continue

            # Calculate volatility metrics
            # Using the exact formula from the specification:
            # σ_daily = √(1/(T-1) · Σ(rt - r̄)²)
            # Note: pandas .std() uses ddof=1 by default, which is equivalent to 1/(T-1)
            T = len(returns)
            mean_return = returns.mean()

            # Verify: Manual calculation matches pandas .std()
            daily_volatility_manual = np.sqrt(((returns - mean_return) ** 2).sum() / (T - 1))
            daily_volatility = returns.std()  # Should match manual calculation

            # Annualize: σ_annual = σ_daily · √365
            annualized_volatility = daily_volatility * np.sqrt(365)

            # Price metrics
            min_price = df['close_price'].min()
            max_price = df['close_price'].max()
            current_price = df['close_price'].iloc[-1]

            volatility_metrics.append({
                'symbol': symbol,
                'current_price': current_price,
                'min_price': min_price,
                'max_price': max_price,
                'price_range_pct': ((max_price - min_price) / min_price) * 100,
                'daily_volatility': daily_volatility,
                'annualized_volatility': annualized_volatility,
                'annualized_volatility_pct': annualized_volatility * 100,
                'days_analyzed': len(returns)
            })

        cursor.close()
        return pd.DataFrame(volatility_metrics)

    def calculate_covariance_matrix(self):
        """Calculate and store covariance matrix of returns"""

        print(f"\n{'='*80}")
        print("COVARIANCE MATRIX CALCULATION")
        print(f"{'='*80}\n")

        cursor = self.db_conn.cursor()

        # Get all symbols
        cursor.execute("SELECT DISTINCT symbol FROM historical_prices ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]

        # Fetch returns for all assets aligned by date
        returns_dict = {}

        for symbol in symbols:
            cursor.execute("""
                SELECT date, close_price
                FROM historical_prices
                WHERE symbol = %s
                ORDER BY date ASC
            """, (symbol,))

            rows = cursor.fetchall()
            df = pd.DataFrame(rows, columns=['date', 'close_price'])
            df['close_price'] = df['close_price'].astype(float)
            df['returns'] = np.log(df['close_price'] / df['close_price'].shift(1))
            df = df.dropna()

            returns_dict[symbol] = df.set_index('date')['returns']

        # Create returns DataFrame (aligned by date)
        returns_df = pd.DataFrame(returns_dict)

        # Calculate covariance matrix: Σ = Cov(r)
        cov_matrix = returns_df.cov()

        # Calculate correlation matrix as well (useful for analysis)
        corr_matrix = returns_df.corr()

        print(f"Covariance Matrix ({len(symbols)}x{len(symbols)}):")
        print(cov_matrix)
        print(f"\nCorrelation Matrix:")
        print(corr_matrix)

        # Store covariance matrix in database
        self.store_covariance_matrix(cov_matrix, corr_matrix)

        cursor.close()
        return cov_matrix, corr_matrix

    def store_covariance_matrix(self, cov_matrix: pd.DataFrame, corr_matrix: pd.DataFrame):
        """Store covariance and correlation matrices in database"""

        cursor = self.db_conn.cursor()

        # Create table for covariance matrix if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asset_covariance (
                asset1 VARCHAR(20),
                asset2 VARCHAR(20),
                covariance DECIMAL(15, 10),
                correlation DECIMAL(8, 6),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (asset1, asset2)
            )
        """)

        # Clear existing data
        cursor.execute("TRUNCATE TABLE asset_covariance")

        # Insert covariance and correlation data
        for asset1 in cov_matrix.index:
            for asset2 in cov_matrix.columns:
                cov_value = cov_matrix.loc[asset1, asset2]
                corr_value = corr_matrix.loc[asset1, asset2]

                cursor.execute("""
                    INSERT INTO asset_covariance (asset1, asset2, covariance, correlation)
                    VALUES (%s, %s, %s, %s)
                """, (asset1, asset2, Decimal(str(cov_value)), Decimal(str(corr_value))))

        self.db_conn.commit()
        cursor.close()
        print("\n✓ Covariance and correlation matrices stored in database")

    def store_volatility_metrics(self, volatility_df: pd.DataFrame):
        """Store volatility metrics in database"""

        print("\nStoring volatility metrics in database...")
        cursor = self.db_conn.cursor()

        # Clear existing data
        cursor.execute("TRUNCATE TABLE asset_volatility")

        for _, row in volatility_df.iterrows():
            cursor.execute("""
                INSERT INTO asset_volatility (
                    symbol, current_price, min_price, max_price, price_range_pct,
                    daily_volatility, annualized_volatility, annualized_volatility_pct,
                    days_analyzed, last_updated
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                row['symbol'],
                Decimal(str(row['current_price'])),
                Decimal(str(row['min_price'])),
                Decimal(str(row['max_price'])),
                Decimal(str(row['price_range_pct'])),
                Decimal(str(row['daily_volatility'])),
                Decimal(str(row['annualized_volatility'])),
                Decimal(str(row['annualized_volatility_pct'])),
                int(row['days_analyzed'])
            ))

        self.db_conn.commit()
        cursor.close()
        print("✓ Volatility metrics stored in database")

    def display_results(self, volatility_df: pd.DataFrame):
        """Display volatility results"""

        print(f"\n{'='*80}")
        print("VOLATILITY METRICS (Sorted by Annualized Volatility)")
        print(f"{'='*80}\n")

        display_df = volatility_df.sort_values('annualized_volatility', ascending=False)

        print(display_df[[
            'symbol',
            'current_price',
            'annualized_volatility_pct',
            'price_range_pct',
            'days_analyzed'
        ]].to_string(index=False))

        print(f"\n{'='*80}")
        print("INTERPRETATION")
        print(f"{'='*80}")
        print("• Annualized Volatility: Standard deviation of returns scaled to 1 year")
        print("• Higher % = More volatile/risky asset")
        print("• Stablecoins (USDC, USDT) should have very low volatility (<1%)")
        print("• Crypto assets typically range from 30-100%+ volatility")
        print(f"{'='*80}\n")

    def run(self, days: int = 90):
        """Main execution"""

        print(f"{'='*80}")
        print("HISTORICAL PRICE DATA FETCHER (DATABASE STORAGE)")
        print(f"{'='*80}")
        print(f"Assets to fetch: {len(self.asset_mapping)}")
        print(f"Time period: {days} days")
        print(f"Data source: CoinGecko API")
        print(f"Storage: PostgreSQL Database")
        print(f"{'='*80}\n")

        try:
            # Fetch and store historical data
            self.fetch_all_assets(days)

            # Calculate volatility from database
            volatility_df = self.calculate_volatility_from_db()

            if volatility_df.empty:
                print("\n✗ No volatility data calculated!")
                return

            # Store volatility metrics
            self.store_volatility_metrics(volatility_df)

            # Calculate and store covariance matrix
            cov_matrix, corr_matrix = self.calculate_covariance_matrix()

            # Display results
            self.display_results(volatility_df)

            print(f"\n{'='*80}")
            print("DATA COLLECTION COMPLETE!")
            print(f"{'='*80}")
            print(f"✓ Historical prices stored in: historical_prices table")
            print(f"✓ Volatility metrics stored in: asset_volatility table")
            print(f"✓ Covariance matrix stored in: asset_covariance table")
            print(f"✓ Total assets: {len(volatility_df)}")
            print(f"✓ Period: Last {days} days")
            print(f"✓ Methodology: Log returns → Daily volatility → Annualized (×√365)")
            print(f"✓ Covariance: Σ = Cov(r) for all asset pairs")
            print(f"{'='*80}\n")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            raise
        finally:
            self.db_conn.close()

if __name__ == "__main__":
    fetcher = HistoricalPriceFetcher()
    fetcher.run(days=90)
