"""
Unified visualization script for Aave V3 VaR Analysis.

Creates:
1. var_comprehensive_dashboard.png - 10-panel risk dashboard
2. var_hf_stress_analysis.png - HF stress scatter + liquidation cascade
3. var_concentration_analysis.png - Concentration and sensitivity analysis
4. asset_composition_supplied_vs_borrowed.png - Collateral vs Debt composition
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.facecolor'] = 'white'


def format_billions(value):
    """Format value as $X.XXB"""
    return f"${value/1e9:.2f}B"


def format_millions(value):
    """Format value as $XXXM"""
    return f"${value/1e6:.0f}M"


class VaRVisualizer:
    """Creates all visualizations for VaR analysis."""

    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            database=os.getenv('DB_NAME', 'aave_positions'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )
        self.cursor = self.conn.cursor()

        # Load simulation results
        self.results_df = pd.read_csv('var_simulation_results.csv')
        self.bad_debt = self.results_df['bad_debt_usd'].values

        # Calculate VaR metrics
        self.var_95 = np.percentile(self.bad_debt, 95)
        self.var_99 = np.percentile(self.bad_debt, 99)
        self.var_999 = np.percentile(self.bad_debt, 99.9)
        self.mean_loss = self.bad_debt.mean()
        self.std_loss = self.bad_debt.std()
        self.es_99 = self.bad_debt[self.bad_debt >= self.var_99].mean()

        # Load metadata
        self.cursor.execute("""
            SELECT n_scenarios FROM simulation_runs ORDER BY run_id DESC LIMIT 1
        """)
        self.n_scenarios = self.cursor.fetchone()[0]

        # Get asset count from covariance matrix
        self.cursor.execute("SELECT COUNT(DISTINCT asset1) FROM asset_covariance")
        self.n_assets = self.cursor.fetchone()[0]

    def create_comprehensive_dashboard(self):
        """Create 10-panel comprehensive dashboard."""
        fig = plt.figure(figsize=(20, 13))
        gs = fig.add_gridspec(4, 3, hspace=0.35, wspace=0.3, top=0.93, bottom=0.05)

        # Banner with simulation parameters
        banner_text = (
            f"{self.n_scenarios:,} Scenarios  |  1-Day VaR  |  90-Day Volatility Window  |  "
            f"Multivariate Gaussian Shocks  |  1,000 Users  |  {self.n_assets} Assets Modeled"
        )
        fig.text(0.5, 0.97, banner_text, ha='center', fontsize=11,
                 bbox=dict(boxstyle='round,pad=0.8', facecolor='lightblue', alpha=0.8),
                 fontweight='bold')

        fig.suptitle('Aave V3 Protocol Value at Risk - Comprehensive Risk Dashboard',
                     fontsize=18, fontweight='bold', y=0.985)

        # Panel 1: Loss Distribution
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.hist(self.bad_debt/1e9, bins=80, alpha=0.7, edgecolor='black', color='steelblue')
        ax1.axvline(self.var_95/1e9, color='orange', linestyle='--', linewidth=2,
                    label=f'VaR 95%: {format_billions(self.var_95)}')
        ax1.axvline(self.var_99/1e9, color='red', linestyle='--', linewidth=2,
                    label=f'VaR 99%: {format_billions(self.var_99)}')
        ax1.set_xlabel('Bad Debt ($ Billions)', fontsize=10)
        ax1.set_ylabel('Frequency', fontsize=10)
        ax1.set_title('Distribution of Protocol Bad Debt', fontsize=12, fontweight='bold')
        ax1.legend(fontsize=9)
        ax1.grid(True, alpha=0.3)

        # Panel 2: User-Level Contribution (Top 15)
        ax2 = fig.add_subplot(gs[0, 1])
        self.cursor.execute("""
            SELECT u.user_address, u.total_debt_usd,
                   SUM(CASE WHEN p.side = 'collateral' AND p.usage_as_collateral_enabled = true
                            THEN p.amount_usd * p.liquidation_threshold ELSE 0 END) as recoverable
            FROM users u
            LEFT JOIN positions p ON u.user_address = p.user_address
            WHERE u.total_debt_usd > 0
            GROUP BY u.user_address, u.total_debt_usd
            ORDER BY u.total_debt_usd DESC LIMIT 15
        """)

        user_bad_debts = []
        user_labels = []
        for i, (addr, debt, recov) in enumerate(self.cursor.fetchall(), 1):
            debt = float(debt)
            recov = float(recov) if recov else 0
            user_bad_debts.append(max(0, debt - recov) / 1e6)
            user_labels.append(f"User {i}")

        ax2.barh(user_labels, user_bad_debts, color='coral', edgecolor='black')
        ax2.set_xlabel('Bad Debt ($ Millions)', fontsize=10)
        ax2.set_title('Top 15 Users by Bad Debt', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='x')

        # Panel 3: Collateral Composition
        ax3 = fig.add_subplot(gs[0, 2])
        self.cursor.execute("""
            SELECT symbol, SUM(amount_usd) as total FROM positions
            WHERE side = 'collateral' AND user_address IN (
                SELECT user_address FROM users WHERE total_debt_usd > 0
                ORDER BY total_debt_usd DESC LIMIT 1000
            )
            GROUP BY symbol ORDER BY total DESC LIMIT 8
        """)

        assets, values = [], []
        for symbol, total in self.cursor.fetchall():
            assets.append(symbol)
            values.append(float(total) / 1e9)

        colors = plt.cm.Set3(range(len(assets)))
        ax3.pie(values, labels=assets, autopct='%1.1f%%', colors=colors, startangle=90)
        ax3.set_title('Collateral Composition (Top 8)', fontsize=12, fontweight='bold')

        # Panel 4: Debt Composition
        ax4 = fig.add_subplot(gs[1, 0])
        self.cursor.execute("""
            SELECT symbol, SUM(amount_usd) as total FROM positions
            WHERE side = 'debt' AND user_address IN (
                SELECT user_address FROM users WHERE total_debt_usd > 0
                ORDER BY total_debt_usd DESC LIMIT 1000
            )
            GROUP BY symbol ORDER BY total DESC LIMIT 8
        """)

        debt_assets, debt_values = [], []
        for symbol, total in self.cursor.fetchall():
            debt_assets.append(symbol)
            debt_values.append(float(total) / 1e9)

        colors_debt = plt.cm.Pastel1(range(len(debt_assets)))
        ax4.pie(debt_values, labels=debt_assets, autopct='%1.1f%%', colors=colors_debt, startangle=90)
        ax4.set_title('Debt Composition (Top 8)', fontsize=12, fontweight='bold')

        # Panel 5: Health Factor Distribution
        ax5 = fig.add_subplot(gs[1, 1])
        self.cursor.execute("""
            SELECT health_factor FROM users
            WHERE total_debt_usd > 0 AND health_factor IS NOT NULL AND health_factor > 0
            ORDER BY total_debt_usd DESC LIMIT 1000
        """)
        health_factors = [float(row[0]) for row in self.cursor.fetchall() if row[0] and float(row[0]) < 5]

        ax5.hist(health_factors, bins=50, alpha=0.7, edgecolor='black', color='lightcoral')
        ax5.axvline(1.0, color='red', linestyle='--', linewidth=2, label='Liquidation (HF=1.0)')
        ax5.set_xlabel('Health Factor', fontsize=10)
        ax5.set_ylabel('Number of Users', fontsize=10)
        ax5.set_title('Health Factor Distribution', fontsize=12, fontweight='bold')
        ax5.legend(fontsize=9)
        ax5.grid(True, alpha=0.3)

        # Panel 6: Correlation Heatmap
        ax6 = fig.add_subplot(gs[1, 2])
        self.cursor.execute("""
            SELECT asset1, asset2, correlation FROM asset_covariance
            WHERE asset1 IN ('WETH', 'weETH', 'wstETH', 'WBTC', 'USDC', 'USDT')
              AND asset2 IN ('WETH', 'weETH', 'wstETH', 'WBTC', 'USDC', 'USDT')
            ORDER BY asset1, asset2
        """)

        corr_data = self.cursor.fetchall()
        symbols_unique = sorted(list(set([row[0] for row in corr_data])))
        n = len(symbols_unique)
        corr_matrix = np.zeros((n, n))
        for asset1, asset2, corr in corr_data:
            i, j = symbols_unique.index(asset1), symbols_unique.index(asset2)
            corr_matrix[i, j] = float(corr)

        sns.heatmap(corr_matrix, annot=True, fmt='.3f', cmap='RdYlGn', center=0,
                    xticklabels=symbols_unique, yticklabels=symbols_unique, ax=ax6, vmin=-1, vmax=1)
        ax6.set_title('Asset Correlation Matrix', fontsize=12, fontweight='bold')

        # Panel 7: User-Level Loss Distribution
        ax7 = fig.add_subplot(gs[2, 0])
        self.cursor.execute("""
            SELECT u.user_address, u.total_debt_usd,
                   SUM(CASE WHEN p.side = 'collateral' AND p.usage_as_collateral_enabled = true
                            THEN p.amount_usd * p.liquidation_threshold ELSE 0 END) as recoverable
            FROM users u
            LEFT JOIN positions p ON u.user_address = p.user_address
            WHERE u.total_debt_usd > 0
            GROUP BY u.user_address, u.total_debt_usd
            ORDER BY u.total_debt_usd DESC LIMIT 1000
        """)

        user_bad_debts_all = []
        for _, debt, recov in self.cursor.fetchall():
            debt = float(debt)
            recov = float(recov) if recov else 0
            user_bad_debts_all.append(max(0, debt - recov) / 1e6)

        ax7.hist(user_bad_debts_all, bins=50, alpha=0.7, edgecolor='black', color='darkgreen')
        ax7.set_xlabel('User Bad Debt ($ Millions)', fontsize=10)
        ax7.set_ylabel('Number of Users', fontsize=10)
        ax7.set_title('User-Level Bad Debt Distribution', fontsize=12, fontweight='bold')
        ax7.grid(True, alpha=0.3)

        # Panel 8: Price Shock Distribution (WETH)
        ax8 = fig.add_subplot(gs[2, 1])
        self.cursor.execute("SELECT simulated_price FROM simulated_prices WHERE asset_symbol = 'WETH' ORDER BY scenario_id")
        sim_prices = [float(row[0]) for row in self.cursor.fetchall()]
        self.cursor.execute("SELECT price_usd FROM asset_prices WHERE symbol = 'WETH'")
        current_price = float(self.cursor.fetchone()[0])

        eth_returns = [(p / current_price - 1) * 100 for p in sim_prices]
        ax8.hist(eth_returns, bins=50, alpha=0.7, edgecolor='black', color='royalblue')
        ax8.axvline(0, color='black', linestyle='-', linewidth=2)
        ax8.axvline(np.percentile(eth_returns, 1), color='red', linestyle='--', linewidth=2,
                    label=f'99th %ile: {np.percentile(eth_returns, 1):.2f}%')
        ax8.set_xlabel('WETH Price Return (%)', fontsize=10)
        ax8.set_ylabel('Frequency', fontsize=10)
        ax8.set_title('1-Day Price Shock Distribution (WETH)', fontsize=12, fontweight='bold')
        ax8.legend(fontsize=9)
        ax8.grid(True, alpha=0.3)

        # Panel 9: CDF
        ax9 = fig.add_subplot(gs[2, 2])
        sorted_losses = np.sort(self.bad_debt)
        cumulative = np.arange(1, len(sorted_losses) + 1) / len(sorted_losses) * 100

        ax9.plot(sorted_losses / 1e9, cumulative, linewidth=2.5, color='steelblue')
        ax9.axhline(95, color='orange', linestyle='--', linewidth=1.5, alpha=0.7)
        ax9.axhline(99, color='red', linestyle='--', linewidth=1.5, alpha=0.7)
        ax9.axvline(self.var_95 / 1e9, color='orange', linestyle='--', linewidth=1.5, alpha=0.7)
        ax9.axvline(self.var_99 / 1e9, color='red', linestyle='--', linewidth=1.5, alpha=0.7)

        ax9.set_xlabel('Bad Debt ($ Billions)', fontsize=11, fontweight='bold')
        ax9.set_ylabel('Cumulative Probability (%)', fontsize=11, fontweight='bold')
        ax9.set_title('Cumulative Distribution', fontsize=12, fontweight='bold')
        ax9.grid(True, alpha=0.3)

        # Auto-scale x-axis based on data
        ax9.set_xlim(sorted_losses.min()/1e9 * 0.98, sorted_losses.max()/1e9 * 1.02)

        # Panel 10: Summary Table
        ax10 = fig.add_subplot(gs[3, :])
        ax10.axis('off')

        summary_data = [
            ['Risk Metric', 'Value', 'Risk Metric', 'Value'],
            ['Mean Bad Debt', format_billions(self.mean_loss), 'Std Dev', format_billions(self.std_loss)],
            ['95% VaR', format_billions(self.var_95), '99% VaR', format_billions(self.var_99)],
            ['99.9% VaR', format_billions(self.var_999), 'ES (99%)', format_billions(self.es_99)],
            ['Max Loss', format_billions(np.max(self.bad_debt)), 'Min Loss', format_billions(np.min(self.bad_debt))],
        ]

        table = ax10.table(cellText=summary_data, loc='center', cellLoc='center',
                          colWidths=[0.25, 0.25, 0.25, 0.25])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2.5)

        for i in range(4):
            table[(0, i)].set_facecolor('#4472C4')
            table[(0, i)].set_text_props(weight='bold', color='white', fontsize=11)

        ax10.set_title('Summary Statistics', fontsize=14, fontweight='bold', pad=20)

        plt.tight_layout()
        plt.savefig('var_comprehensive_dashboard.png', dpi=300, bbox_inches='tight')
        print("Created: var_comprehensive_dashboard.png")
        plt.close()

    def create_hf_stress_analysis(self):
        """Create HF stress analysis charts."""
        fig = plt.figure(figsize=(18, 10))
        gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
        fig.suptitle('Aave V3 - Health Factor Stress Analysis', fontsize=16, fontweight='bold')

        # Get current health factors
        self.cursor.execute("""
            SELECT user_address, health_factor, total_debt_usd, total_collateral_usd
            FROM users WHERE total_debt_usd > 0 ORDER BY total_debt_usd DESC LIMIT 1000
        """)

        hf_before, debt_sizes = [], []
        for addr, hf, debt, coll in self.cursor.fetchall():
            hf_before.append(float(hf) if hf else 0)
            debt_sizes.append(float(debt))

        # Simulate HF after shock (simplified)
        hf_after = [min(h * 0.93, 5) for h in hf_before]  # ~7% shock approximation

        # Panel 1: HF Scatter
        ax = fig.add_subplot(gs[0, :])
        scatter = ax.scatter(hf_before, hf_after, c=np.array(debt_sizes)/1e9,
                            s=50, alpha=0.6, cmap='YlOrRd', edgecolors='black', linewidth=0.5)
        ax.plot([0, 5], [0, 5], 'k--', linewidth=2, alpha=0.5, label='No Change')
        ax.axhline(1.0, color='red', linestyle='--', linewidth=2, alpha=0.7, label='Liquidation')
        ax.axvline(1.0, color='red', linestyle='--', linewidth=2, alpha=0.7)

        ax.set_xlabel('Health Factor (Current)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Health Factor (After Shock)', fontsize=12, fontweight='bold')
        ax.set_title('Health Factor Stress Test', fontsize=14, fontweight='bold')
        ax.legend(fontsize=10)
        ax.set_xlim(0, 5)
        ax.set_ylim(0, 5)
        ax.grid(True, alpha=0.3)

        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Total Debt ($ Billions)', fontsize=11)

        underwater_before = len([h for h in hf_before if h < 1.0])
        underwater_after = len([h for h in hf_after if h < 1.0])
        ax.text(0.98, 0.02, f'Underwater Before: {underwater_before}\nUnderwater After: {underwater_after}',
                transform=ax.transAxes, fontsize=11, ha='right', va='bottom',
                bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))

        # Panel 2: Cascade Table
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.axis('off')

        cascade_data = [
            ['Scenario', '# HF<1', '# HF<0.5', 'Debt at Risk'],
            ['Current', str(len([h for h in hf_before if h < 1.0])),
             str(len([h for h in hf_before if h < 0.5])),
             format_billions(sum([debt_sizes[i] for i in range(len(hf_before)) if hf_before[i] < 1.0]))],
            ['95% VaR', str(len([h for h in [x*0.97 for x in hf_before] if h < 1.0])),
             str(len([h for h in [x*0.97 for x in hf_before] if h < 0.5])),
             format_billions(sum([debt_sizes[i] for i in range(len(hf_before)) if hf_before[i]*0.97 < 1.0]))],
            ['99% VaR', str(len([h for h in [x*0.93 for x in hf_before] if h < 1.0])),
             str(len([h for h in [x*0.93 for x in hf_before] if h < 0.5])),
             format_billions(sum([debt_sizes[i] for i in range(len(hf_before)) if hf_before[i]*0.93 < 1.0]))],
        ]

        table = ax2.table(cellText=cascade_data, loc='center', cellLoc='center',
                         colWidths=[0.25, 0.2, 0.2, 0.35])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2.5)
        for i in range(4):
            table[(0, i)].set_facecolor('#4472C4')
            table[(0, i)].set_text_props(weight='bold', color='white')
        ax2.set_title('Liquidation Cascade Analysis', fontsize=12, fontweight='bold', pad=20)

        # Panel 3: Risk by Asset
        ax3 = fig.add_subplot(gs[1, 1])
        self.cursor.execute("""
            SELECT p.symbol, COUNT(DISTINCT u.user_address) as cnt, SUM(u.total_debt_usd) as debt
            FROM positions p JOIN users u ON p.user_address = u.user_address
            WHERE p.side = 'collateral' AND u.health_factor < 1.5 AND u.total_debt_usd > 0
            GROUP BY p.symbol ORDER BY debt DESC LIMIT 8
        """)

        assets, counts, debts = [], [], []
        for symbol, cnt, debt in self.cursor.fetchall():
            assets.append(symbol)
            counts.append(int(cnt))
            debts.append(float(debt) / 1e9)

        x = np.arange(len(assets))
        ax3.bar(x, debts, color='steelblue', edgecolor='black')
        ax3.set_xlabel('Collateral Asset', fontsize=11)
        ax3.set_ylabel('Debt at Risk ($ Billions)', fontsize=10)
        ax3.set_title('Risk by Collateral Asset (HF<1.5)', fontsize=12, fontweight='bold')
        ax3.set_xticks(x)
        ax3.set_xticklabels(assets, rotation=45, ha='right')
        ax3.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig('var_hf_stress_analysis.png', dpi=300, bbox_inches='tight')
        print("Created: var_hf_stress_analysis.png")
        plt.close()

    def create_concentration_analysis(self):
        """Create concentration analysis charts."""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Aave V3 - Risk Concentration Analysis', fontsize=16, fontweight='bold')

        # Panel 1: Cumulative bad debt by user
        ax = axes[0, 0]
        self.cursor.execute("""
            SELECT u.total_debt_usd,
                   SUM(CASE WHEN p.side = 'collateral' AND p.usage_as_collateral_enabled = true
                            THEN p.amount_usd * p.liquidation_threshold ELSE 0 END) as recoverable
            FROM users u LEFT JOIN positions p ON u.user_address = p.user_address
            WHERE u.total_debt_usd > 0
            GROUP BY u.user_address, u.total_debt_usd
            ORDER BY u.total_debt_usd DESC LIMIT 100
        """)

        cumulative = []
        running = 0
        for debt, recov in [(float(d), float(r) if r else 0) for d, r in self.cursor.fetchall()]:
            running += max(0, debt - recov)
            cumulative.append(running / 1e9)

        ax.plot(range(1, len(cumulative) + 1), cumulative, linewidth=2.5, color='darkred', marker='o', markersize=3)
        ax.set_xlabel('User Rank', fontsize=11)
        ax.set_ylabel('Cumulative Bad Debt ($ Billions)', fontsize=11)
        ax.set_title('Cumulative Bad Debt (Top 100 Users)', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)

        if cumulative:
            top10_pct = (cumulative[9] / cumulative[-1]) * 100 if len(cumulative) > 9 else 0
            ax.text(0.65, 0.15, f'Top 10: {top10_pct:.1f}%', transform=ax.transAxes, fontsize=11,
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))

        # Panel 2: Leverage distribution
        ax = axes[0, 1]
        self.cursor.execute("""
            SELECT total_debt_usd, total_collateral_usd FROM users
            WHERE total_debt_usd > 0 AND total_collateral_usd > 0
            ORDER BY total_debt_usd DESC LIMIT 1000
        """)

        leverage = [float(d)/float(c) for d, c in self.cursor.fetchall() if float(c) > 0]
        ax.hist([l for l in leverage if l < 2], bins=50, alpha=0.7, edgecolor='black', color='purple')
        ax.set_xlabel('Leverage (Debt/Collateral)', fontsize=11)
        ax.set_ylabel('Users', fontsize=11)
        ax.set_title('Leverage Distribution', fontsize=12, fontweight='bold')
        ax.axvline(np.median(leverage), color='red', linestyle='--', linewidth=2,
                   label=f'Median: {np.median(leverage):.2f}x')
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        # Panel 3: Risk exposure by asset
        ax = axes[1, 0]
        self.cursor.execute("""
            SELECT symbol, SUM(amount_usd) as total, AVG(liquidation_threshold) as lt
            FROM positions WHERE side = 'collateral' AND user_address IN (
                SELECT user_address FROM users WHERE total_debt_usd > 0
                ORDER BY total_debt_usd DESC LIMIT 1000
            )
            GROUP BY symbol ORDER BY total DESC LIMIT 10
        """)

        assets, scores = [], []
        for symbol, total, lt in self.cursor.fetchall():
            assets.append(symbol)
            scores.append(float(total) * (1 - float(lt if lt else 0)) / 1e9)

        ax.barh(assets, scores, color='indianred', edgecolor='black')
        ax.set_xlabel('Risk = Value × (1-LT) [$ Billions]', fontsize=11)
        ax.set_title('Risk Exposure by Asset', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='x')

        # Panel 4: Summary
        ax = axes[1, 1]
        ax.axis('off')

        summary = [
            ['Metric', 'Value'],
            ['99% VaR', format_billions(self.var_99)],
            ['Mean Bad Debt', format_billions(self.mean_loss)],
            ['Std Dev', format_billions(self.std_loss)],
            ['Max Loss', format_billions(np.max(self.bad_debt))],
        ]

        table = ax.table(cellText=summary, loc='center', cellLoc='center', colWidths=[0.5, 0.5])
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 2.5)
        table[(0, 0)].set_facecolor('#4472C4')
        table[(0, 1)].set_facecolor('#4472C4')
        table[(0, 0)].set_text_props(weight='bold', color='white')
        table[(0, 1)].set_text_props(weight='bold', color='white')
        ax.set_title('Key Risk Metrics', fontsize=12, fontweight='bold', pad=20)

        plt.tight_layout()
        plt.savefig('var_concentration_analysis.png', dpi=300, bbox_inches='tight')
        print("Created: var_concentration_analysis.png")
        plt.close()

    def create_asset_composition_chart(self):
        """Create asset composition pie charts (supplied vs borrowed)."""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
        fig.suptitle('Aave V3 - Asset Composition Analysis (Top 1,000 Borrowers)',
                     fontsize=16, fontweight='bold')

        # Collateral
        self.cursor.execute("""
            SELECT symbol, SUM(amount_usd) as total FROM positions
            WHERE side = 'collateral' AND user_address IN (
                SELECT user_address FROM users WHERE total_debt_usd > 0
                ORDER BY total_debt_usd DESC LIMIT 1000
            )
            GROUP BY symbol ORDER BY total DESC
        """)

        all_supplied = self.cursor.fetchall()
        total_supplied = sum([float(row[1]) for row in all_supplied])

        supplied_assets, supplied_values = [], []
        other = 0
        for i, (symbol, value) in enumerate(all_supplied):
            if i < 6:
                supplied_assets.append(symbol)
                supplied_values.append(float(value))
            else:
                other += float(value)

        if other > 0:
            supplied_assets.append('Other')
            supplied_values.append(other)

        colors = ['#8dd3c7', '#ffffb3', '#bebada', '#fb8072', '#80b1d3', '#fdb462', '#d9d9d9']
        ax1.pie(supplied_values, labels=supplied_assets,
                autopct=lambda pct: f'{pct:.1f}%\n{format_billions(pct*total_supplied/100)}',
                colors=colors, startangle=90)
        ax1.set_title(f'Supplied (Collateral)\nTotal: {format_billions(total_supplied)}',
                      fontsize=13, fontweight='bold', pad=20)

        # Debt
        self.cursor.execute("""
            SELECT symbol, SUM(amount_usd) as total FROM positions
            WHERE side = 'debt' AND user_address IN (
                SELECT user_address FROM users WHERE total_debt_usd > 0
                ORDER BY total_debt_usd DESC LIMIT 1000
            )
            GROUP BY symbol ORDER BY total DESC
        """)

        all_borrowed = self.cursor.fetchall()
        total_borrowed = sum([float(row[1]) for row in all_borrowed])

        borrowed_assets, borrowed_values = [], []
        other = 0
        for i, (symbol, value) in enumerate(all_borrowed):
            if i < 6:
                borrowed_assets.append(symbol)
                borrowed_values.append(float(value))
            else:
                other += float(value)

        if other > 0:
            borrowed_assets.append('Other')
            borrowed_values.append(other)

        colors_debt = ['#fbb4ae', '#b3cde3', '#ccebc5', '#decbe4', '#fed9a6', '#ffffcc', '#d9d9d9']
        ax2.pie(borrowed_values, labels=borrowed_assets,
                autopct=lambda pct: f'{pct:.1f}%\n{format_billions(pct*total_borrowed/100)}',
                colors=colors_debt, startangle=90)
        ax2.set_title(f'Borrowed (Debt)\nTotal: {format_billions(total_borrowed)}',
                      fontsize=13, fontweight='bold', pad=20)

        plt.tight_layout()
        plt.savefig('asset_composition_supplied_vs_borrowed.png', dpi=300, bbox_inches='tight')
        print("Created: asset_composition_supplied_vs_borrowed.png")
        plt.close()

    def run_all(self):
        """Generate all visualizations."""
        print("\n" + "="*60)
        print("GENERATING VISUALIZATIONS")
        print("="*60 + "\n")

        self.create_comprehensive_dashboard()
        self.create_hf_stress_analysis()
        self.create_concentration_analysis()
        self.create_asset_composition_chart()

        print("\n" + "="*60)
        print("ALL VISUALIZATIONS COMPLETE")
        print("="*60)
        print("Files created:")
        print("  - var_comprehensive_dashboard.png")
        print("  - var_hf_stress_analysis.png")
        print("  - var_concentration_analysis.png")
        print("  - asset_composition_supplied_vs_borrowed.png")
        print("="*60 + "\n")

        self.cursor.close()
        self.conn.close()


if __name__ == "__main__":
    viz = VaRVisualizer()
    viz.run_all()
