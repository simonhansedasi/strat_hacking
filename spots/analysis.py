"""
Analysis and visualisation for Spots probability exploration.
Run directly:  python3 analysis.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from spots.prob import bust_prob_no_placement, bust_prob_with_placement, expected_placed, treat_value


# ── Plot 1: Bust curve heatmap (no placement) ─────────────────────────────────

def plot_bust_heatmap(max_dice: int = 10, ax=None):
    """
    Heatmap: x = dice rolled, y = yard total, colour = P(bust).
    No placement options — raw risk landscape.
    """
    yard_vals = list(range(8))     # 0–7
    dice_vals = list(range(1, max_dice + 1))

    grid = np.array([
        [bust_prob_no_placement(y, n) for n in dice_vals]
        for y in yard_vals
    ])

    if ax is None:
        _, ax = plt.subplots(figsize=(9, 5))

    im = ax.imshow(grid, aspect='auto', origin='lower',
                   cmap='RdYlGn_r', vmin=0, vmax=1,
                   extent=[0.5, max_dice + 0.5, -0.5, 7.5])
    plt.colorbar(im, ax=ax, label='P(bust)')

    # Contour lines at 10%, 25%, 50%
    ax.contour(
        np.linspace(1, max_dice, max_dice),
        np.arange(8),
        grid,
        levels=[0.10, 0.25, 0.50],
        colors=['white'],
        linewidths=[0.8],
        linestyles=['--'],
    )

    ax.set_xlabel('Dice rolled')
    ax.set_ylabel('Yard total before roll')
    ax.set_yticks(range(8))
    ax.set_xticks(range(1, max_dice + 1))
    ax.set_title('P(bust) — worst case (all dice must be buried)')
    return ax


# ── Plot 2: Placement relief — how open spaces reduce bust risk ───────────────

def plot_placement_relief(yard_total: int = 3, max_dice: int = 7):
    """
    For a fixed yard total, show P(bust) vs. dice rolled for several
    open-space configurations. Shows how many open slots actually help.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    dice_range = range(1, max_dice + 1)

    configs = [
        ([], 'No open spaces (worst case)'),
        ([1, 2, 3, 4, 5, 6], 'One of each (6 slots)'),
        ([1, 1, 2, 2, 3, 3], 'Pairs 1-3 (6 slots, low values)'),
        ([4, 4, 5, 5, 6, 6], 'Pairs 4-6 (6 slots, high values)'),
        ([1]*6, 'Six 1s (best case — absorbs 1s only)'),
    ]

    for spaces, label in configs:
        probs = [bust_prob_with_placement(yard_total, n, spaces) for n in dice_range]
        ax.plot(dice_range, probs, marker='o', label=label)

    ax.axhline(0.25, color='gray', linestyle='--', linewidth=0.8, label='25% threshold')
    ax.set_xlabel('Dice rolled')
    ax.set_ylabel('P(bust)')
    ax.set_title(f'P(bust) by open-space configuration  (yard total = {yard_total})')
    ax.legend(fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_xticks(list(dice_range))
    return fig


# ── Plot 3: Expected dice placed vs. dogs ────────────────────────────────────

def plot_expected_placed():
    """
    Shows how many dice you expect to successfully place (not bury) as
    your number of open spaces grows. Useful for judging trick value.
    """
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: vary number of uniformly distributed open spaces
    dice_rolled = [2, 3, 4, 6, 8]
    space_counts = list(range(0, 13))

    ax = axes[0]
    for n in dice_rolled:
        # Uniform open spaces: equally likely to absorb any value
        expected = []
        for k in space_counts:
            # k open spaces spread uniformly across values 1-6
            spaces = [(i % 6) + 1 for i in range(k)]
            expected.append(expected_placed(n, spaces))
        ax.plot(space_counts, expected, marker='o', label=f'{n} dice')

    ax.set_xlabel('Open spaces on dogs')
    ax.set_ylabel('Expected dice placed')
    ax.set_title('Expected placement yield (uniform spaces)')
    ax.legend()

    # Right: vary dice rolled for specific realistic dog configurations
    ax = axes[1]
    dice_range = range(1, 9)

    dog_configs = [
        ([],                   'No dogs'),
        ([1, 3, 5],            '1 dog: [1,3,5]'),
        ([1, 3, 5, 2, 4, 6],  '2 dogs: [1,3,5]+[2,4,6]'),
        ([1,2,3,4,5,6,1,2,3], '3 dogs: varied'),
    ]

    for spaces, label in dog_configs:
        exp = [expected_placed(n, spaces) for n in dice_range]
        ax.plot(list(dice_range), exp, marker='o', label=label)

    ax.plot(list(dice_range), list(dice_range), 'k--', alpha=0.4, label='Perfect placement')
    ax.set_xlabel('Dice rolled')
    ax.set_ylabel('Expected dice placed')
    ax.set_title('Expected placement — realistic dog configs')
    ax.legend(fontsize=9)

    fig.tight_layout()
    return fig


# ── Plot 4: When to spend a treat ────────────────────────────────────────────

def plot_treat_value():
    """
    Shows treat value (E[placed after reroll] - placed_now) for various
    current-roll quality levels. Positive = reroll profitable on average.

    Setup: 4 dice rolled, dogs need [1, 2, 3, 4] — values 5 and 6 are misses.
    We sweep rolls from all-hits to all-misses.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    # Dogs only need 1, 2, 3, 4 — rolling 5 or 6 = must bury
    open_spaces = [1, 2, 3, 4]
    n_dice = 4
    yard_total = 2

    # Build representative rolls with 0..4 misses
    # Hits are values in open_spaces; misses are 5s (worst affordable miss)
    results = []
    for n_misses in range(n_dice + 1):
        n_hits = n_dice - n_misses
        roll = list(range(1, n_hits + 1)) + [5] * n_misses  # concrete example
        tv = treat_value(roll, yard_total=yard_total, open_spaces=open_spaces)
        results.append((n_misses, tv, roll))

    misses = [r[0] for r in results]
    values = [r[1] for r in results]

    bars = ax.bar(misses, values,
                  color=['#2ca02c' if v > 0 else '#d62728' for v in values])
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_xlabel('Misses in current roll (dice that must be buried)')
    ax.set_ylabel('Treat value: E[placed after reroll] − placed now')
    ax.set_title(
        f'When to spend a treat  ({n_dice} dice, open spaces [1–4], yard={yard_total})\n'
        f'Example rolls: 0 misses=[1,2,3,4], 2 misses=[1,2,5,5], 4 misses=[5,5,5,5]'
    )
    ax.set_xticks(misses)

    for bar, (_, v, _roll) in zip(bars, results):
        ypos = bar.get_height() + 0.01 if v >= 0 else bar.get_height() - 0.05
        ax.text(bar.get_x() + bar.get_width()/2, ypos,
                f'{v:+.2f}', ha='center', va='bottom', fontsize=10)

    return fig


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Generating Spots probability analysis...")

    fig1, ax1 = plt.subplots(figsize=(9, 5))
    plot_bust_heatmap(ax=ax1)
    fig1.tight_layout()
    fig1.savefig(os.path.join(os.path.dirname(__file__), 'bust_heatmap.png'), dpi=150)
    print("  bust_heatmap.png")

    fig2 = plot_placement_relief(yard_total=3)
    fig2.tight_layout()
    fig2.savefig(os.path.join(os.path.dirname(__file__), 'placement_relief.png'), dpi=150)
    print("  placement_relief.png")

    fig3 = plot_expected_placed()
    fig3.savefig(os.path.join(os.path.dirname(__file__), 'expected_placed.png'), dpi=150)
    print("  expected_placed.png")

    fig4 = plot_treat_value()
    fig4.tight_layout()
    fig4.savefig(os.path.join(os.path.dirname(__file__), 'treat_value.png'), dpi=150)
    print("  treat_value.png")

    print("Done.")


if __name__ == '__main__':
    main()
