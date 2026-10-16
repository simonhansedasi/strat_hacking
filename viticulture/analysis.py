from __future__ import annotations
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from viticulture.sim import simulate, SimStats
from viticulture.strategies import (
    RandomStrategy, ExpansionStrategy, OrderRushStrategy, BalancedStrategy,
)

N_GAMES = 5_000
STRATEGY_FACTORIES = [
    lambda rng: RandomStrategy(rng),
    lambda rng: ExpansionStrategy(rng),
    lambda rng: OrderRushStrategy(rng),
    lambda rng: BalancedStrategy(rng),
]
NAMES = ['Random', 'Expansion', 'OrderRush', 'Balanced']
COLORS = ['#888888', '#4C8BE0', '#E07C4C', '#4CAF50']


def _stats() -> SimStats:
    print(f"Running {N_GAMES} games for analysis...")
    return simulate(STRATEGY_FACTORIES, NAMES, n_games=N_GAMES)


def plot_win_rates(stats: SimStats, ax: plt.Axes) -> None:
    x = np.arange(len(stats.strategy_names))
    bars = ax.bar(x, [r * 100 for r in stats.win_rate], color=COLORS, width=0.6)
    ax.axhline(100 / stats.n_players, color='black', linestyle='--', linewidth=0.8,
               label='Baseline (25%)')
    ax.set_xticks(x)
    ax.set_xticklabels(stats.strategy_names)
    ax.set_ylabel('Win rate (%)')
    ax.set_title('Win rates')
    ax.legend(fontsize=8)
    for bar, rate in zip(bars, stats.win_rate):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f'{rate*100:.1f}%', ha='center', va='bottom', fontsize=8)


def plot_vp_distributions(stats: SimStats, ax: plt.Axes) -> None:
    bins = np.arange(0, 32, 2)
    for i, name in enumerate(stats.strategy_names):
        ax.hist(stats.all_vp[i], bins=bins, alpha=0.55, color=COLORS[i],
                label=f'{name} (avg {stats.avg_vp[i]:.1f})', density=True)
    ax.set_xlabel('Final VP')
    ax.set_ylabel('Density')
    ax.set_title('Final VP distributions')
    ax.legend(fontsize=7)


def plot_orders_filled(stats: SimStats, ax: plt.Axes) -> None:
    x = np.arange(len(stats.strategy_names))
    bars = ax.bar(x, stats.avg_orders_filled, color=COLORS, width=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(stats.strategy_names)
    ax.set_ylabel('Avg orders filled per game')
    ax.set_title(f'Orders filled (avg game: {stats.avg_years:.1f} yrs)')
    for bar, val in zip(bars, stats.avg_orders_filled):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f'{val:.2f}', ha='center', va='bottom', fontsize=8)


def main() -> None:
    stats = _stats()
    print(stats)

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle('Viticulture — Strategy Comparison', fontsize=13, fontweight='bold')

    plot_win_rates(stats, axes[0])
    plot_vp_distributions(stats, axes[1])
    plot_orders_filled(stats, axes[2])

    plt.tight_layout()
    out = os.path.join(os.path.dirname(__file__), 'viticulture_analysis.png')
    plt.savefig(out, dpi=150)
    print(f"Saved {out}")


if __name__ == '__main__':
    main()
