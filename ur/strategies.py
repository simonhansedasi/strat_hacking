"""
Strategy interface and implementations for the Royal Game of Ur.

All strategies decide: given a list of piece indices that can legally move,
which one to move?

BaseStrategy.choose_move(valid_pieces, state, player, roll) -> int

Strategies:
  RandomStrategy       — uniform random choice; baseline
  ProgressStrategy     — always move the piece farthest along the path
  SafeStrategy         — prefer rosettes and private zones over shared zone exposure
  AggressiveStrategy   — prioritise captures, then rosettes, then progress
  RosetteHunterStrategy— strongly prefer moves that land on a rosette
  BalancedStrategy     — weighted EV: progress + capture bonus + rosette bonus
                         minus vulnerability penalty for landing in shared zone
                         where the opponent can reach next turn
"""
from __future__ import annotations
import random

from ur.game import GameState, BEAR_OFF, ROSETTES, SAFE_ROSETTE, SHARED_ZONE


class BaseStrategy:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def choose_move(
        self, valid_pieces: list[int], state: GameState, player: int, roll: int
    ) -> int:
        raise NotImplementedError


class RandomStrategy(BaseStrategy):
    def choose_move(self, valid_pieces, state, player, roll):
        return self.rng.choice(valid_pieces)


class ProgressStrategy(BaseStrategy):
    """Move the piece that is farthest along (highest position)."""

    def choose_move(self, valid_pieces, state, player, roll):
        return max(valid_pieces, key=lambda i: state.pieces[player][i])


class SafeStrategy(BaseStrategy):
    """
    Prefer destinations that are safe from capture:
      bear off > rosettes > private zones > shared zone.
    Within shared zone, prefer the safe rosette (pos 8) if reachable.
    Tiebreak by progress (destination position).
    """

    def choose_move(self, valid_pieces, state, player, roll):
        def score(i):
            dest = state.pieces[player][i] + roll
            if dest == BEAR_OFF:
                return 1000
            if dest in ROSETTES:
                return 500 + dest
            if dest not in SHARED_ZONE:
                return 200 + dest  # private zone
            return dest  # shared zone: only raw progress

        return max(valid_pieces, key=score)


class AggressiveStrategy(BaseStrategy):
    """
    Priority: capture opponent > land on rosette > bear off > progress.
    """

    def choose_move(self, valid_pieces, state, player, roll):
        opp = 1 - player
        opp_pos = {p for p in state.pieces[opp] if 0 < p < BEAR_OFF}

        def score(i):
            dest = state.pieces[player][i] + roll
            if dest == BEAR_OFF:
                return 800
            capture = dest in opp_pos and dest in SHARED_ZONE and dest != SAFE_ROSETTE
            rosette = dest in ROSETTES
            return 1000 * capture + 400 * rosette + dest

        return max(valid_pieces, key=score)


class RosetteHunterStrategy(BaseStrategy):
    """
    Rosettes mean extra turns, which compound. Pursue them aggressively.
    If no rosette available, advance the furthest piece.
    """

    def choose_move(self, valid_pieces, state, player, roll):
        def score(i):
            dest = state.pieces[player][i] + roll
            if dest == BEAR_OFF:
                return 2000
            if dest in ROSETTES:
                return 1000 + dest
            return dest

        return max(valid_pieces, key=score)


class BalancedStrategy(BaseStrategy):
    """
    Weighted EV scoring per candidate move:
      +2 * destination (progress)
      +60 for capturing an opponent piece
      +40 for landing on a rosette (extra turn)
      -25 if landing in shared zone where opponent can reach next turn
      +8  if moving a piece OUT of a threatened shared-zone square
    """

    def choose_move(self, valid_pieces, state, player, roll):
        opp = 1 - player
        opp_pos = {p for p in state.pieces[opp] if 0 < p < BEAR_OFF}

        # squares the opponent can threaten on their next turn (rolls 1-4)
        opp_threats: set[int] = set()
        for op in opp_pos:
            for r in range(1, 5):
                t = op + r
                if t in SHARED_ZONE and t != SAFE_ROSETTE:
                    opp_threats.add(t)

        def score(i):
            src = state.pieces[player][i]
            dest = src + roll
            if dest == BEAR_OFF:
                return 2000.0
            s = 2.0 * dest
            if dest in ROSETTES:
                s += 40.0
            if dest in opp_pos and dest in SHARED_ZONE and dest != SAFE_ROSETTE:
                s += 60.0  # capture
            if dest in SHARED_ZONE and dest != SAFE_ROSETTE and dest in opp_threats:
                s -= 25.0  # landing vulnerable
            if src in SHARED_ZONE and src != SAFE_ROSETTE and src in opp_threats:
                s += 8.0   # moving out of a threatened square
            return s

        return max(valid_pieces, key=score)
