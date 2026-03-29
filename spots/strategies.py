"""
Strategy interface and implementations for Spots.

BaseStrategy defines the full interface (all methods tricks.py calls).
Concrete strategies override selectively.

Methods:
  choose_trick(player, tricks)          -> trick dict
  assign_die(die, player)               -> DogCard or None
  should_continue(player, dice_so_far, trick) -> bool
  choose_value(roll, player)            -> int
  choose_dice_subset(roll, player, keep_n) -> list[int]
  should_discard_die(die, player)       -> bool
  choose_dice_subset_sum(roll, player, target_sum) -> list[int]
  should_reroll(roll, player)           -> bool
  trot_move(player)                     -> None
  dig_target(player)                    -> (idx, delta)
  dogpile_take(player)                  -> int or None
"""
from __future__ import annotations
import random
from itertools import combinations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from spots.game import PlayerState, DogCard


class BaseStrategy:
    """Abstract base — all methods have safe no-op / random defaults."""

    def choose_trick(self, player: 'PlayerState', tricks: list[dict]) -> dict:
        raise NotImplementedError

    def assign_die(self, die: int, player: 'PlayerState') -> Optional['DogCard']:
        """Which dog gets this die? Return None to bury instead."""
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        return candidates[0]

    def should_continue(self, player: 'PlayerState', dice_so_far: int, trick: str) -> bool:
        return False

    def choose_value(self, roll: list[int], player: 'PlayerState') -> int:
        """Pick a die value (fetch: from roll; guard: pre-roll naming)."""
        if roll:
            return max(set(roll), key=roll.count)
        return 3  # safe-ish default for guard

    def choose_dice_subset(self, roll: list[int], player: 'PlayerState',
                           keep_n: Optional[int]) -> list[int]:
        """Keep keep_n dice (or all if keep_n is None)."""
        if keep_n is None:
            return list(roll)
        return list(roll[:keep_n])

    def should_discard_die(self, die: int, player: 'PlayerState') -> bool:
        return False

    def choose_dice_subset_sum(self, roll: list[int], player: 'PlayerState',
                               target_sum: int) -> list[int]:
        """Find a subset of roll that sums to target_sum (greedy: largest first)."""
        for size in range(len(roll), 0, -1):
            for combo in combinations(sorted(roll, reverse=True), size):
                if sum(combo) == target_sum:
                    return list(combo)
        return []

    def should_reroll(self, roll: list[int], player: 'PlayerState') -> bool:
        return False

    def trot_move(self, player: 'PlayerState') -> None:
        pass  # no move by default

    def dig_target(self, player: 'PlayerState') -> tuple[Optional[int], int]:
        """Return (yard_index, delta). delta=+1 raises, -1 lowers."""
        return (None, 0)

    def dogpile_take(self, player: 'PlayerState') -> Optional[int]:
        """Remove and return a die value from yard or dogs. None = stop."""
        if player.yard:
            return player.yard.pop(0)
        for dog in player.dogs:
            for i, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    dog.filled[i] = False
                    return v
        return None


# ── Random strategy ───────────────────────────────────────────────────────────

