"""
Yahtzee game mechanics and scorecard.

Turn structure: roll up to 3 times; keep any dice between rolls; score one category.
13 categories total; 35-point upper bonus if ones–sixes sum >= 63;
+100 yahtzee bonus each time a yahtzee is rolled when yahtzee slot already holds 50.

Joker rules (for bonus yahtzees):
  1. Must score the matching upper category if it is open.
  2. Otherwise may score any lower category (full house / straights yield fixed pts).
  3. Otherwise must score any open upper category (likely 0).
"""
from __future__ import annotations
from collections import Counter
from typing import Optional
import random

CATEGORIES = [
    'ones', 'twos', 'threes', 'fours', 'fives', 'sixes',
    'three_of_a_kind', 'four_of_a_kind', 'full_house',
    'small_straight', 'large_straight', 'yahtzee', 'chance',
]

UPPER_CATS   = CATEGORIES[:6]
UPPER_VALUES = {cat: i + 1 for i, cat in enumerate(UPPER_CATS)}  # ones->1, ..., sixes->6

UPPER_BONUS_THRESHOLD = 63
UPPER_BONUS           = 35
YAHTZEE_BONUS         = 100
N_DICE                = 5
MAX_ROLLS             = 3

# Theoretical max score for each category (used for normalisation in strategies)
MAX_SCORE = {
    'ones': 5, 'twos': 10, 'threes': 15, 'fours': 20, 'fives': 25, 'sixes': 30,
    'three_of_a_kind': 30, 'four_of_a_kind': 30, 'full_house': 25,
    'small_straight': 30, 'large_straight': 40, 'yahtzee': 50, 'chance': 30,
}


def roll_dice(n: int, rng: random.Random) -> list[int]:
    return [rng.randint(1, 6) for _ in range(n)]


def possible_score(category: str, dice: list[int]) -> int:
    """Points earned for this category with these dice, ignoring joker rules."""
    counts = Counter(dice)
    if category in UPPER_VALUES:
        return sum(d for d in dice if d == UPPER_VALUES[category])
    if category == 'three_of_a_kind':
        return sum(dice) if max(counts.values()) >= 3 else 0
    if category == 'four_of_a_kind':
        return sum(dice) if max(counts.values()) >= 4 else 0
    if category == 'full_house':
        return 25 if sorted(counts.values()) == [2, 3] else 0
    if category == 'small_straight':
        u = set(dice)
        return 30 if any(s <= u for s in ({1, 2, 3, 4}, {2, 3, 4, 5}, {3, 4, 5, 6})) else 0
    if category == 'large_straight':
        return 40 if set(dice) in ({1, 2, 3, 4, 5}, {2, 3, 4, 5, 6}) else 0
    if category == 'yahtzee':
        return 50 if len(counts) == 1 else 0
    if category == 'chance':
        return sum(dice)
    return 0


def joker_forced_upper(dice: list[int], scorecard: 'Scorecard') -> Optional[str]:
    """
    Under joker rules, if dice are a yahtzee and yahtzee slot already holds 50,
    the player must score the matching upper category if it is still open.
    Returns that category name, or None if no upper category is forced.
    """
    if len(set(dice)) == 1 and scorecard.scores.get('yahtzee') == 50:
        cat = UPPER_CATS[dice[0] - 1]
        if scorecard.scores[cat] is None:
            return cat
    return None


class Scorecard:
    def __init__(self):
        self.scores: dict[str, Optional[int]] = {cat: None for cat in CATEGORIES}
        self.yahtzee_bonuses: int = 0

    @property
    def available(self) -> list[str]:
        return [cat for cat, v in self.scores.items() if v is None]

    @property
    def is_complete(self) -> bool:
        return not self.available

    @property
    def upper_total(self) -> int:
        return sum(
            v for cat, v in self.scores.items()
            if cat in UPPER_VALUES and v is not None
        )

    @property
    def got_upper_bonus(self) -> bool:
        return self.upper_total >= UPPER_BONUS_THRESHOLD

    @property
    def total(self) -> int:
        raw   = sum(v for v in self.scores.values() if v is not None)
        bonus = UPPER_BONUS if self.got_upper_bonus else 0
        return raw + bonus + self.yahtzee_bonuses * YAHTZEE_BONUS

    def score_category(self, category: str, dice: list[int]) -> int:
        """
        Score the given category with these dice and record it.
        Applies yahtzee bonus and joker scoring for full house / straights.
        Returns points earned this scoring action (excluding accumulated bonuses).
        """
        assert self.scores[category] is None, f"{category} already scored"

        is_yz = len(set(dice)) == 1

        if is_yz and self.scores.get('yahtzee') == 50:
            self.yahtzee_bonuses += 1
            # Joker: full house and straights always score their fixed value
            joker_fixed = {'full_house': 25, 'small_straight': 30, 'large_straight': 40}
            if category in joker_fixed:
                self.scores[category] = joker_fixed[category]
                return joker_fixed[category]

        pts = possible_score(category, dice)
        self.scores[category] = pts
        return pts
