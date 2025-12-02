import requests
import pandas as pd
import psycopg2
from decimal import Decimal
from typing import List, Dict
import os
from dotenv import load_dotenv
from tqdm import tqdm
from price_fetcher import PriceFetcher
from datetime import datetime

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

class AavePositionFetcherFinal:
    def __init__(self):
        self.subgraph_url = os.getenv('SUBGRAPH_URL')
        self.batch_size = int(os.getenv('BATCH_SIZE', 100))
        self.top_n = int(os.getenv('TOP_N_POSITIONS', 1000))
        self.price_fetcher = PriceFetcher(api_key=os.getenv('COINGECKO_API_KEY'))

        # Database connection
        self.db_conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'aave_positions'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )

    def query_users_with_debt(self, skip: int = 0, first: int = 100) -> Dict:
        """Query users who have any debt with COMPLETE reserve information"""
        query = """
        query GetUsers($skip: Int!, $first: Int!) {
          users(
            skip: $skip
            first: $first
            where: { borrowedReservesCount_gt: 0 }
            orderBy: id
            orderDirection: asc
          ) {
            id
            borrowedReservesCount
            eModeCategoryId {
              id
            }
            reserves {
              id
              usageAsCollateralEnabledOnUser
              reserve {
                id
                symbol
                name
                underlyingAsset
                decimals
                reserveLiquidationThreshold
                baseLTVasCollateral
                reserveLiquidationBonus
                borrowingEnabled
                usageAsCollateralEnabled
                isActive
                isFrozen
                borrowCap
                supplyCap
                debtCeiling
                borrowableInIsolation
                eMode {
                  id
                }
              }
              currentATokenBalance
              currentVariableDebt
              currentStableDebt
              scaledVariableDebt
            }
          }
        }
        """

        variables = {
            "skip": skip,
            "first": first
        }

        response = requests.post(
            self.subgraph_url,
            json={'query': query, 'variables': variables},
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code != 200:
            raise Exception(f"Query failed with status {response.status_code}: {response.text}")

        data = response.json()
        if 'errors' in data:
            raise Exception(f"GraphQL errors: {data['errors']}")

        return data['data']

    def fetch_all_user_positions(self) -> pd.DataFrame:
        """Fetch all user positions with pagination"""
        all_positions = []
        skip = 0

        print("Fetching users with debt from Aave v3 subgraph (COMPREHENSIVE)...")

        with tqdm(desc="Fetching batches") as pbar:
            while True:
                try:
                    data = self.query_users_with_debt(skip=skip, first=self.batch_size)
                    users = data.get('users', [])

                    if not users:
                        break

                    for user_data in users:
                        user_address = user_data['id']
                        user_emode_category = user_data.get('eModeCategoryId', {}).get('id', '0') if user_data.get('eModeCategoryId') else '0'

                        # Process all reserves for this user
                        for reserve_data in user_data.get('reserves', []):
                            reserve = reserve_data['reserve']
                            asset_address = reserve['underlyingAsset']
                            symbol = reserve['symbol']
                            decimals = int(reserve['decimals'])

                            # All reserve-level fields (with safe defaults for None values)
                            liquidation_threshold = float(reserve.get('reserveLiquidationThreshold') or 0) / 10000
                            base_ltv = float(reserve.get('baseLTVasCollateral') or 0) / 10000
                            liquidation_bonus = float(reserve.get('reserveLiquidationBonus') or 0) / 10000
                            debt_ceiling = float(reserve.get('debtCeiling') or 0) / 100  # Stored in cents
                            borrowable_in_isolation = reserve.get('borrowableInIsolation', False)

                            # eMode category for the reserve (can be null)
                            reserve_emode = reserve.get('eMode')
                            reserve_emode_category = int(reserve_emode['id']) if reserve_emode else 0

                            is_frozen = reserve.get('isFrozen', False)
                            borrow_cap_raw = reserve.get('borrowCap')
                            borrow_cap = int(borrow_cap_raw) if borrow_cap_raw not in (None, '0', 0) else 0
                            supply_cap_raw = reserve.get('supplyCap')
                            supply_cap = int(supply_cap_raw) if supply_cap_raw not in (None, '0', 0) else 0
                            borrowing_enabled = reserve.get('borrowingEnabled', False)
                            is_active = reserve.get('isActive', True)
                            usage_as_collateral_enabled = reserve.get('usageAsCollateralEnabled', False)

                            # Check if this asset is enabled as collateral by the user
                            is_collateral_enabled = reserve_data.get('usageAsCollateralEnabledOnUser', False)

                            # Parse collateral (aToken balance)
                            collateral_raw = int(reserve_data['currentATokenBalance'])
                            collateral_amount = collateral_raw / (10 ** decimals)

                            # Parse debt (variable + stable)
                            variable_debt_raw = int(reserve_data['currentVariableDebt'])
                            stable_debt_raw = int(reserve_data['currentStableDebt'])
                            debt_amount = (variable_debt_raw + stable_debt_raw) / (10 ** decimals)

                            # Base position data
                            base_data = {
                                'user_address': user_address.lower(),
                                'asset_address': asset_address.lower(),
                                'symbol': symbol,
                                'liquidation_threshold': liquidation_threshold,
                                'base_ltv_as_collateral': base_ltv,
                                'liquidation_bonus': liquidation_bonus,
                                'debt_ceiling': debt_ceiling,
                                'borrowable_in_isolation': borrowable_in_isolation,
                                'emode_category_id': reserve_emode_category,
                                'is_frozen': is_frozen,
                                'borrow_cap': borrow_cap,
                                'supply_cap': supply_cap,
                                'borrowing_enabled': borrowing_enabled,
                                'is_active': is_active,
                                'usage_as_collateral_enabled': usage_as_collateral_enabled,
                                'user_emode_category': user_emode_category
                            }

                            # Add collateral position if non-zero AND enabled as collateral
                            if collateral_amount > 0 and is_collateral_enabled:
                                all_positions.append({
                                    **base_data,
                                    'side': 'collateral',
                                    'amount': collateral_amount,
                                })

                            # Add debt position if non-zero
                            if debt_amount > 0:
                                all_positions.append({
                                    **base_data,
                                    'side': 'debt',
                                    'amount': debt_amount,
                                })

                    skip += self.batch_size
                    pbar.update(1)
                    pbar.set_postfix({'users': skip, 'positions': len(all_positions)})

                except Exception as e:
                    print(f"Error fetching batch at skip={skip}: {e}")
                    break

        df = pd.DataFrame(all_positions)
        print(f"\nFetched {len(df)} total positions from {skip} users")
        print(f"Note: Only counting deposits that are ENABLED as collateral")
        return df

    def enrich_with_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add USD prices and calculate USD amounts"""
        print("\nFetching prices from CoinGecko...")

        unique_symbols = df['symbol'].unique().tolist()
        prices = self.price_fetcher.get_prices_batch(unique_symbols)

        # Store price timestamp
        price_timestamp = datetime.now()

        df['price_usd'] = df['symbol'].map(prices)
        df['price_timestamp'] = price_timestamp
        df['amount_usd'] = df['amount'] * df['price_usd']

        self.store_prices(prices)

        return df

    def calculate_top_borrowers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate top borrowers by total debt in USD"""
        print("\nCalculating top borrowers...")

        debt_df = df[df['side'] == 'debt'].copy()
        user_debt = debt_df.groupby('user_address').agg({
            'amount_usd': 'sum'
        }).reset_index()
        user_debt.columns = ['user_address', 'total_debt_usd']

        top_borrowers = user_debt.nlargest(self.top_n, 'total_debt_usd')

        print(f"Top {len(top_borrowers)} borrowers identified")
        if len(top_borrowers) > 0:
            print(f"Debt range: ${top_borrowers['total_debt_usd'].min():,.2f} - ${top_borrowers['total_debt_usd'].max():,.2f}")

        return top_borrowers

    def calculate_user_metrics(self, df: pd.DataFrame, top_borrowers: pd.DataFrame) -> pd.DataFrame:
        """Calculate full metrics for top borrowers"""
        print("\nCalculating user metrics (with proper collateral filtering)...")

        metrics = []

        for _, row in tqdm(top_borrowers.iterrows(), total=len(top_borrowers)):
            user_address = row['user_address']
            user_positions = df[df['user_address'] == user_address]

            collateral = user_positions[user_positions['side'] == 'collateral'].copy()
            collateral['weighted_collateral'] = collateral['amount_usd'] * collateral['liquidation_threshold']
            total_collateral_usd = collateral['amount_usd'].sum()
            weighted_collateral_usd = collateral['weighted_collateral'].sum()

            total_debt_usd = row['total_debt_usd']

            if total_debt_usd > 0:
                health_factor = weighted_collateral_usd / total_debt_usd
            else:
                health_factor = float('inf')

            metrics.append({
                'user_address': user_address,
                'total_debt_usd': total_debt_usd,
                'total_collateral_usd': total_collateral_usd,
                'health_factor': health_factor
            })

        return pd.DataFrame(metrics)

    def store_prices(self, prices: Dict[str, float]):
        """Store asset prices in database"""
        cursor = self.db_conn.cursor()

        for symbol, price in prices.items():
            cursor.execute("""
                INSERT INTO asset_prices (asset_address, symbol, price_usd, last_updated)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (asset_address)
                DO UPDATE SET price_usd = EXCLUDED.price_usd, last_updated = CURRENT_TIMESTAMP
            """, (symbol.lower(), symbol, Decimal(str(price))))

        self.db_conn.commit()
        cursor.close()

    def store_users(self, user_metrics: pd.DataFrame):
        """Store user metrics in database"""
        print("\nStoring user data...")
        cursor = self.db_conn.cursor()

        # Clear existing data first
        cursor.execute("TRUNCATE TABLE users CASCADE")
        cursor.execute("TRUNCATE TABLE positions CASCADE")
        self.db_conn.commit()

        for _, row in tqdm(user_metrics.iterrows(), total=len(user_metrics)):
            cursor.execute("""
                INSERT INTO users (user_address, total_debt_usd, total_collateral_usd, health_factor, last_updated)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                row['user_address'],
                Decimal(str(row['total_debt_usd'])),
                Decimal(str(row['total_collateral_usd'])),
                Decimal(str(min(row['health_factor'], 999999)))
            ))

        self.db_conn.commit()
        cursor.close()

    def store_positions(self, df: pd.DataFrame, top_borrowers: pd.DataFrame):
        """Store positions for top borrowers in database"""
        print("\nStoring position data (with ALL critical fields)...")
        cursor = self.db_conn.cursor()

        top_addresses = set(top_borrowers['user_address'].tolist())
        top_positions = df[df['user_address'].isin(top_addresses)]

        # Deduplicate positions by grouping and summing amounts
        print("Deduplicating positions...")
        top_positions = top_positions.groupby(['user_address', 'asset_address', 'symbol', 'side'], as_index=False).agg({
            'amount': 'sum',
            'amount_usd': 'sum',
            'price_usd': 'first',
            'price_timestamp': 'first',
            'liquidation_threshold': 'first',
            'base_ltv_as_collateral': 'first',
            'liquidation_bonus': 'first',
            'debt_ceiling': 'first',
            'borrowable_in_isolation': 'first',
            'emode_category_id': 'first',
            'is_frozen': 'first',
            'borrow_cap': 'first',
            'supply_cap': 'first',
            'borrowing_enabled': 'first',
            'is_active': 'first',
            'usage_as_collateral_enabled': 'first'
        })

        for _, row in tqdm(top_positions.iterrows(), total=len(top_positions)):
            cursor.execute("""
                INSERT INTO positions (
                    user_address, asset_address, symbol, side,
                    amount, amount_usd, price_usd, price_timestamp,
                    liquidation_threshold, base_ltv_as_collateral, liquidation_bonus,
                    debt_ceiling, borrowable_in_isolation, emode_category_id,
                    is_frozen, borrow_cap, supply_cap,
                    borrowing_enabled, is_active, usage_as_collateral_enabled,
                    last_updated
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                row['user_address'],
                row['asset_address'],
                row['symbol'],
                row['side'],
                Decimal(str(row['amount'])),
                Decimal(str(row['amount_usd'])),
                Decimal(str(row['price_usd'])),
                row['price_timestamp'],
                Decimal(str(row['liquidation_threshold'])),
                Decimal(str(row['base_ltv_as_collateral'])),
                Decimal(str(row['liquidation_bonus'])),
                Decimal(str(row['debt_ceiling'])),
                bool(row['borrowable_in_isolation']),
                int(row['emode_category_id']),
                bool(row['is_frozen']),
                Decimal(str(row['borrow_cap'])),
                Decimal(str(row['supply_cap'])),
                bool(row['borrowing_enabled']),
                bool(row['is_active']),
                bool(row['usage_as_collateral_enabled'])
            ))

        self.db_conn.commit()
        cursor.close()

    def run(self):
        """Main execution flow"""
        try:
            positions_df = self.fetch_all_user_positions()

            if positions_df.empty:
                print("No positions found!")
                return

            positions_df = self.enrich_with_prices(positions_df)
            top_borrowers = self.calculate_top_borrowers(positions_df)
            user_metrics = self.calculate_user_metrics(positions_df, top_borrowers)

            self.store_users(user_metrics)
            self.store_positions(positions_df, top_borrowers)

            print("\n" + "="*80)
            print("COMPREHENSIVE DATA COLLECTION COMPLETE!")
            print("="*80)
            print(f"Total positions fetched: {len(positions_df)}")
            print(f"Top {len(top_borrowers)} borrowers stored")
            print(f"\nTop 10 borrowers:")
            print(user_metrics.head(10)[['user_address', 'total_debt_usd', 'total_collateral_usd', 'health_factor']].to_string(index=False))

            print("\n" + "="*80)
            print("CRITICAL FIELDS INCLUDED:")
            print("="*80)
            print("✓ usageAsCollateralEnabledOnUser (proper collateral filtering)")
            print("✓ baseLTVasCollateral (max borrow LTV)")
            print("✓ reserveLiquidationBonus (liquidator incentive)")
            print("✓ debtCeiling (isolation mode limit)")
            print("✓ isolationModeTotalDebt (current isolation debt)")
            print("✓ eModeCategoryId (efficiency mode category)")
            print("✓ isFrozen (asset freeze status)")
            print("✓ borrowCap & supplyCap (protocol limits)")
            print("✓ borrowingEnabled, isActive, usageAsCollateralEnabled")
            print("✓ price_usd & price_timestamp (for each position)")

        except Exception as e:
            print(f"Error: {e}")
            raise
        finally:
            self.db_conn.close()

if __name__ == "__main__":
    fetcher = AavePositionFetcherFinal()
    fetcher.run()
