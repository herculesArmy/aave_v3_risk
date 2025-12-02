import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

def create_database():
    """Create the database if it doesn't exist"""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    db_name = os.getenv('DB_NAME', 'aave_positions')

    # Check if database exists
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(f'CREATE DATABASE {db_name}')
        print(f"Database '{db_name}' created successfully")
    else:
        print(f"Database '{db_name}' already exists")

    cursor.close()
    conn.close()

def create_tables():
    """Create the necessary tables for storing position data"""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'aave_positions'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_address VARCHAR(42) PRIMARY KEY,
            total_debt_usd DECIMAL(20, 2),
            total_collateral_usd DECIMAL(20, 2),
            health_factor DECIMAL(10, 4),
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create positions table with comprehensive Aave v3 fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id SERIAL PRIMARY KEY,
            user_address VARCHAR(42) REFERENCES users(user_address),
            asset_address VARCHAR(42),
            symbol VARCHAR(20),
            side VARCHAR(20),
            amount DECIMAL(30, 18),
            amount_usd DECIMAL(20, 2),
            price_usd DECIMAL(20, 8),
            price_timestamp TIMESTAMP,
            liquidation_threshold DECIMAL(5, 4),
            base_ltv_as_collateral DECIMAL(5, 4),
            liquidation_bonus DECIMAL(5, 4),
            debt_ceiling DECIMAL(30, 2),
            borrowable_in_isolation BOOLEAN,
            emode_category_id INTEGER,
            is_frozen BOOLEAN,
            borrow_cap DECIMAL(30, 18),
            supply_cap DECIMAL(30, 18),
            borrowing_enabled BOOLEAN,
            is_active BOOLEAN,
            usage_as_collateral_enabled BOOLEAN,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_address, asset_address, side)
        )
    """)

    # Create asset_prices table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asset_prices (
            asset_address VARCHAR(42) PRIMARY KEY,
            symbol VARCHAR(20),
            price_usd DECIMAL(20, 8),
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create historical_prices table for volatility analysis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_prices (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            close_price DECIMAL(20, 8) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        )
    """)

    # Create asset_volatility table for storing calculated metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asset_volatility (
            symbol VARCHAR(20) PRIMARY KEY,
            current_price DECIMAL(20, 8),
            min_price DECIMAL(20, 8),
            max_price DECIMAL(20, 8),
            price_range_pct DECIMAL(10, 4),
            daily_volatility DECIMAL(10, 8),
            annualized_volatility DECIMAL(10, 8),
            annualized_volatility_pct DECIMAL(10, 4),
            days_analyzed INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create simulation_runs table for tracking MC simulations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulation_runs (
            run_id SERIAL PRIMARY KEY,
            n_scenarios INTEGER NOT NULL,
            random_seed INTEGER,
            run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            var_95 DECIMAL(20, 2),
            var_99 DECIMAL(20, 2),
            var_99_9 DECIMAL(20, 2),
            mean_bad_debt DECIMAL(20, 2),
            std_bad_debt DECIMAL(20, 2)
        )
    """)

    # Create simulated_prices table for storing price trajectories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulated_prices (
            id SERIAL PRIMARY KEY,
            run_id INTEGER REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
            scenario_id INTEGER NOT NULL,
            asset_symbol VARCHAR(20) NOT NULL,
            current_price DECIMAL(20, 8),
            simulated_price DECIMAL(20, 8),
            return_pct DECIMAL(10, 6),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create scenario_results table for storing bad debt per scenario
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scenario_results (
            id SERIAL PRIMARY KEY,
            run_id INTEGER REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
            scenario_id INTEGER NOT NULL,
            total_bad_debt DECIMAL(20, 2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(run_id, scenario_id)
        )
    """)

    # Create indexes for better query performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_debt
        ON users(total_debt_usd DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_user
        ON positions(user_address)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_side
        ON positions(side)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_historical_prices_symbol
        ON historical_prices(symbol)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_historical_prices_date
        ON historical_prices(date DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_simulated_prices_scenario
        ON simulated_prices(run_id, scenario_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_simulated_prices_asset
        ON simulated_prices(asset_symbol)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scenario_results_run
        ON scenario_results(run_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scenario_results_bad_debt
        ON scenario_results(total_bad_debt DESC)
    """)

    conn.commit()
    cursor.close()
    conn.close()

    print("Tables created successfully with indexes")

if __name__ == "__main__":
    print("Setting up database...")
    create_database()
    create_tables()
    print("Database setup complete!")
