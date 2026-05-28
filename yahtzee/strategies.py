"""
Strategy interface and implementations for Yahtzee.

BaseStrategy defines two hooks:

  choose_keep(dice, roll_num, scorecard) -> list[int]
    Return the multisubset of dice values to keep; the rest are rerolled.
    roll_num is 1 (after 1st roll) or 2 (after 2nd roll).

  choose_category(dice, scorecard) -> str
    Return the category name to score after the final roll.

Strategies:
  RandomStrategy      — uniform random baseline
  GreedyStrategy      — maximize immediate score at every decision
  UpperBonusHunter    — grind the upper section to secure the 63-pt bonus
  YahtzeeHunter       — obsessively chase five-of-a-kind
  BalancedStrategy    — adaptive EV weighting; tracks bonus feasibility
"""
from __future__ import annotations
from collections import Counter
from typing import Optional, TYPE_CHECKING
import random

from yahtzee.game import (
    CATEGORIES, UPPER_CATS, UPPER_VALUES, MAX_SCORE,
    possible_score, joker_forced_upper,
    UPPER_BONUS_THRESHOLD, N_DICE,
)

if TYPE_CHECKING:
    from yahtzee.game import Scorecard


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _keep_for_category(category: str, dice: list[int]) -> list[int]:
    """Return the multisubset of dice values to keep when targeting this category."""
    counts = Counter(dice)

    if category in UPPER_VALUES:
        v = UPPER_VALUES[category]
        return [d for d in dice if d == v]

    if category in ('three_of_a_kind', 'four_of_a_kind', 'yahtzee'):
        most = counts.most_common(1)[0][0]
        return [d for d in dice if d == most]

    if category == 'full_house':
        mc = counts.most_common()
        if len(mc) >= 2:
            keep_vals = {mc[0][0], mc[1][0]}
            return [d for d in dice if d in keep_vals]
        return dice[:]

    if category in ('small_straight', 'large_straight'):
        target = 4 if category == 'small_straight' else 5
        return _keep_straight(dice, target)

    if category == 'chance':
        return [d for d in dice if d >= 4]

    return dice[:]


def _keep_straight(dice: list[int], target_len: int) -> list[int]:
    """Return up to target_len unique sequential dice forming the longest run."""
    unique = sorted(set(dice))
    if not unique:
        return []

    best: list[int] = []
    current: list[int] = [unique[0]]
    for v in unique[1:]:
        if v == current[-1] + 1:
            current.append(v)
        else:
            if len(current) > len(best):
                best = current[:]
            current = [v]
    if len(current) > len(best):
        best = current[:]

    keep_vals = set(best[:target_len])
    result, used = [], Counter()
    for d in dice:
        if d in keep_vals and used[d] < 1:
            result.append(d)
            used[d] += 1
    return result


def _progress(category: str, dice: list[int]) -> float:
    """
    0-1 measure of how close the current dice are to scoring this category.
    Used as a proxy for 'how worth keeping these dice are' when possible_score == 0.
    """
    counts = Counter(dice)
    if category in UPPER_VALUES:
        v = UPPER_VALUES[category]
        return counts.get(v, 0) / N_DICE
    if category == 'yahtzee':
        return counts.most_common(1)[0][1] / N_DICE
    if category == 'three_of_a_kind':
        return min(counts.most_common(1)[0][1], 3) / 3
    if category == 'four_of_a_kind':
        return min(counts.most_common(1)[0][1], 4) / 4
    if category == 'full_house':
        mc = counts.most_common()
        if len(mc) >= 2:
            return min(mc[0][1], 3) / 3 * 0.6 + min(mc[1][1], 2) / 2 * 0.4
        return min(mc[0][1], 3) / 3 * 0.5
    if category == 'small_straight':
        kept = _keep_straight(dice, 4)
        return len(kept) / 4
    if category == 'large_straight':
        kept = _keep_straight(dice, 5)
        return len(kept) / 5
    if category == 'chance':
        return sum(d for d in dice if d >= 4) / (N_DICE * 4)
    return 0.5


def _potential(category: str, dice: list[int]) -> float:
    """
    Combined score estimate: actual score if > 0, else progress-weighted max.
    Gives non-zero signal for partial setups (e.g. 3 matching dice toward yahtzee).
    """
    actual = possible_score(category, dice)
    if actual > 0:
        return float(actual)
    return MAX_SCORE.get(category, 20) * _progress(category, dice) * 0.6


def _best_immediate(dice: list[int], scorecard: 'Scorecard') -> str:
    """Return the available category with the highest actual possible_score."""
    avail = scorecard.available
    return max(avail, key=lambda c: possible_score(c, dice))


def _apply_joker_priority(
    dice: list[int],
    scorecard: 'Scorecard',
    preferred: Optional[str] = None,
) -> str:
    """
    Enforce joker rule priority order:
      1. Matching upper category (forced if open).
      2. preferred (if given and available).
      3. Any available lower category (best scoring).
      4. Any available upper category (fallback, likely 0).
    """
    forced = joker_forced_upper(dice, scorecard)
    if forced:
        return forced

    avail = scorecard.available
    if preferred and preferred in avail:
        return preferred

    lower = [c for c in avail if c not in UPPER_VALUES]
    if lower:
        return max(lower, key=lambda c: possible_score(c, dice))

    return avail[0]


# ── Base ───────────────────────────────────────────────────────────────────────

class BaseStrategy:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def choose_keep(
        self, dice: list[int], roll_num: int, scorecard: 'Scorecard'
    ) -> list[int]:
        """Return multisubset of dice values to keep; remainder are rerolled."""
        return []

    def choose_category(self, dice: list[int], scorecard: 'Scorecard') -> str:
        """Return category name to score."""
        return scorecard.available[0]


