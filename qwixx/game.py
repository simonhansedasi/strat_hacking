"""
Qwixx game mechanics.

4 color rows on the score sheet:
  red / yellow: numbers 2-12, crossed left to right (ascending)
  green / blue: numbers 12-2, crossed left to right (descending)

Each row has 11 number positions (indices 0-10) plus a lock slot.
The lock slot is earned when you cross the rightmost number (index 10)
after having >= 5 crosses already in that row. The lock cross counts
toward the triangular score.

Scoring: n crosses → n*(n+1)//2 points. Each penalty box = -5.

Game ends when any player reaches 4 penalties OR two rows are locked.
"""
from __future__ import annotations

COLORS = ['red', 'yellow', 'green', 'blue']

ROWS: dict[str, list[int]] = {
    'red':    list(range(2, 13)),
    'yellow': list(range(2, 13)),
    'green':  list(range(12, 1, -1)),
    'blue':   list(range(12, 1, -1)),
}

SCORE_TABLE = [n * (n + 1) // 2 for n in range(13)]  # index = n crosses
PENALTY_PTS  = -5
MAX_PENALTIES = 4


class Scoresheet:
    def __init__(self):
        self.crossed: dict[str, list[bool]] = {c: [False] * 11 for c in COLORS}
        self.lock_cross: dict[str, bool]    = {c: False for c in COLORS}
        self.penalties: int = 0

    def crosses_in_row(self, color: str) -> int:
        return sum(self.crossed[color]) + (1 if self.lock_cross[color] else 0)

    def rightmost_idx(self, color: str) -> int:
        """0-based index of rightmost crossed position, or -1 if none."""
        row = self.crossed[color]
        for i in range(10, -1, -1):
            if row[i]:
                return i
        return -1

    def can_cross(self, color: str, value: int, global_locked: dict[str, bool]) -> bool:
        if global_locked.get(color, False):
            return False
        row_vals = ROWS[color]
        if value not in row_vals:
            return False
        idx = row_vals.index(value)
        if idx <= self.rightmost_idx(color):
            return False
        # Crossing the last position requires 5+ prior crosses
        if idx == 10:
            return sum(self.crossed[color][:10]) >= 5
        return True

    def cross(self, color: str, value: int) -> bool:
        """Mark value as crossed. Returns True if this locks the row."""
        idx = ROWS[color].index(value)
        self.crossed[color][idx] = True
        if idx == 10:
            self.lock_cross[color] = True
            return True
        return False

    def valid_crosses(self, value: int, global_locked: dict[str, bool]) -> list[str]:
        """Colors where value can be legally crossed right now."""
        return [c for c in COLORS if self.can_cross(c, value, global_locked)]

    def row_score(self, color: str) -> int:
        return SCORE_TABLE[self.crosses_in_row(color)]

    @property
    def total(self) -> int:
        return sum(self.row_score(c) for c in COLORS) + self.penalties * PENALTY_PTS

    @property
    def is_busted(self) -> bool:
        return self.penalties >= MAX_PENALTIES
