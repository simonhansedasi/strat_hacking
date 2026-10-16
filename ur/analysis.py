"""
Royal Game of Ur strategy analysis.
Run directly:  python3 -m ur.analysis
Saves strategy_comparison.png to ur/.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from ur.sim import simulate
from ur.strategies import (
    RandomStrategy, ProgressStrategy, SafeStrategy,
    AggressiveStrategy, RosetteHunterStrategy, BalancedStrategy,
)

FACTORIES = [
    lambda rng: RandomStrategy(rng),
    lambda rng: ProgressStrategy(rng),
    lambda rng: SafeStrategy(rng),
    lambda rng: AggressiveStrategy(rng),
    lambda rng: RosetteHunterStrategy(rng),
    lambda rng: BalancedStrategy(rng),
]
NAMES = ["Random", "Progress", "Safe", "Aggressive", "RosetteHunter", "Balanced"]
COLORS = ['#aec7e8', '#1f77b4', '#ffbb78', '#ff7f0e', '#d62728', '#2ca02c']
N_GAMES = 10_000
HERE = os.path.dirname(__file__)


def _stats():
    print(f"Simulating {N_GAMES:,} games per pair...")
    return simulate(FACTORIES, NAMES, n_games=N_GAMES)


def plot_win_rates(stats, ax):
    rates = [stats.win_rate(i) * 100 for i in range(len(NAMES))]
    bars = ax.bar(NAMES, rates, color=COLORS, edgecolor='white', linewidth=0.8)
    ax.set_ylabel("Overall win % (round-robin)")
    ax.set_title("Royal Game of Ur — strategy win rates")
    ax.set_ylim(0, max(rates) * 1.25)
    ax.axhline(100 / len(NAMES), color='grey', linestyle='--', linewidth=0.8,
               label=f"random baseline ({100/len(NAMES):.0f}%)")
    ax.legend(fontsize=8)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{rate:.1f}%", ha='center', va='bottom', fontsize=8)
    ax.tick_params(axis='x', rotation=20)


def plot_heatmap(stats, ax):
    n = len(NAMES)
    matrix = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i, j] = stats.h2h_rate(i, j) * 100

    im = ax.imshow(matrix, vmin=0, vmax=100, cmap='RdYlGn', aspect='auto')
    plt.colorbar(im, ax=ax, label='Win % (row vs col)')
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(NAMES, rotation=35, ha='right', fontsize=8)
    ax.set_yticklabels(NAMES, fontsize=8)
    ax.set_title("Head-to-head win % (row beats col)")
    for i in range(n):
        for j in range(n):
            if not np.isnan(matrix[i, j]):
                ax.text(j, i, f"{matrix[i,j]:.0f}",
                        ha='center', va='center', fontsize=7,
                        color='black' if 20 < matrix[i, j] < 80 else 'white')


def main():
    stats = _stats()
    print(stats)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    plot_win_rates(stats, axes[0])
    plot_heatmap(stats, axes[1])
    fig.tight_layout()

    out = os.path.join(HERE, "strategy_comparison.png")
    fig.savefig(out, dpi=150)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
