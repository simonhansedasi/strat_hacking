"""
Probability analysis for Spots.

Core question: given a yard total Y and rolling N dice, what fraction of
outcomes cause a bust — and how does placement opportunity change that?

All distributions are computed exactly (no Monte Carlo needed for the bust
curve itself).
"""
from __future__ import annotations
from functools import lru_cache
from itertools import product
from collections import Counter
import math


# ── Exact bust probability ────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def sum_dist(n_dice: int) -> dict[int, float]:
    """
    Exact probability distribution of the sum of n_dice independent d6.
    Returns {sum: probability}.
    """
    if n_dice == 0:
        return {0: 1.0}
    prev = sum_dist(n_dice - 1)
    dist: dict[int, float] = {}
    for s, p in prev.items():
        for face in range(1, 7):
            k = s + face
            dist[k] = dist.get(k, 0.0) + p / 6
    return dist


def bust_prob_no_placement(yard_total: int, n_dice: int) -> float:
    """
    P(bust) if ALL dice must be buried (worst case — no placement options).
    Bust when yard_total + roll_sum > 7.
    """
    threshold = 7 - yard_total
    dist = sum_dist(n_dice)
    return sum(p for s, p in dist.items() if s > threshold)


def bust_prob_with_placement(
    yard_total: int,
    n_dice: int,
    open_spaces: list[int],
    strategy: str = 'greedy',
) -> float:
    """
    Estimate P(bust) when the player has open dog spaces to absorb dice.

    strategy='greedy': place any die that matches an open space (never bury
    a die you can place). This is the dominant strategy for individual dice.

    open_spaces: list of die values still needed across all dogs
                 (duplicates matter — two dogs both needing a 3 = [3, 3]).

    Note: this enumerates all outcomes so is only practical for small n_dice.
    For n_dice > 6 use monte_carlo_bust_prob instead.
    """
    if n_dice > 7:
        return monte_carlo_bust_prob(yard_total, n_dice, open_spaces, n=200_000)

    available = Counter(open_spaces)
    busts = 0
    total = 6 ** n_dice

    for roll in product(range(1, 7), repeat=n_dice):
        remaining = Counter(available)
        buried_sum = yard_total
        busted = False
        for die in sorted(roll):          # sort: greedy places smallest first
            if remaining[die] > 0:
                remaining[die] -= 1       # placed on dog
            else:
                buried_sum += die         # must bury
                if buried_sum > 7:
                    busted = True
                    break
        if busted:
            busts += 1

    return busts / total


def monte_carlo_bust_prob(
    yard_total: int,
    n_dice: int,
    open_spaces: list[int],
    n: int = 100_000,
    seed: int = 42,
) -> float:
    """Monte Carlo fallback for large n_dice."""
    import random
    rng = random.Random(seed)
    available = Counter(open_spaces)
    busts = 0
    for _ in range(n):
        remaining = Counter(available)
        buried = yard_total
        busted = False
        roll = sorted(rng.randint(1, 6) for _ in range(n_dice))
        for die in roll:
            if remaining[die] > 0:
                remaining[die] -= 1
            else:
                buried += die
                if buried > 7:
                    busted = True
                    break
        if busted:
            busts += 1
    return busts / n


# ── Bust curve table ──────────────────────────────────────────────────────────

def bust_curve(max_dice: int = 10) -> dict[tuple[int, int], float]:
    """
    Returns {(yard_total, n_dice): P(bust)} for all combinations,
    assuming NO placement options (pure burial — worst case).
    Useful for understanding the raw risk landscape.
    """
    return {
        (y, n): bust_prob_no_placement(y, n)
        for y in range(8)       # 0–7 (8 would already be bust)
        for n in range(1, max_dice + 1)
    }


# ── Expected placement yield ──────────────────────────────────────────────────

def expected_placed(n_dice: int, open_spaces: list[int]) -> float:
    """
    Expected number of dice successfully placed on dogs (not buried)
    given a greedy placement strategy, ignoring bust.
    """
    if n_dice > 7:
        return _mc_expected_placed(n_dice, open_spaces)

    available = Counter(open_spaces)
    total_placed = 0
    total = 6 ** n_dice

    for roll in product(range(1, 7), repeat=n_dice):
        remaining = Counter(available)
        placed = 0
        for die in sorted(roll):
            if remaining[die] > 0:
                remaining[die] -= 1
                placed += 1
        total_placed += placed

    return total_placed / total


def _mc_expected_placed(n_dice: int, open_spaces: list[int], n: int = 100_000, seed: int = 42) -> float:
    import random
    rng = random.Random(seed)
    available = Counter(open_spaces)
    total = 0
    for _ in range(n):
        remaining = Counter(available)
        placed = 0
        for die in sorted(rng.randint(1, 6) for _ in range(n_dice)):
            if remaining[die] > 0:
                remaining[die] -= 1
                placed += 1
        total += placed
    return total / n


# ── Treat value ───────────────────────────────────────────────────────────────

def treat_value(
    roll: list[int],
    yard_total: int,
    open_spaces: list[int],
) -> float:
    """
    Expected improvement in dice placed by spending a treat to reroll.
    Positive = reroll is beneficial on average.

    Returns: E[placed after reroll] - placed_now
    """
    available = Counter(open_spaces)

    # How many dice would be placed with current roll?
    remaining = Counter(available)
    placed_now = 0
    for die in sorted(roll):
        if remaining[die] > 0:
            remaining[die] -= 1
            placed_now += 1

    # After reroll, expected placed (same number of dice, same open spaces)
    n = len(roll)
    exp_after = expected_placed(n, open_spaces)

    return exp_after - placed_now
