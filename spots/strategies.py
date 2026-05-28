"""
Strategy interface and implementations for Spots.

BaseStrategy defines the full interface (all methods tricks.py calls).

Strategies explore distinct axes:

  OneAtATimeStrategy  — complete one dog before touching the next; avoid Howl
  FullPackStrategy    — rush to 6 dogs via Howl; spread dice to maximise placement
                        surface; exploit Sprint
  TreatGamblerStrategy— accumulate treats until flush, then burn them on rolling
                        streaks with aggressive rerolls
  FastAndLooseStrategy— always roll more dice; accept bust as the cost of speed
  BustAwareStrategy   — uses exact bust probability math to decide when to stop

  RandomStrategy      — uniform random baseline
"""
from __future__ import annotations
import random
from collections import Counter
from itertools import combinations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from spots.game import PlayerState, DogCard


# ── Shared helpers ────────────────────────────────────────────────────────────

def _best_subset_sum(roll: list[int], target: int) -> list[int]:
    """Largest subset of roll that sums to target, empty if impossible."""
    for size in range(len(roll), 0, -1):
        for combo in combinations(sorted(roll, reverse=True), size):
            if sum(combo) == target:
                return list(combo)
    return []


def _bust_prob(yard_total: int, open_spaces: list[int], n_dice: int = 1) -> float:
    """Estimated P(bust) rolling n_dice given current yard and placement options."""
    try:
        from spots.prob import bust_prob_with_placement
        return bust_prob_with_placement(yard_total, n_dice, open_spaces)
    except Exception:
        # Fallback: rough linear estimate
        threshold = 7 - yard_total
        if threshold <= 0:
            return 1.0
        return max(0.0, min(1.0, n_dice / (threshold + 1)))


def _trick_pref(face_up: list[dict], scores: dict[str, float]) -> dict:
    """Pick the highest-scoring face-up trick by function name."""
    return max(face_up, key=lambda t: scores.get(t['fn'].__name__, 0.0))


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseStrategy:
    """All methods have safe defaults; concrete strategies override selectively."""

    def choose_trick(self, player: 'PlayerState', tricks: list[dict]) -> dict:
        raise NotImplementedError

    def assign_die(self, die: int, player: 'PlayerState') -> Optional['DogCard']:
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        return candidates[0] if candidates else None

    def should_continue(self, player: 'PlayerState', dice_so_far: int, trick: str) -> bool:
        return False

    def choose_value(self, roll: list[int], player: 'PlayerState') -> int:
        open_spaces = player.all_open_spaces()
        if roll and open_spaces:
            return max(set(roll), key=lambda v: (open_spaces.count(v), -v))
        return max(set(roll), key=roll.count) if roll else 3

    def choose_dice_subset(self, roll: list[int], player: 'PlayerState',
                           keep_n: Optional[int]) -> list[int]:
        if keep_n is None:
            return list(roll)
        return list(roll[:keep_n])

    def should_discard_die(self, die: int, player: 'PlayerState') -> bool:
        return False

    def choose_dice_subset_sum(self, roll: list[int], player: 'PlayerState',
                               target_sum: int) -> list[int]:
        return _best_subset_sum(roll, target_sum)

    def should_reroll(self, roll: list[int], player: 'PlayerState') -> bool:
        return False

    def trot_move(self, player: 'PlayerState') -> None:
        pass

    def dig_target(self, player: 'PlayerState') -> tuple[Optional[int], int]:
        return (None, 0)

    def dogpile_take(self, player: 'PlayerState') -> Optional[int]:
        if player.yard:
            return player.yard.pop(0)
        for dog in player.dogs:
            for i, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    dog.filled[i] = False
                    return v
        return None


# ── Random baseline ───────────────────────────────────────────────────────────

