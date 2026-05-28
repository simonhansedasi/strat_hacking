"""
Qwixx strategy analysis and visualisation.
Run directly:  python3 -m qwixx.analysis
Saves strategy_comparison.png to qwixx/.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt

from qwixx.sim import simulate
from qwixx.strategies import (
    RandomStrategy, AggressiveStrategy, ConservativeStrategy,
    LockHunterStrategy, BalancedStrategy,
)

FACTORIES = [
    lambda rng: RandomStrategy(rng),
    lambda rng: AggressiveStrategy(rng),
    lambda rng: ConservativeStrategy(rng),
    lambda rng: LockHunterStrategy(rng),
    lambda rng: BalancedStrategy(rng),
]
NAMES     = ['Random', 'Aggressive', 'Conservative', 'LockHunter', 'Balanced']
PLT_COLS  = ['#aec7e8', '#1f77b4', '#ffbb78', '#d62728', '#2ca02c']
N_GAMES   = 20_000
HERE      = os.path.dirname(__file__)


def _stats():
    print(f"Simulating {N_GAMES:,} games...")
    return simulate(FACTORIES, NAMES, n_games=N_GAMES)


def plot_distributions(stats, ax):
    bins = np.arange(-20, 181, 5)
    for i, name in enumerate(NAMES):
        ax.hist(np.array(stats.all_scores[i]), bins=bins, alpha=0.45,
                color=PLT_COLS[i], label=f"{name} (avg {stats.avg_score[i]:.0f})",
                density=True)
    ax.set_xlabel('Total score')
    ax.set_ylabel('Density')
    ax.set_title('Score distribution by strategy')
    ax.legend(fontsize=8)


def plot_avg_scores(stats, ax):
    x    = np.arange(len(NAMES))
    avgs = stats.avg_score
    stds = stats.std_score
    bars = ax.bar(x, avgs, color=PLT_COLS, alpha=0.85, zorder=2)
    ax.errorbar(x, avgs, yerr=stds, fmt='none', color='black',
                capsize=5, linewidth=1.5, zorder=3)
    for bar, avg, std in zip(bars, avgs, stds):
        ax.text(bar.get_x() + bar.get_width() / 2, avg + std + 1,
                f'{avg:.0f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(NAMES, rotation=15, ha='right')
    ax.set_ylabel('Average total score')
    ax.set_title('Average score +/- 1 std dev')
    ax.set_ylim(0, max(avgs) * 1.3)
    ax.grid(axis='y', alpha=0.4, zorder=1)
    # annotate win rate below each bar
    for i, (bar, wr) in enumerate(zip(bars, stats.win_rate)):
        ax.text(bar.get_x() + bar.get_width() / 2, 1,
                f'win {wr:.0%}', ha='center', va='bottom', fontsize=7, color='white')


def plot_crosses(stats, ax):
    x         = np.arange(len(NAMES))
    width     = 0.18
    row_cols  = ['#d62728', '#ffd700', '#2ca02c', '#1f77b4']
    offsets   = [-1.5, -0.5, 0.5, 1.5]
    for color, rc, off in zip(['red', 'yellow', 'green', 'blue'], row_cols, offsets):
        vals = [stats.avg_crosses[i][color] for i in range(len(NAMES))]
        ax.bar(x + off * width, vals, width, label=color.capitalize(),
               color=rc, alpha=0.82)
    ax.set_xticks(x)
    ax.set_xticklabels(NAMES, rotation=15, ha='right')
    ax.set_ylabel('Average crosses')
    ax.set_title('Average crosses per row')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.4)


def plot_cdf(stats, ax):
    for i, name in enumerate(NAMES):
        scores = sorted(stats.all_scores[i])
        y      = np.arange(1, len(scores) + 1) / len(scores)
        ax.plot(scores, y, color=PLT_COLS[i], label=name, linewidth=1.8)
    ax.set_xlabel('Total score')
    ax.set_ylabel('Cumulative probability')
    ax.set_title('CDF by strategy')
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)


def main():
    stats = _stats()
    print(stats)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    plot_distributions(stats, axes[0, 0])
    plot_avg_scores(stats, axes[0, 1])
    plot_crosses(stats, axes[1, 0])
    plot_cdf(stats, axes[1, 1])

    fig.suptitle('Qwixx strategy comparison', fontsize=14, fontweight='bold')
    fig.tight_layout()
    out = os.path.join(HERE, 'strategy_comparison.png')
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


if __name__ == '__main__':
    main()