class RandomStrategy(BaseStrategy):
    """All decisions made uniformly at random."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def choose_trick(self, player: 'PlayerState', tricks: list[dict]) -> dict:
        face_up = [t for t in tricks if t['face_up']]
        return self.rng.choice(face_up)

    def assign_die(self, die: int, player: 'PlayerState') -> Optional['DogCard']:
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        return self.rng.choice(candidates)

    def should_continue(self, player: 'PlayerState', dice_so_far: int, trick: str) -> bool:
        return self.rng.random() < 0.5

    def choose_value(self, roll: list[int], player: 'PlayerState') -> int:
        if roll:
            return self.rng.choice(roll)
        return self.rng.randint(1, 6)

    def choose_dice_subset(self, roll: list[int], player: 'PlayerState',
                           keep_n: Optional[int]) -> list[int]:
        if keep_n is None:
            return list(roll)
        shuffled = list(roll)
        self.rng.shuffle(shuffled)
        return shuffled[:keep_n]

    def should_discard_die(self, die: int, player: 'PlayerState') -> bool:
        return self.rng.random() < 0.5

    def should_reroll(self, roll: list[int], player: 'PlayerState') -> bool:
        return self.rng.random() < 0.4

    def trot_move(self, player: 'PlayerState') -> None:
        # Randomly move a filled die from one dog to another compatible dog
        sources = [(d, i, v) for d in player.dogs
                   for i, (v, f) in enumerate(zip(d.spaces, d.filled)) if f]
        if not sources:
            return
        src_dog, src_idx, val = self.rng.choice(sources)
        targets = [d for d in player.incomplete_dogs
                   if d is not src_dog and d.can_accept(val)]
        if targets:
            src_dog.filled[src_idx] = False
            self.rng.choice(targets).place(val)

    def dig_target(self, player: 'PlayerState') -> tuple[Optional[int], int]:
        if not player.yard:
            return (None, 0)
        return (self.rng.randint(0, len(player.yard) - 1),
                self.rng.choice([-1, 1]))

    def dogpile_take(self, player: 'PlayerState') -> Optional[int]:
        options = []
        if player.yard:
            options.append(('yard', None))
        for di, dog in enumerate(player.dogs):
            for si, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    options.append(('dog', (di, si, v)))
        if not options:
            return None
        choice = self.rng.choice(options)
        if choice[0] == 'yard':
            return player.yard.pop(self.rng.randint(0, len(player.yard) - 1))
        _, (di, si, v) = choice
        player.dogs[di].filled[si] = False
        return v


# ── Greedy strategy ───────────────────────────────────────────────────────────

class GreedyStrategy(BaseStrategy):
    """
    Maximise expected placed dice each turn.

    - Prefers tricks that roll more dice.
    - Assigns dice to the dog closest to completion (fewest open spaces left).
    - Continues rolling as long as bust probability stays below threshold.
    - Rerolls if current roll has more misses than expected average.
    """

    CONTINUE_BUST_THRESHOLD = 0.25   # stop if estimated bust prob > this

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._trick_preference = {
            'run': 10, 'sprint': 9, 'chase': 8, 'bolt': 7, 'dogpile': 6,
            'fetch': 8, 'hunt': 7, 'guard': 6, 'scavenge': 5, 'search': 4,
            'walk': 6, 'track': 5, 'trot': 5, 'retrieve': 4, 'dig': 4,
            'beg': 3, 'chew': 3, 'gobble': 3, 'play_dead': 2, 'stay': 1,
            'howl': 2, 'roll_over': 3,
        }

    def choose_trick(self, player: 'PlayerState', tricks: list[dict]) -> dict:
        face_up = [t for t in tricks if t['face_up']]
        return max(face_up, key=lambda t: self._trick_preference.get(t['fn'].__name__, 0))

    def assign_die(self, die: int, player: 'PlayerState') -> Optional['DogCard']:
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        # Prefer dog with fewest open spaces (closest to complete)
        return min(candidates, key=lambda d: len(d.open_spaces))

    def should_continue(self, player: 'PlayerState', dice_so_far: int, trick: str) -> bool:
        # Simple heuristic: continue if yard is low and we have open spaces
        if player.yard_total >= 5:
            return False
        if not player.all_open_spaces():
            return False
        return dice_so_far < 6

    def choose_value(self, roll: list[int], player: 'PlayerState') -> int:
        open_spaces = player.all_open_spaces()
        if roll and open_spaces:
            # Pick the value in roll that matches the most open spaces
            best = max(set(roll), key=lambda v: (open_spaces.count(v), -v))
            return best
        if roll:
            return max(set(roll), key=roll.count)
        # guard pre-roll: name the value we need most
        if open_spaces:
            from collections import Counter
            return Counter(open_spaces).most_common(1)[0][0]
        return 3

    def choose_dice_subset(self, roll: list[int], player: 'PlayerState',
                           keep_n: Optional[int]) -> list[int]:
        open_spaces = player.all_open_spaces()
        # Sort: placeable dice first, then by value descending
        scored = sorted(roll, key=lambda d: (d not in open_spaces, -d))
        if keep_n is None:
            return scored
        return scored[:keep_n]

    def should_discard_die(self, die: int, player: 'PlayerState') -> bool:
        # Discard if burying it would bring yard total close to bust
        return player.yard_total + die > 5

    def should_reroll(self, roll: list[int], player: 'PlayerState') -> bool:
        if player.treats <= 0:
            return False
        open_spaces = player.all_open_spaces()
        misses = sum(1 for d in roll if d not in open_spaces)
        return misses > len(roll) / 2

    def trot_move(self, player: 'PlayerState') -> None:
        # Move a die from a nearly-complete dog that can't finish to one that can
        for src_dog in sorted(player.dogs, key=lambda d: len(d.open_spaces), reverse=True):
            for i, (v, f) in enumerate(zip(src_dog.spaces, src_dog.filled)):
                if f:
                    targets = [d for d in player.incomplete_dogs
                               if d is not src_dog and d.can_accept(v)]
                    if targets:
                        src_dog.filled[i] = False
                        min(targets, key=lambda d: len(d.open_spaces)).place(v)
                        return

    def dig_target(self, player: 'PlayerState') -> tuple[Optional[int], int]:
        if not player.yard:
            return (None, 0)
        open_spaces = player.all_open_spaces()
        # Try to adjust a buried die to match an open space
        for target_val in open_spaces:
            for idx, buried in enumerate(player.yard):
                if abs(buried - target_val) == 1:
                    return (idx, target_val - buried)
        # Otherwise lower the highest buried die
        highest_idx = max(range(len(player.yard)), key=lambda i: player.yard[i])
        return (highest_idx, -1)

    def dogpile_take(self, player: 'PlayerState') -> Optional[int]:
        # Take highest buried die from yard; fall back to a filled space
        if player.yard:
            idx = max(range(len(player.yard)), key=lambda i: player.yard[i])
            return player.yard.pop(idx)
        for dog in sorted(player.dogs, key=lambda d: len(d.open_spaces), reverse=True):
            for i, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    dog.filled[i] = False
                    return v
        return None


# ── Conservative strategy ─────────────────────────────────────────────────────

class ConservativeStrategy(BaseStrategy):
    """
    Minimise bust risk.

    - Prefers safe tricks (treat-gaining, few dice).
    - Stops rolling early.
    - Never rerolls unless roll is a total disaster.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._trick_preference = {
            'beg': 10, 'chew': 9, 'stay': 8, 'gobble': 7, 'play_dead': 6,
            'roll_over': 5, 'howl': 4,
            'fetch': 5, 'guard': 4, 'hunt': 3, 'search': 2, 'scavenge': 3,
            'walk': 4, 'track': 3, 'trot': 3, 'retrieve': 3, 'dig': 2,
            'run': 2, 'sprint': 1, 'chase': 1, 'bolt': 1, 'dogpile': 1,
        }

    def choose_trick(self, player: 'PlayerState', tricks: list[dict]) -> dict:
        face_up = [t for t in tricks if t['face_up']]
        return max(face_up, key=lambda t: self._trick_preference.get(t['fn'].__name__, 0))

    def assign_die(self, die: int, player: 'PlayerState') -> Optional['DogCard']:
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        return min(candidates, key=lambda d: len(d.open_spaces))

    def should_continue(self, player: 'PlayerState', dice_so_far: int, trick: str) -> bool:
        return False  # always stop at minimum

    def choose_value(self, roll: list[int], player: 'PlayerState') -> int:
        open_spaces = player.all_open_spaces()
        if roll and open_spaces:
            matches = [v for v in roll if v in open_spaces]
            if matches:
                return max(set(matches), key=matches.count)
        if roll:
            return min(roll)  # bury the smallest if no match
        if open_spaces:
            from collections import Counter
            return Counter(open_spaces).most_common(1)[0][0]
        return 1

    def choose_dice_subset(self, roll: list[int], player: 'PlayerState',
                           keep_n: Optional[int]) -> list[int]:
        open_spaces = player.all_open_spaces()
        placeable = [d for d in roll if d in open_spaces]
        non_placeable = [d for d in roll if d not in open_spaces]
        kept = (placeable + non_placeable)
        if keep_n is None:
            return kept
        return kept[:keep_n]

    def should_discard_die(self, die: int, player: 'PlayerState') -> bool:
        return player.yard_total + die > 4  # very conservative

    def choose_dice_subset_sum(self, roll: list[int], player: 'PlayerState',
                               target_sum: int) -> list[int]:
        for size in range(len(roll), 0, -1):
            for combo in combinations(sorted(roll, reverse=True), size):
                if sum(combo) == target_sum:
                    return list(combo)
        return []

    def should_reroll(self, roll: list[int], player: 'PlayerState') -> bool:
        if player.treats <= 0:
            return False
        open_spaces = player.all_open_spaces()
        # Only reroll if every die is a miss
        return all(d not in open_spaces for d in roll)

    def trot_move(self, player: 'PlayerState') -> None:
        pass  # don't move dice around

    def dig_target(self, player: 'PlayerState') -> tuple[Optional[int], int]:
        if not player.yard:
            return (None, 0)
        # Lower the highest die to reduce bust risk
        highest_idx = max(range(len(player.yard)), key=lambda i: player.yard[i])
        return (highest_idx, -1)

    def dogpile_take(self, player: 'PlayerState') -> Optional[int]:
        return None  # never use dogpile
