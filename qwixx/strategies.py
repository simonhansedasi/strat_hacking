"""
Strategy interface and implementations for Qwixx.

BaseStrategy defines two hooks:

  choose_action1(white_sum, sheet, global_locked) -> str | None
    Return the color to cross white_sum in, or None to skip.
    Called for ALL players (active and non-active).

  choose_action2(options, sheet, global_locked) -> (str, int) | None
    Active player only. options is a list of (color, value) pairs that
    can legally be crossed via white+colored die. Return one to cross,
    or None to skip.

Strategies:
  RandomStrategy      — random valid choice; skips ~50% of the time
  AggressiveStrategy  — always cross; pick the rightmost (highest index) option
  ConservativeStrategy— only cross positions >= index 5 (right half of row)
  LockHunterStrategy  — focus on 1-2 leading rows; elsewhere only consecutive
  BalancedStrategy    — score each option by position progress minus gap penalty
"""
from __future__ import annotations
import random
from typing import Optional

from qwixx.game import COLORS, ROWS, Scoresheet


def _idx(color: str, value: int) -> int:
    return ROWS[color].index(value)


def _gap(sheet: Scoresheet, color: str, value: int) -> int:
    """Positions skipped over if we cross this value now."""
    return _idx(color, value) - sheet.rightmost_idx(color) - 1


class BaseStrategy:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def choose_action1(
        self, white_sum: int, sheet: Scoresheet, global_locked: dict[str, bool]
    ) -> Optional[str]:
        return None

    def choose_action2(
        self,
        options: list[tuple[str, int]],
        sheet: Scoresheet,
        global_locked: dict[str, bool],
    ) -> Optional[tuple[str, int]]:
        return None


class RandomStrategy(BaseStrategy):
    """Uniform random baseline; skips ~50% of the time even when moves exist."""

    def choose_action1(self, white_sum, sheet, global_locked):
        valid = sheet.valid_crosses(white_sum, global_locked)
        if not valid or self.rng.random() < 0.5:
            return None
        return self.rng.choice(valid)

    def choose_action2(self, options, sheet, global_locked):
        if not options or self.rng.random() < 0.5:
            return None
        return self.rng.choice(options)


class AggressiveStrategy(BaseStrategy):
    """Always cross when possible; among valid moves pick the rightmost position."""

    def _best_color(self, value: int, colors: list[str]) -> str:
        return max(colors, key=lambda c: _idx(c, value))

    def _best_option(self, options: list[tuple[str, int]]) -> tuple[str, int]:
        return max(options, key=lambda cv: _idx(cv[0], cv[1]))

    def choose_action1(self, white_sum, sheet, global_locked):
        valid = sheet.valid_crosses(white_sum, global_locked)
        return self._best_color(white_sum, valid) if valid else None

    def choose_action2(self, options, sheet, global_locked):
        return self._best_option(options) if options else None


class ConservativeStrategy(BaseStrategy):
    """
    Only crosses when the value falls in the right half of the row (index >= 5).
    Avoids committing to early positions that foreclose mid-row options.
    Among eligible moves, still picks the rightmost.
    """

    MIN_IDX = 5

    def choose_action1(self, white_sum, sheet, global_locked):
        valid = [c for c in sheet.valid_crosses(white_sum, global_locked)
                 if _idx(c, white_sum) >= self.MIN_IDX]
        if not valid:
            return None
        return max(valid, key=lambda c: _idx(c, white_sum))

    def choose_action2(self, options, sheet, global_locked):
        filtered = [(c, v) for c, v in options if _idx(c, v) >= self.MIN_IDX]
        if not filtered:
            return None
        return max(filtered, key=lambda cv: _idx(cv[0], cv[1]))


class LockHunterStrategy(BaseStrategy):
    """
    Identifies the 2 rows with the most crosses and pushes those hard.
    In other rows, only crosses the next consecutive position (gap == 0).
    """

    def _targets(self, sheet: Scoresheet) -> set[str]:
        ranked = sorted(COLORS, key=lambda c: -sheet.crosses_in_row(c))
        return set(ranked[:2])

    def _pick(self, sheet, pairs: list[tuple[str, int]]) -> Optional[tuple[str, int]]:
        targets = self._targets(sheet)
        in_target = [(c, v) for c, v in pairs if c in targets]
        if in_target:
            return max(in_target, key=lambda cv: _idx(cv[0], cv[1]))
        no_gap = [(c, v) for c, v in pairs if _gap(sheet, c, v) == 0]
        if no_gap:
            return max(no_gap, key=lambda cv: _idx(cv[0], cv[1]))
        return None

    def choose_action1(self, white_sum, sheet, global_locked):
        valid = sheet.valid_crosses(white_sum, global_locked)
        if not valid:
            return None
        result = self._pick(sheet, [(c, white_sum) for c in valid])
        return result[0] if result else None

    def choose_action2(self, options, sheet, global_locked):
        if not options:
            return None
        return self._pick(sheet, options)


class BalancedStrategy(BaseStrategy):
    """
    Scores each potential cross by position progress minus a gap penalty.
    Takes the highest-scoring option; skips if all options score below zero.
    """

    GAP_WEIGHT = 0.15

    def _score(self, sheet: Scoresheet, color: str, value: int) -> float:
        return _idx(color, value) / 10.0 - _gap(sheet, color, value) * self.GAP_WEIGHT

    def choose_action1(self, white_sum, sheet, global_locked):
        valid = sheet.valid_crosses(white_sum, global_locked)
        if not valid:
            return None
        return max(valid, key=lambda c: self._score(sheet, c, white_sum))

    def choose_action2(self, options, sheet, global_locked):
        if not options:
            return None
        return max(options, key=lambda cv: self._score(sheet, cv[0], cv[1]))
