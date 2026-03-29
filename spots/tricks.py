"""
Trick implementations for Spots.

Each trick is a function: trick_name(player, deck, strategy, rng, pool) -> None
All decisions are delegated to the strategy object.
Tricks mutate player state directly.

pool (spots.game.Pool) enforces the 20-treat / 40-dice hard limits.
Pass pool=None to run without limits (testing only).

IMPORTANT: Tricks NEVER call player.bust() directly. _place_roll returns False
when the yard exceeds the bust threshold, and tricks return early. sim.py is
responsible for detecting player.is_busted, returning dice to the pool, and
calling player.bust().

Beginner set: Howl, Roll Over, Beg, Fetch, Walk, Run
Full set adds one of each colour — same interface throughout.
"""
from __future__ import annotations
import random
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from spots.game import PlayerState, DogCard, Pool
    from spots.strategies import BaseStrategy


# ── Pool helpers ──────────────────────────────────────────────────────────────

def _roll(n: int, rng: random.Random, pool: Optional['Pool'] = None) -> list[int]:
    """Roll up to n dice, limited by pool.dice if pool is provided."""
    if pool is not None:
        n = min(n, pool.dice)
    result = [rng.randint(1, 6) for _ in range(n)]
    if pool is not None:
        pool.dice -= len(result)
    return result


def _return_dice(n: int, pool: Optional['Pool']) -> None:
    """Return n dice to the supply (discarded by fetch/hunt/etc. or unprocessed on bust)."""
    if pool is not None and n > 0:
        pool.dice += n


def _gain_treats(player: 'PlayerState', amount: int, pool: Optional['Pool']) -> None:
    """Give player up to amount treats, capped by pool supply."""
    if amount <= 0:
        return
    if pool is not None:
        amount = min(amount, pool.treats)
        pool.treats -= amount
    player.treats += amount


def _spend_treat(player: 'PlayerState', pool: Optional['Pool']) -> bool:
    """Spend 1 treat from player, return it to pool. Returns False if none left."""
    if player.treats <= 0:
        return False
    player.treats -= 1
    if pool is not None:
        pool.treats += 1
    return True


def _place_roll(player: 'PlayerState', roll: list[int], strategy: 'BaseStrategy',
                pool: Optional['Pool'] = None) -> bool:
    """
    Place all dice from a roll using strategy decisions.
    Each die either goes on a matching dog space or is buried in the yard.

    Returns False if the player busted during placement. On bust, any
    unprocessed dice in the roll are returned to the pool. The caller
    is responsible for detecting player.is_busted and calling player.bust().
    """
    for i, die in enumerate(roll):
        if player.can_place(die):
            dog = strategy.assign_die(die, player)
            if dog is not None:
                dog.place(die)
            else:
                player.bury(die)
                if player.is_busted:
                    _return_dice(len(roll) - i - 1, pool)
                    return False
        else:
            player.bury(die)
            if player.is_busted:
                _return_dice(len(roll) - i - 1, pool)
                return False
    return True


# ── Always-present tricks ─────────────────────────────────────────────────────

def howl(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None):
    """Draw a dog if <6, then roll 1 die."""
    if len(player.dogs) < 6 and deck:
        player.dogs.append(deck.pop(0))
    roll = _roll(1, rng, pool)
    _place_roll(player, roll, strategy, pool)


def roll_over(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
              rng: random.Random, pool: Optional['Pool'] = None):
    """Roll all buried dice, then optionally roll 1 more die."""
    if player.yard:
        buried = list(player.yard)
        player.yard.clear()
        # Buried dice were already deducted from pool when first rolled.
        # Clearing yard doesn't change pool — dice stay committed until placed/scored/busted.
        busted = not _place_roll(player, buried, strategy, pool)
        if busted:
            return
    if strategy.should_continue(player, dice_so_far=len(player.yard), trick='roll_over'):
        roll = _roll(1, rng, pool)
        _place_roll(player, roll, strategy, pool)


# ── Green tricks (treats) ─────────────────────────────────────────────────────

def beg(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
        rng: random.Random, pool: Optional['Pool'] = None):
    """Take 1 treat + 1 per paw print."""
    _gain_treats(player, 1 + player.paw_prints, pool)


def chew(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None):
    """Double treats, then take 1. Net draw from supply: player.treats + 1."""
    _gain_treats(player, player.treats + 1, pool)


def gobble(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
           rng: random.Random, pool: Optional['Pool'] = None):
    """Take 7 treats, return treats equal to highest unfilled space."""
    _gain_treats(player, 7, pool)
    all_open = player.all_open_spaces()
    if all_open:
        refund = min(max(all_open), player.treats)
        player.treats -= refund
        if pool is not None:
            pool.treats += refund


