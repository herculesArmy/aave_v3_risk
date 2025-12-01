import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class PositionAnalyzer:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'aave_positions'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )

    def get_top_borrowers(self, limit: int = 100) -> pd.DataFrame:
        """Get top borrowers by total debt"""
        query = """
            SELECT
                user_address,
                total_debt_usd,
                total_collateral_usd,
                health_factor,
                last_updated
            FROM users
            ORDER BY total_debt_usd DESC
            LIMIT %s
        """
        return pd.read_sql_query(query, self.conn, params=(limit,))

    def get_user_positions(self, user_address: str) -> pd.DataFrame:
        """Get all positions for a specific user"""
        query = """
            SELECT
                user_address,
                asset_address,
                symbol,
                side,
                amount,
                amount_usd,
                liquidation_threshold,
                last_updated
            FROM positions
            WHERE user_address = %s
            ORDER BY amount_usd DESC
        """
        return pd.read_sql_query(query, self.conn, params=(user_address.lower(),))

    def get_risky_positions(self, health_factor_threshold: float = 1.5) -> pd.DataFrame:
        """Get users with health factor below threshold (risky positions)"""
        query = """
            SELECT
                user_address,
                total_debt_usd,
                total_collateral_usd,
                health_factor,
                last_updated
            FROM users
            WHERE health_factor < %s AND health_factor > 0
            ORDER BY health_factor ASC
        """
        return pd.read_sql_query(query, self.conn, params=(health_factor_threshold,))

    def get_asset_exposure(self) -> pd.DataFrame:
        """Get total exposure by asset across all positions"""
        query = """
            SELECT
                symbol,
                side,
                COUNT(DISTINCT user_address) as num_users,
                SUM(amount) as total_amount,
                SUM(amount_usd) as total_amount_usd,
                AVG(amount_usd) as avg_amount_usd,
                MAX(amount_usd) as max_amount_usd
            FROM positions
            GROUP BY symbol, side
            ORDER BY total_amount_usd DESC
        """
        return pd.read_sql_query(query, self.conn)

    def get_user_summary(self, user_address: str) -> dict:
        """Get detailed summary for a specific user"""
        # Get user info
        user_query = """
            SELECT * FROM users WHERE user_address = %s
        """
        user_df = pd.read_sql_query(user_query, self.conn, params=(user_address.lower(),))

        if user_df.empty:
            return None

        # Get positions
        positions = self.get_user_positions(user_address)

        collateral = positions[positions['side'] == 'collateral']
        debt = positions[positions['side'] == 'debt']

        return {
            'user_address': user_address,
            'total_debt_usd': float(user_df['total_debt_usd'].iloc[0]),
            'total_collateral_usd': float(user_df['total_collateral_usd'].iloc[0]),
            'health_factor': float(user_df['health_factor'].iloc[0]),
            'num_collateral_assets': len(collateral),
            'num_debt_assets': len(debt),
            'collateral_breakdown': collateral[['symbol', 'amount', 'amount_usd']].to_dict('records'),
            'debt_breakdown': debt[['symbol', 'amount', 'amount_usd']].to_dict('records')
        }

    def export_to_csv(self, filename: str = 'top_1000_borrowers.csv'):
        """Export top borrowers with their positions to CSV"""
        query = """
            SELECT
                u.user_address,
                u.total_debt_usd,
                u.total_collateral_usd,
                u.health_factor,
                p.asset_address,
                p.symbol,
                p.side,
                p.amount,
                p.amount_usd,
                p.liquidation_threshold
            FROM users u
            LEFT JOIN positions p ON u.user_address = p.user_address
            ORDER BY u.total_debt_usd DESC, p.amount_usd DESC
        """
        df = pd.read_sql_query(query, self.conn)
        df.to_csv(filename, index=False)
        print(f"Data exported to {filename}")
        return df

    def close(self):
        self.conn.close()


def main():
    analyzer = PositionAnalyzer()

    try:
        print("=" * 80)
        print("AAVE V3 POSITION ANALYSIS")
        print("=" * 80)

        # Top 10 borrowers
        print("\nTop 10 Borrowers by Total Debt:")
        print("-" * 80)
        top_10 = analyzer.get_top_borrowers(10)
        print(top_10.to_string(index=False))

        # Risky positions
        print("\n\nRisky Positions (Health Factor < 1.5):")
        print("-" * 80)
        risky = analyzer.get_risky_positions(1.5)
        if not risky.empty:
            print(f"Found {len(risky)} risky positions")
            print(risky.head(10).to_string(index=False))
        else:
            print("No risky positions found")

        # Asset exposure
        print("\n\nTop Asset Exposure:")
        print("-" * 80)
        exposure = analyzer.get_asset_exposure()
        print(exposure.head(20).to_string(index=False))

        # Example user detail
        if not top_10.empty:
            example_user = top_10.iloc[0]['user_address']
            print(f"\n\nExample User Detail ({example_user}):")
            print("-" * 80)
            summary = analyzer.get_user_summary(example_user)
            if summary:
                print(f"Total Debt: ${summary['total_debt_usd']:,.2f}")
                print(f"Total Collateral: ${summary['total_collateral_usd']:,.2f}")
                print(f"Health Factor: {summary['health_factor']:.4f}")
                print(f"\nCollateral Assets ({summary['num_collateral_assets']}):")
                for asset in summary['collateral_breakdown']:
                    print(f"  - {asset['symbol']}: {asset['amount']:.4f} (${asset['amount_usd']:,.2f})")
                print(f"\nDebt Assets ({summary['num_debt_assets']}):")
                for asset in summary['debt_breakdown']:
                    print(f"  - {asset['symbol']}: {asset['amount']:.4f} (${asset['amount_usd']:,.2f})")

        # Export option
        print("\n\n" + "=" * 80)
        export = input("Export all data to CSV? (y/n): ")
        if export.lower() == 'y':
            analyzer.export_to_csv()

    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
