import numpy as np
import pandas as pd
import psycopg2
from scipy import stats
from decimal import Decimal
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
VIZ_DIR = os.path.join(PROJECT_ROOT, 'visualizations')

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

class AaveVaRSimulation:
    """
    Monte Carlo simulation engine for Aave V3 protocol Value at Risk (VaR) analysis.

    Methodology:
    - Simulates correlated price shocks using multivariate normal distribution
    - Recalculates user-level Health Factors under each scenario
    - Computes bad debt when recoverable collateral < total debt
    - Aggregates protocol-level losses across all scenarios
    - Calculates VaR at different confidence levels
    """

    def __init__(self, n_simulations: int = 10000, random_seed: int = 42):
        """
        Initialize simulation engine.

        Args:
            n_simulations: Number of Monte Carlo scenarios to generate
            random_seed: Random seed for reproducibility
        """
        self.n_simulations = n_simulations
        self.random_seed = random_seed
        np.random.seed(random_seed)

        # Database connection
        self.db_conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'aave_positions'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )

        # Data containers
        self.users = []
        self.asset_prices = {}
        self.covariance_matrix = None
        self.asset_symbols = []
        self.simulation_results = None
        self.emode_categories = {}  # E-Mode ID -> {label, ltv, lt, bonus}

    def load_data(self):
        """Load all required data from database."""
        print(f"\n{'='*80}")
        print("LOADING DATA FROM DATABASE")
        print(f"{'='*80}\n")

        self._load_emode_categories()
        self._load_users_and_positions()
        self._load_current_prices()
        self._load_covariance_matrix()

        print(f"✓ Data loading complete")
        print(f"  - Users: {len(self.users)}")
        print(f"  - Assets: {len(self.asset_symbols)}")
        print(f"  - E-Mode categories: {len(self.emode_categories)}")
        print(f"  - Covariance matrix: {len(self.asset_symbols)}×{len(self.asset_symbols)}")

    def _load_emode_categories(self):
        """Load E-Mode categories from database."""
        cursor = self.db_conn.cursor()

        cursor.execute("""
            SELECT id, label, ltv, liquidation_threshold, liquidation_bonus
            FROM emode_categories
        """)

        for row in cursor.fetchall():
            emode_id, label, ltv, lt, bonus = row
            self.emode_categories[emode_id] = {
                'label': label,
                'ltv': float(ltv) if ltv else 0.0,
                'lt': float(lt) if lt else 0.0,
                'bonus': float(bonus) if bonus else 0.0
            }

        cursor.close()
        print(f"✓ Loaded {len(self.emode_categories)} E-Mode categories")

    def _load_users_and_positions(self):
        """Load user positions from database."""
        cursor = self.db_conn.cursor()

        # Get top 1000 borrowers with their E-Mode category
        cursor.execute("""
            SELECT user_address, total_debt_usd, total_collateral_usd, health_factor, user_emode_category
            FROM users
            WHERE total_debt_usd > 0
            ORDER BY total_debt_usd DESC
            LIMIT 1000
        """)

        top_users = cursor.fetchall()
        print(f"Loading positions for {len(top_users)} users...")

        for user_address, total_debt, total_collateral, health_factor, user_emode in top_users:
            # Get all positions for this user
            cursor.execute("""
                SELECT
                    symbol, side, amount, amount_usd,
                    liquidation_threshold,
                    usage_as_collateral_enabled,
                    borrowable_in_isolation,
                    emode_category_id
                FROM positions
                WHERE user_address = %s
            """, (user_address,))

            positions = cursor.fetchall()

            collateral_positions = []
            debt_positions = []

            for symbol, side, amount, amount_usd, lt, usage_enabled, borrowable_iso, emode in positions:
                if side == 'collateral':
                    collateral_positions.append({
                        'symbol': symbol,
                        'amount': float(amount),
                        'amount_usd': float(amount_usd),
                        'liquidation_threshold': float(lt) if lt else 0.0,
                        'usage_as_collateral_enabled': usage_enabled,
                        'borrowable_in_isolation': borrowable_iso
                    })
                elif side == 'debt':
                    debt_positions.append({
                        'symbol': symbol,
                        'amount': float(amount),
                        'amount_usd': float(amount_usd)
                    })

            self.users.append({
                'address': user_address,
                'collateral': collateral_positions,
                'debt': debt_positions,
                'total_debt_usd': float(total_debt),
                'total_collateral_usd': float(total_collateral),
                'health_factor': float(health_factor) if health_factor else 0.0,
                'user_emode_category': int(user_emode) if user_emode else 0
            })

        cursor.close()
        print(f"✓ Loaded {len(self.users)} users with positions")

    def _load_current_prices(self):
        """Load current asset prices."""
        cursor = self.db_conn.cursor()

        cursor.execute("""
            SELECT symbol, price_usd
            FROM asset_prices
        """)

        for symbol, price in cursor.fetchall():
            self.asset_prices[symbol] = float(price)

        cursor.close()
        print(f"✓ Loaded {len(self.asset_prices)} asset prices")

    def _load_covariance_matrix(self):
        """Load covariance matrix from database."""
        cursor = self.db_conn.cursor()

        # Get all unique assets from covariance table
        cursor.execute("""
            SELECT DISTINCT asset1 FROM asset_covariance
            ORDER BY asset1
        """)

        self.asset_symbols = [row[0] for row in cursor.fetchall()]
        n_assets = len(self.asset_symbols)

        # Build covariance matrix
        cov_matrix = np.zeros((n_assets, n_assets))

        cursor.execute("""
            SELECT asset1, asset2, covariance
            FROM asset_covariance
        """)

        for asset1, asset2, cov in cursor.fetchall():
            i = self.asset_symbols.index(asset1)
            j = self.asset_symbols.index(asset2)
            cov_matrix[i, j] = float(cov)

        self.covariance_matrix = cov_matrix
        cursor.close()

        print(f"✓ Loaded {n_assets}×{n_assets} covariance matrix")

    def generate_price_shocks(self) -> np.ndarray:
        """
        Generate correlated price shocks using multivariate normal distribution.

        Returns:
            Array of shape (n_simulations, n_assets) containing simulated returns
        """
        print(f"\n{'='*80}")
        print("GENERATING CORRELATED PRICE SHOCKS")
        print(f"{'='*80}\n")

        print(f"Method: Multivariate Normal with empirical covariance matrix")
        print(f"Number of scenarios: {self.n_simulations:,}")
        print(f"Assets: {len(self.asset_symbols)}")
        print(f"Mean return: 0 (standard for 1-day VaR)")

        # Generate correlated returns: r ~ N(0, Σ)
        mean_returns = np.zeros(len(self.asset_symbols))

        # Generate returns
        returns = np.random.multivariate_normal(
            mean_returns,
            self.covariance_matrix,
            size=self.n_simulations
        )

        print(f"\n✓ Generated {self.n_simulations:,} correlated shock scenarios")
        print(f"\nReturn statistics (across all scenarios):")
        for i, symbol in enumerate(self.asset_symbols):
            print(f"  {symbol:8s}: mean={returns[:, i].mean():7.4f}, std={returns[:, i].std():7.4f}")

        return returns

    def simulate_prices(self, returns: np.ndarray) -> np.ndarray:
        """
        Convert returns to simulated prices using log-normal process.

        P_T = P_0 × exp(r)

        Args:
            returns: Array of shape (n_simulations, n_assets) containing returns

        Returns:
            Array of shape (n_simulations, n_assets) containing simulated prices
        """
        prices = np.zeros_like(returns)

        for i, symbol in enumerate(self.asset_symbols):
            P_0 = self.asset_prices.get(symbol, 0)
            prices[:, i] = P_0 * np.exp(returns[:, i])

        return prices

    def calculate_user_bad_debt(self, user: dict, simulated_prices: dict) -> float:
        """
        Calculate bad debt for a single user under simulated prices.

        Uses the user's E-Mode liquidation threshold if they are in an E-Mode,
        otherwise uses the base liquidation threshold from the position.

        Args:
            user: User dictionary with collateral and debt positions
            simulated_prices: Dictionary mapping symbol -> simulated price

        Returns:
            Bad debt amount (0 if user remains solvent)
        """
        # Get user's E-Mode LT (if in E-Mode)
        user_emode = user.get('user_emode_category', 0)
        emode_lt = None
        if user_emode > 0 and user_emode in self.emode_categories:
            emode_lt = self.emode_categories[user_emode]['lt']

        # Calculate total debt value at simulated prices
        total_debt = 0.0
        for debt_pos in user['debt']:
            symbol = debt_pos['symbol']
            amount = debt_pos['amount']
            price = simulated_prices.get(symbol, self.asset_prices.get(symbol, 0))
            total_debt += amount * price

        # Calculate recoverable collateral value
        # Only count collateral where usage_as_collateral_enabled = True
        # Weight by liquidation threshold (E-Mode LT if user is in E-Mode, else base LT)
        recoverable_collateral = 0.0
        for coll_pos in user['collateral']:
            # Check if this collateral is enabled
            if not coll_pos['usage_as_collateral_enabled']:
                continue

            symbol = coll_pos['symbol']
            amount = coll_pos['amount']
            price = simulated_prices.get(symbol, self.asset_prices.get(symbol, 0))

            # Use E-Mode LT if user is in E-Mode, otherwise use base LT
            if emode_lt is not None:
                lt = emode_lt
            else:
                lt = coll_pos['liquidation_threshold']

            # Recoverable value = amount × price × liquidation_threshold
            recoverable_collateral += amount * price * lt

        # Calculate bad debt
        # If recoverable collateral < total debt, the difference is bad debt
        bad_debt = max(0.0, total_debt - recoverable_collateral)

        return bad_debt

    def run_simulation(self):
        """Run full Monte Carlo simulation."""
        print(f"\n{'='*80}")
        print("RUNNING MONTE CARLO SIMULATION")
        print(f"{'='*80}\n")

        # Generate price shocks
        returns = self.generate_price_shocks()
        simulated_prices_matrix = self.simulate_prices(returns)

        # Store for database export
        self.returns_matrix = returns
        self.simulated_prices_matrix = simulated_prices_matrix

        # Run simulation for each scenario
        print(f"\nSimulating user-level solvency across {self.n_simulations:,} scenarios...")

        scenario_losses = np.zeros(self.n_simulations)

        for scenario_idx in range(self.n_simulations):
            # Get prices for this scenario
            scenario_prices = {
                symbol: simulated_prices_matrix[scenario_idx, i]
                for i, symbol in enumerate(self.asset_symbols)
            }

            # Calculate bad debt for each user
            scenario_bad_debt = 0.0
            for user in self.users:
                user_bad_debt = self.calculate_user_bad_debt(user, scenario_prices)
                scenario_bad_debt += user_bad_debt

            scenario_losses[scenario_idx] = scenario_bad_debt

            # Progress indicator
            if (scenario_idx + 1) % 1000 == 0:
                print(f"  Completed {scenario_idx + 1:,} / {self.n_simulations:,} scenarios")

        self.simulation_results = scenario_losses

        print(f"\n✓ Simulation complete!")
        print(f"  Total scenarios: {self.n_simulations:,}")
        print(f"  Users analyzed: {len(self.users)}")

    def calculate_var_metrics(self) -> dict:
        """Calculate VaR and related risk metrics."""
        print(f"\n{'='*80}")
        print("VALUE AT RISK (VaR) ANALYSIS")
        print(f"{'='*80}\n")

        losses = self.simulation_results

        # VaR at different confidence levels
        var_95 = np.percentile(losses, 95)
        var_99 = np.percentile(losses, 99)
        var_99_9 = np.percentile(losses, 99.9)

        # Expected Shortfall (CVaR) - average loss beyond VaR
        es_95 = losses[losses >= var_95].mean()
        es_99 = losses[losses >= var_99].mean()

        # Basic statistics
        mean_loss = losses.mean()
        median_loss = np.median(losses)
        max_loss = losses.max()
        min_loss = losses.min()
        std_loss = losses.std()

        # Probability of any loss
        prob_loss = (losses > 0).sum() / len(losses)

        metrics = {
            'var_95': var_95,
            'var_99': var_99,
            'var_99_9': var_99_9,
            'es_95': es_95,
            'es_99': es_99,
            'mean_loss': mean_loss,
            'median_loss': median_loss,
            'max_loss': max_loss,
            'min_loss': min_loss,
            'std_loss': std_loss,
            'prob_loss': prob_loss
        }

        print(f"VaR Metrics (Protocol-Level Bad Debt):")
        print(f"{'='*80}")
        print(f"  Mean Loss:              ${mean_loss:,.2f}")
        print(f"  Median Loss:            ${median_loss:,.2f}")
        print(f"  Std Dev:                ${std_loss:,.2f}")
        print(f"  Maximum Loss:           ${max_loss:,.2f}")
        print(f"  Probability of Loss:    {prob_loss*100:.2f}%")
        print(f"\nValue at Risk:")
        print(f"  VaR (95%):              ${var_95:,.2f}")
        print(f"  VaR (99%):              ${var_99:,.2f}")
        print(f"  VaR (99.9%):            ${var_99_9:,.2f}")
        print(f"\nExpected Shortfall (CVaR):")
        print(f"  ES (95%):               ${es_95:,.2f}")
        print(f"  ES (99%):               ${es_99:,.2f}")
        print(f"{'='*80}\n")

        return metrics

    def plot_results(self, save_path: str = None):
        """Generate comprehensive visualization of simulation results."""
        if save_path is None:
            save_path = os.path.join(VIZ_DIR, 'var_analysis.png')
        print(f"\nGenerating visualizations...")

        losses = self.simulation_results
        metrics = self.calculate_var_metrics()

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Aave V3 Protocol Value at Risk Analysis\nMonte Carlo Simulation Results',
                     fontsize=16, fontweight='bold')

        # 1. Loss Distribution Histogram
        ax1 = axes[0, 0]
        ax1.hist(losses, bins=100, alpha=0.7, edgecolor='black', color='steelblue')
        ax1.axvline(metrics['var_95'], color='orange', linestyle='--', linewidth=2, label=f"VaR 95%: ${metrics['var_95']:,.0f}")
        ax1.axvline(metrics['var_99'], color='red', linestyle='--', linewidth=2, label=f"VaR 99%: ${metrics['var_99']:,.0f}")
        ax1.set_xlabel('Bad Debt (USD)', fontsize=12)
        ax1.set_ylabel('Frequency', fontsize=12)
        ax1.set_title('Distribution of Protocol Bad Debt', fontsize=14, fontweight='bold')
        ax1.legend(fontsize=10)
        ax1.grid(True, alpha=0.3)

        # 2. Cumulative Distribution
        ax2 = axes[0, 1]
        sorted_losses = np.sort(losses)
        cumulative = np.arange(1, len(sorted_losses) + 1) / len(sorted_losses)
        ax2.plot(sorted_losses, cumulative * 100, linewidth=2, color='steelblue')
        ax2.axhline(95, color='orange', linestyle='--', linewidth=1, alpha=0.7)
        ax2.axhline(99, color='red', linestyle='--', linewidth=1, alpha=0.7)
        ax2.axvline(metrics['var_95'], color='orange', linestyle='--', linewidth=2, alpha=0.7)
        ax2.axvline(metrics['var_99'], color='red', linestyle='--', linewidth=2, alpha=0.7)
        ax2.set_xlabel('Bad Debt (USD)', fontsize=12)
        ax2.set_ylabel('Cumulative Probability (%)', fontsize=12)
        ax2.set_title('Cumulative Distribution Function', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        # 3. Tail Risk Analysis (log scale)
        ax3 = axes[1, 0]
        losses_nonzero = losses[losses > 0]
        if len(losses_nonzero) > 0:
            ax3.hist(losses_nonzero, bins=100, alpha=0.7, edgecolor='black', color='coral')
            ax3.set_yscale('log')
            ax3.axvline(metrics['var_95'], color='orange', linestyle='--', linewidth=2)
            ax3.axvline(metrics['var_99'], color='red', linestyle='--', linewidth=2)
            ax3.set_xlabel('Bad Debt (USD)', fontsize=12)
            ax3.set_ylabel('Frequency (log scale)', fontsize=12)
            ax3.set_title('Tail Risk Analysis (Non-Zero Losses)', fontsize=14, fontweight='bold')
            ax3.grid(True, alpha=0.3)

        # 4. Summary Statistics Table
        ax4 = axes[1, 1]
        ax4.axis('off')

        summary_data = [
            ['Metric', 'Value'],
            ['', ''],
            ['Number of Scenarios', f'{self.n_simulations:,}'],
            ['Number of Users', f'{len(self.users):,}'],
            ['', ''],
            ['Mean Loss', f'${metrics["mean_loss"]:,.2f}'],
            ['Median Loss', f'${metrics["median_loss"]:,.2f}'],
            ['Std Deviation', f'${metrics["std_loss"]:,.2f}'],
            ['', ''],
            ['VaR (95%)', f'${metrics["var_95"]:,.2f}'],
            ['VaR (99%)', f'${metrics["var_99"]:,.2f}'],
            ['VaR (99.9%)', f'${metrics["var_99_9"]:,.2f}'],
            ['', ''],
            ['Expected Shortfall (95%)', f'${metrics["es_95"]:,.2f}'],
            ['Expected Shortfall (99%)', f'${metrics["es_99"]:,.2f}'],
            ['', ''],
            ['Probability of Loss', f'{metrics["prob_loss"]*100:.2f}%'],
            ['Maximum Loss', f'${metrics["max_loss"]:,.2f}']
        ]

        table = ax4.table(cellText=summary_data, loc='center', cellLoc='left',
                         colWidths=[0.6, 0.4])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)

        # Style header row
        for i in range(2):
            table[(0, i)].set_facecolor('#4472C4')
            table[(0, i)].set_text_props(weight='bold', color='white')

        # Style metric rows
        for i in [1, 4, 8, 12, 15]:
            for j in range(2):
                table[(i, j)].set_facecolor('#E7E6E6')

        ax4.set_title('Summary Statistics', fontsize=14, fontweight='bold', pad=20)

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved visualization to: {save_path}")

        return fig

    def export_results(self, output_path: str = None):
        """Export simulation results to CSV."""
        if output_path is None:
            output_path = os.path.join(DATA_DIR, 'var_simulation_results.csv')
        print(f"\nExporting results...")

        df = pd.DataFrame({
            'scenario': range(self.n_simulations),
            'bad_debt_usd': self.simulation_results
        })

        df.to_csv(output_path, index=False)
        print(f"✓ Exported {len(df)} scenarios to: {output_path}")

    def save_to_database(self, metrics: dict):
        """Save simulation results, price trajectories, and scenarios to database."""
        print(f"\nSaving simulation to database...")

        cursor = self.db_conn.cursor()

        # Step 1: Create simulation run record
        cursor.execute("""
            INSERT INTO simulation_runs (
                n_scenarios, random_seed, var_95, var_99, var_99_9,
                mean_bad_debt, std_bad_debt
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id
        """, (
            self.n_simulations,
            self.random_seed,
            Decimal(str(metrics['var_95'])),
            Decimal(str(metrics['var_99'])),
            Decimal(str(metrics['var_99_9'])),
            Decimal(str(metrics['mean_loss'])),
            Decimal(str(metrics['std_loss']))
        ))

        run_id = cursor.fetchone()[0]
        self.db_conn.commit()

        print(f"  ✓ Created simulation run #{run_id}")

        # Step 2: Save scenario results (bad debt per scenario)
        print(f"  Saving {self.n_simulations:,} scenario results...")

        scenario_data = []
        for scenario_idx in range(self.n_simulations):
            scenario_data.append((
                run_id,
                scenario_idx,
                Decimal(str(self.simulation_results[scenario_idx]))
            ))

        cursor.executemany("""
            INSERT INTO scenario_results (run_id, scenario_id, total_bad_debt)
            VALUES (%s, %s, %s)
        """, scenario_data)

        self.db_conn.commit()
        print(f"  ✓ Saved scenario results")

        # Step 3: Save ALL price trajectories
        # 10,000 scenarios × 10 assets = 100k rows (manageable size)
        print(f"  Saving all {self.n_simulations:,} price trajectories...")

        total_saved = 0
        batch_size = 10000  # Insert in batches to manage memory

        for batch_start in range(0, self.n_simulations, 1000):
            batch_end = min(batch_start + 1000, self.n_simulations)
            price_data = []

            for scenario_idx in range(batch_start, batch_end):
                for asset_idx, symbol in enumerate(self.asset_symbols):
                    current_price = self.asset_prices.get(symbol, 0)
                    simulated_price = self.simulated_prices_matrix[scenario_idx, asset_idx]
                    return_pct = self.returns_matrix[scenario_idx, asset_idx] * 100

                    price_data.append((
                        run_id,
                        scenario_idx,
                        symbol,
                        Decimal(str(current_price)),
                        Decimal(str(simulated_price)),
                        Decimal(str(return_pct))
                    ))

            cursor.executemany("""
                INSERT INTO simulated_prices (
                    run_id, scenario_id, asset_symbol, current_price,
                    simulated_price, return_pct
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, price_data)

            self.db_conn.commit()
            total_saved += len(price_data)

            if (batch_end) % 5000 == 0 or batch_end == self.n_simulations:
                print(f"    Progress: {batch_end:,} / {self.n_simulations:,} scenarios")

        print(f"  ✓ Saved {total_saved:,} price trajectory records (all scenarios)")

        cursor.close()

        print(f"\n✓ Database save complete!")
        print(f"  Run ID: {run_id}")
        print(f"  Query examples in README.md")

        return run_id

    def run(self):
        """Main execution pipeline."""
        print(f"\n{'='*80}")
        print("AAVE V3 PROTOCOL VALUE AT RISK SIMULATION")
        print(f"{'='*80}")
        print(f"Simulation Parameters:")
        print(f"  Number of scenarios: {self.n_simulations:,}")
        print(f"  Random seed: {self.random_seed}")
        print(f"  Time horizon: 1 day")
        print(f"  Model: Multivariate log-normal with empirical covariance")
        print(f"{'='*80}\n")

        try:
            # Load data
            self.load_data()

            # Run simulation
            self.run_simulation()

            # Calculate metrics
            metrics = self.calculate_var_metrics()

            # Save to database
            run_id = self.save_to_database(metrics)

            # Generate visualizations
            self.plot_results()

            # Export results
            self.export_results()

            print(f"\n{'='*80}")
            print("SIMULATION COMPLETE!")
            print(f"{'='*80}")
            print(f"✓ Analyzed {len(self.users)} users across {self.n_simulations:,} scenarios")
            print(f"✓ Protocol VaR (99%): ${metrics['var_99']:,.2f}")
            print(f"✓ Results saved to database (run_id: {run_id})")
            print(f"✓ Results exported and visualized")
            print(f"{'='*80}\n")

        except Exception as e:
            print(f"\n✗ Error during simulation: {e}")
            raise
        finally:
            self.db_conn.close()


if __name__ == "__main__":
    # Run simulation with 10,000 scenarios
    simulation = AaveVaRSimulation(n_simulations=10000, random_seed=42)
    simulation.run()