# ── RandomStrategy ─────────────────────────────────────────────────────────────

class RandomStrategy(BaseStrategy):
    def choose_keep(self, dice, roll_num, scorecard):
        shuffled = dice[:]
        self.rng.shuffle(shuffled)
        return shuffled[: self.rng.randint(0, N_DICE)]

    def choose_category(self, dice, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return forced
        return self.rng.choice(scorecard.available)


# ── GreedyStrategy ─────────────────────────────────────────────────────────────

class GreedyStrategy(BaseStrategy):
    """
    At each decision: find the available category that scores highest with the
    current dice, keep dice relevant to it, and score it immediately at the end.
    Never thinks ahead — purely maximises the current roll.
    """

    def choose_keep(self, dice, roll_num, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return dice[:]
        target = _best_immediate(dice, scorecard)
        return _keep_for_category(target, dice)

    def choose_category(self, dice, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return forced
        return _best_immediate(dice, scorecard)


# ── UpperBonusHunter ───────────────────────────────────────────────────────────

class UpperBonusHunter(BaseStrategy):
    """
    Cycles through upper categories (ones first, then twos, …) and tries to
    fill them all. Once the upper section is complete, plays greedily in the
    lower section.

    Philosophy: the 35-point upper bonus is worth more than occasional lucky
    lower-section scores. Consistent high upper totals beat sporadic yahtzees.
    """

    def _next_upper(self, scorecard: 'Scorecard') -> Optional[str]:
        for cat in UPPER_CATS:
            if scorecard.scores[cat] is None:
                return cat
        return None

    def choose_keep(self, dice, roll_num, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return dice[:]
        target = self._next_upper(scorecard)
        if target:
            return _keep_for_category(target, dice)
        return _keep_for_category(_best_immediate(dice, scorecard), dice)

    def choose_category(self, dice, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return forced
        target = self._next_upper(scorecard)
        if target and target in scorecard.available:
            return target
        return _best_immediate(dice, scorecard)


# ── YahtzeeHunter ──────────────────────────────────────────────────────────────

class YahtzeeHunter(BaseStrategy):
    """
    Always keeps the most-frequent value, relentlessly chasing five-of-a-kind.
    Scores yahtzee as soon as it lands. After yahtzee is scored (or the slot
    is used up), falls back to the highest available lower category.
    Upper categories are taken only if nothing better is on offer.
    """

    def choose_keep(self, dice, roll_num, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return dice[:]
        # Always keep the most-frequent value
        counts = Counter(dice)
        most_val = counts.most_common(1)[0][0]
        return [d for d in dice if d == most_val]

    def choose_category(self, dice, scorecard):
        if len(set(dice)) == 1:
            # It's a yahtzee roll
            if scorecard.scores.get('yahtzee') is None:
                return 'yahtzee'
            return _apply_joker_priority(dice, scorecard)
        return _best_immediate(dice, scorecard)


# ── BalancedStrategy ───────────────────────────────────────────────────────────

class BalancedStrategy(BaseStrategy):
    """
    Adaptive strategy that weighs every available category by a combined score
    that accounts for:
      - Current dice proximity to scoring (potential, not just actual score)
      - Upper bonus urgency: boosts upper categories when the 63-pt bonus is
        still achievable but requires focus
      - Yahtzee bonus value: heavily boosts yahtzee when it is already scored
        (each extra yahtzee is worth +100)

    Unlike GreedyStrategy, BalancedStrategy will pursue a partial setup for
    a high-value category rather than bank a mediocre sure thing.
    """

    def _upper_deficit(self, scorecard: 'Scorecard') -> int:
        filled = sum(
            v for cat, v in scorecard.scores.items()
            if cat in UPPER_VALUES and v is not None
        )
        return max(0, UPPER_BONUS_THRESHOLD - filled)

    def _upper_remaining(self, scorecard: 'Scorecard') -> list[str]:
        return [c for c in UPPER_CATS if scorecard.scores[c] is None]

    def _bonus_feasible(self, scorecard: 'Scorecard') -> bool:
        remaining = self._upper_remaining(scorecard)
        if not remaining:
            return False
        deficit = self._upper_deficit(scorecard)
        max_possible = sum(UPPER_VALUES[c] * N_DICE for c in remaining)
        return max_possible >= deficit

    def _weight(self, category: str, dice: list[int], scorecard: 'Scorecard') -> float:
        base = _potential(category, dice)

        # Boost upper categories when bonus is feasible and there's urgency
        if category in UPPER_VALUES and self._bonus_feasible(scorecard):
            n_remain = len(self._upper_remaining(scorecard))
            deficit  = self._upper_deficit(scorecard)
            urgency  = min(2.5, deficit / (n_remain * UPPER_VALUES[category] + 1))
            base *= (1.0 + urgency)

        # Heavily boost yahtzee-hunting when bonus yahtzees are on the table
        if category == 'yahtzee' and scorecard.scores.get('yahtzee') == 50:
            base *= 4.0

        return base

    def choose_keep(self, dice, roll_num, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return dice[:]
        avail = scorecard.available
        if not avail:
            return dice[:]
        best = max(avail, key=lambda c: self._weight(c, dice, scorecard))
        return _keep_for_category(best, dice)

    def choose_category(self, dice, scorecard):
        forced = joker_forced_upper(dice, scorecard)
        if forced:
            return forced
        avail = scorecard.available
        return max(avail, key=lambda c: self._weight(c, dice, scorecard))
