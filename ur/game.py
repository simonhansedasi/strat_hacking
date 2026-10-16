"""
Royal Game of Ur — board mechanics.

Path: 14 squares per player (positions 1-14).
  1-4:   private start zone  (no capture; physically separate per player)
  5-12:  shared zone         (capture possible)
  13-14: private exit zone   (no capture; physically separate per player)
  0:     off board, waiting to enter
  15:    borne off (done)

Pieces enter at position = roll (e.g. roll 3 → enter at position 3).
Bearing off: destination must equal exactly BEAR_OFF (15). From position 14,
need roll 1; from position 11, need roll 4; positions < 11 cannot bear off.

Rosettes at positions 4, 8, 14 → extra turn on landing.
Position 8 is the SAFE ROSETTE: opponent cannot land there to capture you.

Dice: 4 binary tokens, each 0 or 1 with equal probability → sum 0-4.
  P(0)=1/16  P(1)=4/16  P(2)=6/16  P(3)=4/16  P(4)=1/16
"""
from __future__ import annotations
import random

PIECES_PER_PLAYER = 7
BEAR_OFF = 15
ROSETTES = frozenset({4, 8, 14})
SAFE_ROSETTE = 8
SHARED_ZONE = frozenset(range(5, 13))


def roll_dice(rng: random.Random) -> int:
    return sum(rng.randint(0, 1) for _ in range(4))


class GameState:
    __slots__ = ("pieces", "current")

    def __init__(self) -> None:
        self.pieces: list[list[int]] = [
            [0] * PIECES_PER_PLAYER,
            [0] * PIECES_PER_PLAYER,
        ]
        self.current: int = 0

    def copy(self) -> "GameState":
        gs = GameState()
        gs.pieces = [list(self.pieces[0]), list(self.pieces[1])]
        gs.current = self.current
        return gs

    def _occupied(self, player: int) -> set[int]:
        return {p for p in self.pieces[player] if 0 < p < BEAR_OFF}

    def valid_moves(self, player: int, roll: int) -> list[int]:
        """Return piece indices that can legally move with this roll."""
        if roll == 0:
            return []
        opp = 1 - player
        own_pos = self._occupied(player)
        opp_pos = self._occupied(opp)
        valid = []
        for i, pos in enumerate(self.pieces[player]):
            if pos == BEAR_OFF:
                continue
            dest = pos + roll
            if dest > BEAR_OFF:
                continue  # too far; exact roll required to exit
            if dest == BEAR_OFF:
                valid.append(i)
                continue
            # dest in 1-14: normal move
            if dest in own_pos:
                continue
            if dest == SAFE_ROSETTE and dest in opp_pos:
                continue  # safe rosette is occupied by opponent; can't enter
            valid.append(i)
        return valid

    def apply_move(self, player: int, piece_idx: int, roll: int) -> bool:
        """Move piece in-place. Returns True if player earns an extra turn."""
        opp = 1 - player
        dest = self.pieces[player][piece_idx] + roll
        self.pieces[player][piece_idx] = dest
        if dest == BEAR_OFF:
            return False
        if dest in SHARED_ZONE and dest != SAFE_ROSETTE:
            for j in range(PIECES_PER_PLAYER):
                if self.pieces[opp][j] == dest:
                    self.pieces[opp][j] = 0
                    break
        return dest in ROSETTES

    def is_over(self) -> bool:
        return (
            all(p == BEAR_OFF for p in self.pieces[0])
            or all(p == BEAR_OFF for p in self.pieces[1])
        )

    def winner(self) -> int:
        if all(p == BEAR_OFF for p in self.pieces[0]):
            return 0
        if all(p == BEAR_OFF for p in self.pieces[1]):
            return 1
        return -1
