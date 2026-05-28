"""
Yahtzee strategy analysis and visualisation.
Run directly:  python3 -m yahtzee.analysis
Saves four plots to yahtzee/.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt

from yahtzee.sim import simulate
from yahtzee.strategies import (
    RandomStrategy, GreedyStrategy, UpperBonusHunter,
    YahtzeeHunter, BalancedStrategy,
)

FACTORIES = [
    lambda rng: RandomStrategy(rng),
    lambda rng: GreedyStrategy(rng),
    lambda rng: UpperBonusHunter(rng),
    lambda rng: YahtzeeHunter(rng),
    lambda rng: BalancedStrategy(rng),
]
NAMES  = ['Random', 'Greedy', 'UpperBonus', 'YahtzeeHunt', 'Balanced']
COLORS = ['#aec7e8', '#1f77b4', '#ffbb78', '#d62728', '#2ca02c']
N_GAMES = 20_000

HERE = os.path.dirname(__file__)


def _get_stats():
    print(f"Simulating {N_GAMES:,} games per strategy…")
    return simulate(FACTORIES, NAMES, n_games=N_GAMES)


# ── Plot 1: Score distribution (overlapping histograms) ───────────────────────

def plot_score_distributions(stats, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 5))

    bins = np.arange(0, 501, 10)
    for i, name in enumerate(NAMES):
        scores = np.array(stats.all_scores[i])
        ax.hist(scores, bins=bins, alpha=0.45, color=COLORS[i],
                label=f"{name} (avg {stats.avg_score[i]:.0f})", density=True)

    ax.set_xlabel('Total score')
    ax.set_ylabel('Density')
    ax.set_title('Score distribution by strategy')
    ax.legend(fontsize=9)
    return ax


# ── Plot 2: Average score + std error bar chart ───────────────────────────────

def plot_avg_scores(stats, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5))

    x     = np.arange(len(NAMES))
    avgs  = stats.avg_score
    stds  = stats.std_score

    bars = ax.bar(x, avgs, color=COLORS, alpha=0.85, zorder=2)
    ax.errorbar(x, avgs, yerr=stds, fmt='none', color='black',
                capsize=5, linewidth=1.5, zorder=3)

    for bar, avg, std in zip(bars, avgs, stds):
        ax.text(bar.get_x() + bar.get_width() / 2,
                avg + std + 3, f'{avg:.0f}',
                ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(NAMES, rotation=15, ha='right')
    ax.set_ylabel('Average total score')
    ax.set_title('Average score ± 1 std dev')
    ax.set_ylim(0, max(avgs) * 1.25)
    ax.grid(axis='y', alpha=0.4, zorder=1)
    return ax


# ── Plot 3: Upper bonus rate + 250/300 thresholds ────────────────────────────

def plot_rates(stats, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 5))

    x     = np.arange(len(NAMES))
    width = 0.25

    bars1 = ax.bar(x - width, [r * 100 for r in stats.bonus_rate],
                   width, label='Upper bonus %', color='#2ca02c', alpha=0.8)
    bars2 = ax.bar(x,         [r * 100 for r in stats.pct_250_plus],
                   width, label='Score >= 250 %', color='#1f77b4', alpha=0.8)
    bars3 = ax.bar(x + width, [r * 100 for r in stats.pct_300_plus],
                   width, label='Score >= 300 %', color='#d62728', alpha=0.8)

    for bars in (bars1, bars2, bars3):
        for bar in bars:
            h = bar.get_height()
            if h > 2:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                        f'{h:.0f}%', ha='center', va='bottom', fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(NAMES, rotation=15, ha='right')
    ax.set_ylabel('% of games')
    ax.set_title('Upper bonus rate and score thresholds')
    ax.legend(fontsize=9)
    ax.set_ylim(0, 100)
    ax.grid(axis='y', alpha=0.4)
    return ax


# ── Plot 4: Cumulative score distribution (CDF) ───────────────────────────────

def plot_cdf(stats, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 5))

    for i, name in enumerate(NAMES):
        scores = sorted(stats.all_scores[i])
        y      = np.arange(1, len(scores) + 1) / len(scores)
        ax.plot(scores, y, color=COLORS[i], label=name, linewidth=1.8)

    ax.axvline(250, color='gray', linestyle='--', linewidth=0.8, alpha=0.7)
    ax.axvline(300, color='gray', linestyle=':', linewidth=0.8, alpha=0.7)
    ax.text(252, 0.05, '250', fontsize=8, color='gray')
    ax.text(302, 0.05, '300', fontsize=8, color='gray')

    ax.set_xlabel('Total score')
    ax.set_ylabel('Cumulative probability')
    ax.set_title('Cumulative score distribution (CDF)')
    ax.legend(fontsize=9)
    ax.set_xlim(0, 500)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    return ax


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    stats = _get_stats()
    print(stats)
    print()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    plot_score_distributions(stats, ax=axes[0, 0])
    plot_avg_scores(stats, ax=axes[0, 1])
    plot_rates(stats, ax=axes[1, 0])
    plot_cdf(stats, ax=axes[1, 1])

    fig.suptitle('Yahtzee strategy comparison', fontsize=14, fontweight='bold')
    fig.tight_layout()

    out = os.path.join(HERE, 'strategy_comparison.png')
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


if __name__ == '__main__':
    main()