class RandomStrategy(BaseStrategy):
    """Uniform random on every decision. Baseline only."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def choose_trick(self, player, tricks):
        return self.rng.choice([t for t in tricks if t['face_up']])

    def assign_die(self, die, player):
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        return self.rng.choice(candidates) if candidates else None

    def should_continue(self, player, dice_so_far, trick):
        return self.rng.random() < 0.4

    def choose_value(self, roll, player):
        return self.rng.choice(roll) if roll else self.rng.randint(1, 6)

    def choose_dice_subset(self, roll, player, keep_n):
        if keep_n is None:
            return list(roll)
        s = list(roll); self.rng.shuffle(s)
        return s[:keep_n]

    def should_discard_die(self, die, player):
        return self.rng.random() < 0.5

    def should_reroll(self, roll, player):
        return player.treats > 0 and self.rng.random() < 0.3

    def trot_move(self, player):
        sources = [(d, i, v) for d in player.dogs
                   for i, (v, f) in enumerate(zip(d.spaces, d.filled)) if f]
        if not sources:
            return
        src, idx, val = self.rng.choice(sources)
        targets = [d for d in player.incomplete_dogs if d is not src and d.can_accept(val)]
        if targets:
            src.filled[idx] = False
            self.rng.choice(targets).place(val)

    def dig_target(self, player):
        if not player.yard:
            return (None, 0)
        return (self.rng.randint(0, len(player.yard) - 1), self.rng.choice([-1, 1]))

    def dogpile_take(self, player):
        opts = []
        if player.yard:
            opts += [('yard', i) for i in range(len(player.yard))]
        for di, dog in enumerate(player.dogs):
            for si, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    opts.append(('dog', (di, si)))
        if not opts:
            return None
        kind, ref = self.rng.choice(opts)
        if kind == 'yard':
            return player.yard.pop(ref)
        di, si = ref
        player.dogs[di].filled[si] = False
        return player.dogs[di].spaces[si]


# ── OneAtATime ────────────────────────────────────────────────────────────────

class OneAtATimeStrategy(BaseStrategy):
    """
    Complete one dog fully before touching the next.

    assign_die: always give the die to whichever dog is closest to completion
                (fewest open spaces remaining). Ties broken by sum of remaining
                needs — prefer the dog that's cheapest to finish.

    Avoids Howl: more dogs = more dice committed to incomplete slots.
    Should_continue: stop once yard is risky (uses bust probability).
    """

    BUST_STOP = 0.20   # stop rolling if P(bust on next die) exceeds this

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._prefs = {
            'sprint': 9, 'run': 8, 'chase': 7, 'walk': 7,
            'fetch': 7, 'hunt': 6, 'guard': 6, 'track': 6,
            'trot': 5, 'retrieve': 5, 'dig': 5, 'scavenge': 5, 'search': 4,
            'roll_over': 4, 'bolt': 4, 'dogpile': 3,
            'beg': 2, 'chew': 2, 'gobble': 2, 'play_dead': 2, 'stay': 1,
            'howl': 0,   # actively avoid
        }

    def choose_trick(self, player, tricks):
        return _trick_pref([t for t in tricks if t['face_up']], self._prefs)

    def assign_die(self, die, player):
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        # Closest to done first; break ties by cheapest remaining need sum
        return min(candidates, key=lambda d: (len(d.open_spaces), sum(d.open_spaces)))

    def should_continue(self, player, dice_so_far, trick):
        if not player.all_open_spaces():
            return False
        p = _bust_prob(player.yard_total, player.all_open_spaces(), n_dice=1)
        return p < self.BUST_STOP

    def choose_dice_subset(self, roll, player, keep_n):
        open_s = player.all_open_spaces()
        ranked = sorted(roll, key=lambda d: (d not in open_s, -d))
        return ranked if keep_n is None else ranked[:keep_n]

    def should_discard_die(self, die, player):
        return player.yard_total + die > 5

    def should_reroll(self, roll, player):
        if player.treats <= 0:
            return False
        open_s = player.all_open_spaces()
        misses = sum(1 for d in roll if d not in open_s)
        return misses > len(roll) // 2

    def dig_target(self, player):
        if not player.yard:
            return (None, 0)
        open_s = player.all_open_spaces()
        for target in open_s:
            for idx, b in enumerate(player.yard):
                if abs(b - target) == 1:
                    return (idx, target - b)
        return (max(range(len(player.yard)), key=lambda i: player.yard[i]), -1)

    def dogpile_take(self, player):
        if player.yard:
            return player.yard.pop(max(range(len(player.yard)),
                                       key=lambda i: player.yard[i]))
        for dog in sorted(player.dogs, key=lambda d: len(d.open_spaces), reverse=True):
            for i, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    dog.filled[i] = False
                    return v
        return None


# ── FullPack ──────────────────────────────────────────────────────────────────

class FullPackStrategy(BaseStrategy):
    """
    Maintain 6 dogs at all times to maximise placement surface area.

    assign_die: give each die to the dog with the MOST open spaces — spread
                progress evenly so every die value is absorbable for as long
                as possible. This minimises the chance any single die has to
                be buried.

    Howl is top priority. Sprint is best rolling trick (scales with dog count).
    Will continue rolling aggressively because many open spaces = low bust risk.
    """

    BUST_STOP = 0.30   # more tolerant of risk because coverage is high

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._prefs = {
            'howl': 10,
            'sprint': 9, 'run': 8, 'chase': 7, 'bolt': 6,
            'fetch': 7, 'hunt': 6, 'guard': 5,
            'walk': 6, 'trot': 5, 'retrieve': 5, 'track': 4, 'dig': 4,
            'roll_over': 4, 'scavenge': 4, 'search': 3, 'dogpile': 3,
            'beg': 2, 'chew': 2, 'gobble': 2, 'play_dead': 1, 'stay': 1,
        }

    def choose_trick(self, player, tricks):
        return _trick_pref([t for t in tricks if t['face_up']], self._prefs)

    def assign_die(self, die, player):
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        # Spread: give die to the dog with the most open spaces (furthest from done)
        # Tie-break: prefer dog whose remaining needs include the highest values
        # (keeps high-value dogs absorbing dangerous dice longer)
        return max(candidates, key=lambda d: (len(d.open_spaces), max(d.open_spaces)))

    def should_continue(self, player, dice_so_far, trick):
        open_s = player.all_open_spaces()
        if not open_s:
            return False
        p = _bust_prob(player.yard_total, open_s, n_dice=1)
        return p < self.BUST_STOP and dice_so_far < 12

    def choose_dice_subset(self, roll, player, keep_n):
        open_s = player.all_open_spaces()
        ranked = sorted(roll, key=lambda d: (d not in open_s, -d))
        return ranked if keep_n is None else ranked[:keep_n]

    def should_discard_die(self, die, player):
        return player.yard_total + die > 6  # very tolerant — lots of placement coverage

    def should_reroll(self, roll, player):
        if player.treats <= 0:
            return False
        open_s = player.all_open_spaces()
        misses = sum(1 for d in roll if d not in open_s)
        return misses > 1

    def trot_move(self, player):
        # Move a placed die from the most-complete dog to a less-complete one
        # to maintain broad coverage
        for src in sorted(player.dogs, key=lambda d: len(d.open_spaces)):
            for i, (v, f) in enumerate(zip(src.spaces, src.filled)):
                if f:
                    targets = [d for d in player.incomplete_dogs
                               if d is not src and d.can_accept(v)
                               and len(d.open_spaces) > len(src.open_spaces) + 1]
                    if targets:
                        src.filled[i] = False
                        max(targets, key=lambda d: len(d.open_spaces)).place(v)
                        return

    def dig_target(self, player):
        if not player.yard:
            return (None, 0)
        # Lower highest die — free up yard capacity to keep rolling
        return (max(range(len(player.yard)), key=lambda i: player.yard[i]), -1)

    def dogpile_take(self, player):
        if player.yard:
            return player.yard.pop(max(range(len(player.yard)),
                                       key=lambda i: player.yard[i]))
        return None


# ── TreatGambler ─────────────────────────────────────────────────────────────

class TreatGamblerStrategy(BaseStrategy):
    """
    Two-phase strategy: accumulate treats, then splurge on rolling streaks.

    Accumulate phase (treats < SPLURGE_AT):
        Pick beg/chew/gobble. Never roll extra. Reroll nothing.

    Splurge phase (treats >= SPLURGE_AT):
        Pick rolling tricks. Always continue. Reroll on ANY miss (burn treats).
        Switch back to accumulate when treats < RETREAT_TO.

    The gamble: treat rerolls turn bad rolls into good ones, so rolling
    aggressively when flush is EV-positive. The danger is bust eating your
    accumulated treats indirectly (lost turns).
    """

    SPLURGE_AT  = 6    # treats needed to enter splurge phase
    RETREAT_TO  = 2    # treats below which we switch back to accumulate

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._accumulate_prefs = {
            'chew': 10, 'beg': 9, 'gobble': 8, 'stay': 7, 'play_dead': 5,
            'roll_over': 4, 'howl': 3,
            'fetch': 3, 'hunt': 3, 'guard': 2, 'scavenge': 2, 'search': 2,
            'walk': 3, 'track': 3, 'trot': 2, 'retrieve': 2, 'dig': 2,
            'run': 1, 'sprint': 1, 'chase': 1, 'bolt': 1, 'dogpile': 1,
        }
        self._splurge_prefs = {
            'run': 10, 'sprint': 9, 'chase': 8, 'bolt': 7, 'dogpile': 6,
            'track': 8,   # best in splurge — uses treats on rerolls
            'fetch': 7, 'hunt': 6, 'guard': 5,
            'walk': 6, 'trot': 5, 'retrieve': 5, 'dig': 4, 'scavenge': 4, 'search': 3,
            'roll_over': 3, 'howl': 2,
            'beg': 1, 'chew': 1, 'gobble': 1, 'stay': 1, 'play_dead': 1,
        }

    def _splurging(self, player) -> bool:
        return player.treats >= self.SPLURGE_AT or (
            player.treats >= self.RETREAT_TO and
            # stay in splurge if we were already there (hysteresis)
            hasattr(self, '_was_splurging') and self._was_splurging
        )

    def choose_trick(self, player, tricks):
        face_up = [t for t in tricks if t['face_up']]
        self._was_splurging = self._splurging(player)
        prefs = self._splurge_prefs if self._was_splurging else self._accumulate_prefs
        return _trick_pref(face_up, prefs)

    def assign_die(self, die, player):
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        return min(candidates, key=lambda d: len(d.open_spaces))

    def should_continue(self, player, dice_so_far, trick):
        if not self._splurging(player):
            return False
        if not player.all_open_spaces():
            return False
        # In splurge: keep rolling until very risky or out of treats as safety net
        bust_p = _bust_prob(player.yard_total, player.all_open_spaces(), n_dice=1)
        return bust_p < 0.40 and dice_so_far < 10

    def choose_value(self, roll, player):
        open_s = player.all_open_spaces()
        if roll and open_s:
            return max(set(roll), key=lambda v: (open_s.count(v), -v))
        return max(set(roll), key=roll.count) if roll else 3

    def choose_dice_subset(self, roll, player, keep_n):
        open_s = player.all_open_spaces()
        ranked = sorted(roll, key=lambda d: (d not in open_s, -d))
        return ranked if keep_n is None else ranked[:keep_n]

    def should_discard_die(self, die, player):
        return player.yard_total + die > 5

    def should_reroll(self, roll, player):
        if player.treats <= 0:
            return False
        if not self._splurging(player):
            return False
        open_s = player.all_open_spaces()
        # In splurge: reroll if ANY die is a miss (burn treats freely)
        return any(d not in open_s for d in roll)

    def dig_target(self, player):
        if not player.yard:
            return (None, 0)
        open_s = player.all_open_spaces()
        for t in open_s:
            for idx, b in enumerate(player.yard):
                if abs(b - t) == 1:
                    return (idx, t - b)
        return (max(range(len(player.yard)), key=lambda i: player.yard[i]), -1)

    def dogpile_take(self, player):
        if not self._splurging(player):
            return None
        if player.yard:
            return player.yard.pop(max(range(len(player.yard)),
                                       key=lambda i: player.yard[i]))
        return None


# ── FastAndLoose ──────────────────────────────────────────────────────────────

class FastAndLooseStrategy(BaseStrategy):
    """
    Maximum dice, always. Accepts busts as a cost of speed.

    Rolling tricks only. Always continue. Busts happen — reset and go again.
    The bet: high variance, but the games you win, you win fast.
    No treat usage (don't bother accumulating; rerolling costs turns).
    """

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._prefs = {
            'sprint': 10, 'chase': 9, 'bolt': 8, 'run': 8, 'dogpile': 7,
            'fetch': 8, 'hunt': 7, 'guard': 6, 'scavenge': 5, 'search': 4,
            'walk': 7, 'trot': 6, 'retrieve': 6, 'dig': 5, 'track': 4,
            'roll_over': 5, 'howl': 4,
            'beg': 1, 'chew': 1, 'gobble': 1, 'play_dead': 1, 'stay': 1,
        }

    def choose_trick(self, player, tricks):
        return _trick_pref([t for t in tricks if t['face_up']], self._prefs)

    def assign_die(self, die, player):
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        # Closest to done — get those completions early
        return min(candidates, key=lambda d: len(d.open_spaces))

    def should_continue(self, player, dice_so_far, trick):
        # Always roll more — no risk management
        return bool(player.all_open_spaces()) and dice_so_far < 15

    def choose_value(self, roll, player):
        open_s = player.all_open_spaces()
        if roll and open_s:
            return max(set(roll), key=lambda v: (open_s.count(v), -v))
        return max(set(roll), key=roll.count) if roll else 3

    def choose_dice_subset(self, roll, player, keep_n):
        open_s = player.all_open_spaces()
        ranked = sorted(roll, key=lambda d: (d not in open_s, -d))
        return ranked if keep_n is None else ranked[:keep_n]

    def should_discard_die(self, die, player):
        # Only discard if it's basically certain to bust
        return player.yard_total + die > 7

    def should_reroll(self, roll, player):
        return False  # don't spend time on rerolls — just roll more dice

    def trot_move(self, player):
        pass  # no repositioning — full throttle only

    def dig_target(self, player):
        if not player.yard:
            return (None, 0)
        # Lower the highest die — reduce bust risk so we CAN keep rolling
        return (max(range(len(player.yard)), key=lambda i: player.yard[i]), -1)

    def dogpile_take(self, player):
        if player.yard:
            return player.yard.pop(max(range(len(player.yard)),
                                       key=lambda i: player.yard[i]))
        for dog in sorted(player.dogs, key=lambda d: len(d.open_spaces), reverse=True):
            for i, (v, f) in enumerate(zip(dog.spaces, dog.filled)):
                if f:
                    dog.filled[i] = False
                    return v
        return None


# ── BustAware ─────────────────────────────────────────────────────────────────

class BustAwareStrategy(BaseStrategy):
    """
    Uses exact bust probability math (from spots.prob) to make rolling decisions.

    assign_die: prefers dogs whose remaining needs include HIGH values — those
                dogs absorb expensive dice that would otherwise cost most of the
                yard budget in a single burial. Keeping them alive protects you.

    should_continue: rolls another die only if P(bust | current state) < threshold.
                     Threshold tightens as yard fills.

    choose_value: for fetch/guard, picks the value that minimises expected bust
                  probability on the next roll.
    """

    BUST_THRESHOLD  = 0.15   # stop rolling if P(bust on next single die) > this

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._prefs = {
            'fetch': 9, 'hunt': 8, 'guard': 8, 'search': 6, 'scavenge': 7,
            'run': 7, 'sprint': 7, 'walk': 7, 'track': 6, 'trot': 6,
            'chase': 5, 'bolt': 5, 'retrieve': 5, 'dig': 5, 'dogpile': 4,
            'roll_over': 5, 'howl': 4,
            'beg': 3, 'chew': 3, 'gobble': 3, 'play_dead': 3, 'stay': 2,
        }

    def choose_trick(self, player, tricks):
        return _trick_pref([t for t in tricks if t['face_up']], self._prefs)

    def assign_die(self, die, player):
        """
        Prefer dogs that still need HIGH-value dice.

        Rationale: a dog needing a [6] is a future die-catcher for your most
        dangerous rolls. Give dice to those dogs to keep them progressing so
        they remain in play to absorb 5s and 6s.
        """
        candidates = [d for d in player.incomplete_dogs if d.can_accept(die)]
        if not candidates:
            return None
        # Score = max remaining need on the dog (how dangerous are its future dice?)
        # Tie-break: fewest open spaces (close to done)
        return max(candidates,
                   key=lambda d: (max(d.open_spaces), -len(d.open_spaces)))

    def should_continue(self, player, dice_so_far, trick):
        open_s = player.all_open_spaces()
        if not open_s:
            return False
        p = _bust_prob(player.yard_total, open_s, n_dice=1)
        return p < self.BUST_THRESHOLD

    def choose_value(self, roll, player):
        """Pick the value that, if kept, leaves the lowest bust probability."""
        open_s = player.all_open_spaces()
        if not roll:
            return Counter(open_s).most_common(1)[0][0] if open_s else 3
        # Evaluate each candidate value: what's P(bust) after keeping those dice?
        best_val, best_score = None, float('inf')
        for val in set(roll):
            kept = [d for d in roll if d == val]
            # These dice will be placed; unplaceable ones go to yard
            future_yard = player.yard_total
            future_open = list(Counter(open_s))
            remaining = Counter(open_s)
            for d in sorted(kept):
                if remaining[d] > 0:
                    remaining[d] -= 1
                else:
                    future_yard += d
            future_open = [v for v, c in remaining.items() for _ in range(c)]
            p = _bust_prob(future_yard, future_open, n_dice=1)
            if p < best_score:
                best_score, best_val = p, val
        return best_val

    def choose_dice_subset(self, roll, player, keep_n):
        open_s = player.all_open_spaces()
        ranked = sorted(roll, key=lambda d: (d not in open_s, -d))
        return ranked if keep_n is None else ranked[:keep_n]

    def should_discard_die(self, die, player):
        return player.yard_total + die > 5

    def should_reroll(self, roll, player):
        if player.treats <= 0:
            return False
        open_s = player.all_open_spaces()
        # Reroll if expected bust after placing current roll exceeds threshold
        future_yard = player.yard_total
        remaining = Counter(open_s)
        for d in sorted(roll):
            if remaining[d] > 0:
                remaining[d] -= 1
            else:
                future_yard += d
        future_open = [v for v, c in remaining.items() for _ in range(c)]
        p_after = _bust_prob(future_yard, future_open, n_dice=1)
        return p_after > self.BUST_THRESHOLD * 2

    def dig_target(self, player):
        if not player.yard:
            return (None, 0)
        open_s = player.all_open_spaces()
        # Nudge a buried die toward a needed value
        for target in sorted(open_s, reverse=True):
            for idx, b in enumerate(player.yard):
                if abs(b - target) == 1:
                    return (idx, target - b)
        return (max(range(len(player.yard)), key=lambda i: player.yard[i]), -1)

    def dogpile_take(self, player):
        open_s = player.all_open_spaces()
        # Take a buried die that we can nudge into a needed value
        if player.yard:
            for target in sorted(open_s, reverse=True):
                for idx, b in enumerate(player.yard):
                    if b == target:
                        return player.yard.pop(idx)
        return None