def play_dead(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
              rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 1 die. If buried without busting, gain treats equal to die value."""
    roll = _roll(1, rng, pool)
    if not roll:
        return
    die = roll[0]
    if not player.can_place(die):
        player.bury(die)
        if not player.is_busted:
            _gain_treats(player, die, pool)
        # if busted: sim.py detects and handles
    else:
        _place_roll(player, roll, strategy, pool)


def stay(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None,
         facedown_count: int = 0):
    """Take 1 treat per facedown trick (excluding Stay itself)."""
    _gain_treats(player, facedown_count, pool)


# ── Blue tricks (choose dice) ─────────────────────────────────────────────────

def fetch(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
          rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 8 dice. Place all dice of a chosen value, discard the rest."""
    roll = _roll(8, rng, pool)
    chosen = strategy.choose_value(roll, player)
    kept = [d for d in roll if d == chosen]
    _return_dice(len(roll) - len(kept), pool)
    _place_roll(player, kept, strategy, pool)


def guard(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
          rng: random.Random, pool: Optional['Pool'] = None):
    """Name a number, roll 4. Discard > that number, place the rest."""
    threshold = strategy.choose_value([], player)
    roll = _roll(4, rng, pool)
    kept = [d for d in roll if d <= threshold]
    _return_dice(len(roll) - len(kept), pool)
    _place_roll(player, kept, strategy, pool)


def hunt(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 2 + paw_prints dice. Place any 2, discard the rest."""
    roll = _roll(2 + player.paw_prints, rng, pool)
    kept = strategy.choose_dice_subset(roll, player, keep_n=2)
    _return_dice(len(roll) - len(kept), pool)
    _place_roll(player, kept, strategy, pool)


def scavenge(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
             rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 4. May discard any die lower than yard total, then place rest."""
    roll = _roll(4, rng, pool)
    kept = []
    discarded = 0
    for die in roll:
        if die < player.yard_total and strategy.should_discard_die(die, player):
            discarded += 1
        else:
            kept.append(die)
    _return_dice(discarded, pool)
    _place_roll(player, kept, strategy, pool)


def search(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
           rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 7. Place dice whose total equals exactly 8, discard rest."""
    roll = _roll(7, rng, pool)
    kept = strategy.choose_dice_subset_sum(roll, player, target_sum=8)
    _return_dice(len(roll) - len(kept), pool)
    _place_roll(player, kept, strategy, pool)


# ── Yellow tricks (roll a few) ────────────────────────────────────────────────

def walk(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 2 dice, then optionally roll 1 more."""
    roll = _roll(2, rng, pool)
    busted = not _place_roll(player, roll, strategy, pool)
    if busted:
        return
    if strategy.should_continue(player, dice_so_far=2, trick='walk'):
        roll2 = _roll(1, rng, pool)
        _place_roll(player, roll2, strategy, pool)


def track(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
          rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 3 dice. Treats allow partial reroll."""
    roll = _roll(3, rng, pool)
    while player.treats > 0 and strategy.should_reroll(roll, player):
        keep = strategy.choose_dice_subset(roll, player, keep_n=None)
        reroll_n = len(roll) - len(keep)
        _return_dice(reroll_n, pool)   # rerolled dice return to supply
        _spend_treat(player, pool)
        roll = keep + _roll(reroll_n, rng, pool)
    _place_roll(player, roll, strategy, pool)


def trot(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None):
    """Optionally remove a die from a dog to place elsewhere, then roll 2."""
    strategy.trot_move(player)
    roll = _roll(2, rng, pool)
    _place_roll(player, roll, strategy, pool)


def retrieve(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
             rng: random.Random, pool: Optional['Pool'] = None):
    """Place 1 die with value from top dog in deck, then roll 2."""
    if deck:
        top_dog = deck[0]
        if top_dog.spaces:
            free_die_value = top_dog.spaces[0]
            if pool is None or pool.dice > 0:
                if pool is not None:
                    pool.dice -= 1
                if player.can_place(free_die_value):
                    dog = strategy.assign_die(free_die_value, player)
                    if dog:
                        dog.place(free_die_value)
                    else:
                        player.bury(free_die_value)
                else:
                    player.bury(free_die_value)
    if not player.is_busted:
        roll = _roll(2, rng, pool)
        _place_roll(player, roll, strategy, pool)


def dig(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
        rng: random.Random, pool: Optional['Pool'] = None,
        all_players: list = None):
    """Per paw print: raise or lower a buried die by 1. Then roll 2."""
    for _ in range(player.paw_prints):
        if player.yard:
            idx, delta = strategy.dig_target(player)
            if idx is not None and 0 <= idx < len(player.yard):
                new_val = player.yard[idx] + delta
                if new_val <= 0:
                    player.yard.pop(idx)
                    _return_dice(1, pool)   # die leaves the game state
                else:
                    player.yard[idx] = new_val
    roll = _roll(2, rng, pool)
    _place_roll(player, roll, strategy, pool)


# ── Purple tricks (repeat rolls) ─────────────────────────────────────────────

def run(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
        rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 3 dice, then optionally keep rolling 1 die at a time."""
    roll = _roll(3, rng, pool)
    busted = not _place_roll(player, roll, strategy, pool)
    if busted:
        return
    dice_rolled = 3
    while strategy.should_continue(player, dice_so_far=dice_rolled, trick='run'):
        roll = _roll(1, rng, pool)
        if not roll:
            break
        busted = not _place_roll(player, roll, strategy, pool)
        if busted:
            return
        dice_rolled += 1


def sprint(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
           rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 1 die per incomplete dog, then repeat as many times as wanted."""
    if not player.incomplete_dogs:
        return
    dice_rolled = 0
    while True:
        n = len(player.incomplete_dogs)
        if n == 0:
            break
        roll = _roll(n, rng, pool)
        if not roll:
            break
        busted = not _place_roll(player, roll, strategy, pool)
        dice_rolled += len(roll)
        if busted:
            return
        if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='sprint'):
            break


def chase(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
          rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 1 die, then may add 1 die and repeat."""
    n = 1
    dice_rolled = 0
    while True:
        roll = _roll(n, rng, pool)
        if not roll:
            break
        busted = not _place_roll(player, roll, strategy, pool)
        dice_rolled += len(roll)
        if busted:
            return
        if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='chase'):
            break
        n += 1


def bolt(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
         rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 3-12 dice one at a time. May stop when paw_prints >= dice remaining."""
    total = rng.randint(3, 12)
    dice_rolled = 0
    for i in range(total):
        remaining = total - i
        roll = _roll(1, rng, pool)
        if not roll:
            break
        busted = not _place_roll(player, roll, strategy, pool)
        dice_rolled += 1
        if busted:
            return
        if player.paw_prints >= remaining - 1:
            if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='bolt'):
                break


def dogpile(player: 'PlayerState', deck: list, strategy: 'BaseStrategy',
            rng: random.Random, pool: Optional['Pool'] = None):
    """Roll 3 dice (1 must come from dogs/yard), repeat as wanted."""
    if not player.yard and not any(any(d.filled) for d in player.dogs):
        return
    dice_rolled = 0
    while True:
        taken = strategy.dogpile_take(player)
        if taken is None:
            break
        # Taken die was already committed (on dog/yard); no pool change for it.
        roll = [taken] + _roll(2, rng, pool)
        busted = not _place_roll(player, roll, strategy, pool)
        dice_rolled += 3
        if busted:
            return
        if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='dogpile'):
            break


# ── Trick registry ─────────────────────────────────────────────────────────────

TRICKS_BY_COLOUR = {
    'always': [
        {'name': 'Howl',      'fn': howl,      'colour': 'always'},
        {'name': 'Roll Over', 'fn': roll_over,  'colour': 'always'},
    ],
    'green': [
        {'name': 'Beg',       'fn': beg,        'colour': 'green'},
        {'name': 'Chew',      'fn': chew,       'colour': 'green'},
        {'name': 'Gobble',    'fn': gobble,     'colour': 'green'},
        {'name': 'Play Dead', 'fn': play_dead,  'colour': 'green'},
        {'name': 'Stay',      'fn': stay,       'colour': 'green'},
    ],
    'blue': [
        {'name': 'Fetch',     'fn': fetch,      'colour': 'blue'},
        {'name': 'Guard',     'fn': guard,      'colour': 'blue'},
        {'name': 'Hunt',      'fn': hunt,       'colour': 'blue'},
        {'name': 'Scavenge',  'fn': scavenge,   'colour': 'blue'},
        {'name': 'Search',    'fn': search,     'colour': 'blue'},
    ],
    'yellow': [
        {'name': 'Walk',      'fn': walk,       'colour': 'yellow'},
        {'name': 'Track',     'fn': track,      'colour': 'yellow'},
        {'name': 'Trot',      'fn': trot,       'colour': 'yellow'},
        {'name': 'Retrieve',  'fn': retrieve,   'colour': 'yellow'},
        {'name': 'Dig',       'fn': dig,        'colour': 'yellow'},
    ],
    'purple': [
        {'name': 'Run',       'fn': run,        'colour': 'purple'},
        {'name': 'Sprint',    'fn': sprint,     'colour': 'purple'},
        {'name': 'Chase',     'fn': chase,      'colour': 'purple'},
        {'name': 'Bolt',      'fn': bolt,       'colour': 'purple'},
        {'name': 'Dogpile',   'fn': dogpile,    'colour': 'purple'},
    ],
}


def deal_tricks(rng: random.Random) -> list[dict]:
    """
    Build a game's trick set: Howl + Roll Over (always) + 1 of each colour.
    Returns list of trick dicts with face_up=True and treats=0.
    """
    tricks = list(TRICKS_BY_COLOUR['always'])
    for colour in ('green', 'blue', 'yellow', 'purple'):
        chosen = rng.choice(TRICKS_BY_COLOUR[colour])
        tricks.append(chosen)
    return [{'name': t['name'], 'fn': t['fn'], 'colour': t['colour'],
             'face_up': True, 'treats': 0}
            for t in tricks]
