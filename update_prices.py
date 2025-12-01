import psycopg2
import os
from dotenv import load_dotenv
from price_fetcher import PriceFetcher
from decimal import Decimal
from tqdm import tqdm
import pandas as pd

load_dotenv()

def update_prices_in_database():
    """Fetch current prices and update all positions in the database"""

    # Connect to database
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'aave_positions'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )

    cursor = conn.cursor()

    print("Fetching positions from database...")
    cursor.execute("SELECT DISTINCT symbol FROM positions")
    symbols = [row[0] for row in cursor.fetchall()]
    print(f"Found {len(symbols)} unique assets: {', '.join(symbols)}")

    # Fetch prices
    print("\nFetching prices from CoinGecko...")
    price_fetcher = PriceFetcher(api_key=os.getenv('COINGECKO_API_KEY'))
    prices = price_fetcher.get_prices_batch(symbols)

    print("\nPrices fetched:")
    for symbol, price in prices.items():
        print(f"  {symbol}: ${price:,.2f}")

    # Store prices in asset_prices table
    print("\nUpdating asset_prices table...")
    for symbol, price in prices.items():
        cursor.execute("""
            INSERT INTO asset_prices (asset_address, symbol, price_usd, last_updated)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (asset_address)
            DO UPDATE SET price_usd = EXCLUDED.price_usd, last_updated = CURRENT_TIMESTAMP
        """, (symbol.lower(), symbol, Decimal(str(price))))
    conn.commit()

    # Update positions with USD amounts
    print("\nUpdating position USD amounts...")
    cursor.execute("SELECT id, symbol, amount FROM positions")
    positions = cursor.fetchall()

    for position_id, symbol, amount in tqdm(positions, desc="Updating positions"):
        price = prices.get(symbol, 0.0)
        amount_usd = float(amount) * price

        cursor.execute("""
            UPDATE positions
            SET amount_usd = %s
            WHERE id = %s
        """, (Decimal(str(amount_usd)), position_id))

    conn.commit()

    # Recalculate user metrics
    print("\nRecalculating user metrics...")
    cursor.execute("SELECT DISTINCT user_address FROM positions")
    users = [row[0] for row in cursor.fetchall()]

    for user_address in tqdm(users, desc="Updating users"):
        # Get user positions
        cursor.execute("""
            SELECT symbol, side, amount, amount_usd, liquidation_threshold
            FROM positions
            WHERE user_address = %s
        """, (user_address,))

        user_positions = cursor.fetchall()

        total_debt_usd = 0.0
        total_collateral_usd = 0.0
        weighted_collateral_usd = 0.0

        for symbol, side, amount, amount_usd, liq_threshold in user_positions:
            if side == 'debt':
                total_debt_usd += float(amount_usd)
            elif side == 'collateral':
                total_collateral_usd += float(amount_usd)
                if liq_threshold:
                    weighted_collateral_usd += float(amount_usd) * float(liq_threshold)

        # Calculate health factor
        if total_debt_usd > 0:
            health_factor = weighted_collateral_usd / total_debt_usd
        else:
            health_factor = 999999.0  # Infinite

        # Update user
        cursor.execute("""
            INSERT INTO users (user_address, total_debt_usd, total_collateral_usd, health_factor, last_updated)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_address)
            DO UPDATE SET
                total_debt_usd = EXCLUDED.total_debt_usd,
                total_collateral_usd = EXCLUDED.total_collateral_usd,
                health_factor = EXCLUDED.health_factor,
                last_updated = CURRENT_TIMESTAMP
        """, (
            user_address,
            Decimal(str(total_debt_usd)),
            Decimal(str(total_collateral_usd)),
            Decimal(str(min(health_factor, 999999.0)))
        ))

    conn.commit()

    # Show summary
    print("\n" + "="*80)
    print("PRICE UPDATE COMPLETE!")
    print("="*80)

    cursor.execute("SELECT COUNT(*) FROM users WHERE total_debt_usd > 0")
    user_count = cursor.fetchone()[0]
    print(f"Total users with debt: {user_count}")

    cursor.execute("""
        SELECT user_address, total_debt_usd, total_collateral_usd, health_factor
        FROM users
        WHERE total_debt_usd > 0
        ORDER BY total_debt_usd DESC
        LIMIT 10
    """)

    print("\nTop 10 borrowers by debt:")
    print(f"{'User Address':<44} {'Debt (USD)':>15} {'Collateral (USD)':>18} {'Health Factor':>15}")
    print("-" * 100)

    for user_address, debt, collateral, hf in cursor.fetchall():
        print(f"{user_address:<44} ${debt:>14,.2f} ${collateral:>17,.2f} {hf:>15,.4f}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    update_prices_in_database()
