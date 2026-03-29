"""
Trick implementations for Spots.

Each trick is a function: trick_name(player, deck, strategy, rng) -> None
All decisions are delegated to the strategy object.
Tricks mutate player state directly.

Beginner set: Howl, Roll Over, Beg, Fetch, Walk, Run
Full set adds one of each colour — same interface throughout.
"""
from __future__ import annotations
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spots.game import PlayerState, DogCard
    from spots.strategies import BaseStrategy


def _roll(n: int, rng: random.Random) -> list[int]:
    return [rng.randint(1, 6) for _ in range(n)]


def _place_roll(player: 'PlayerState', roll: list[int], strategy: 'BaseStrategy') -> bool:
    """
    Place all dice from a roll using strategy decisions.
    Each die either goes on a matching dog space or is buried in the yard.
    Returns False if player busted during placement.
    """
    for die in roll:
        if player.can_place(die):
            # Strategy chooses which dog gets the die
            dog = strategy.assign_die(die, player)
            if dog is not None:
                dog.place(die)
            else:
                # Strategy chose to bury a placeable die (unusual but allowed)
                if not player.bury(die):
                    player.bust()
                    return False
        else:
            if not player.bury(die):
                player.bust()
                return False
    return True


# ── Always-present tricks ─────────────────────────────────────────────────────

def howl(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Draw a dog if <6, then roll 1 die."""
    if len(player.dogs) < 6 and deck:
        new_dog = deck.pop(0)
        player.dogs.append(new_dog)
    roll = _roll(1, rng)
    _place_roll(player, roll, strategy)


def roll_over(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll all buried dice, then optionally roll 1 more die."""
    if player.yard:
        buried = list(player.yard)
        player.yard.clear()
        busted = not _place_roll(player, buried, strategy)
        if busted:
            return
    # Optionally roll 1 extra die
    if strategy.should_continue(player, dice_so_far=len(player.yard), trick='roll_over'):
        roll = _roll(1, rng)
        _place_roll(player, roll, strategy)


# ── Green tricks (treats) ─────────────────────────────────────────────────────

def beg(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Take 1 treat + 1 per paw print."""
    player.treats += 1 + player.paw_prints


def chew(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Double treats, then take 1."""
    player.treats = player.treats * 2 + 1


def gobble(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Take 7 treats, return treats equal to highest unfilled space."""
    player.treats += 7
    all_open = player.all_open_spaces()
    if all_open:
        player.treats -= max(all_open)
        player.treats = max(0, player.treats)


def play_dead(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 1 die. If buried without busting, gain treats equal to die value."""
    roll = _roll(1, rng)
    die = roll[0]
    if not player.can_place(die):
        ok = player.bury(die)
        if ok:
            player.treats += die
        else:
            player.bust()
    else:
        _place_roll(player, roll, strategy)


def stay(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random,
         facedown_count: int = 0):
    """Take 1 treat per facedown trick (excluding Stay itself)."""
    player.treats += facedown_count


# ── Blue tricks (choose dice) ─────────────────────────────────────────────────

def fetch(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 8 dice. Place all dice of a chosen value, discard the rest."""
    roll = _roll(8, rng)
    chosen = strategy.choose_value(roll, player)
    kept = [d for d in roll if d == chosen]
    _place_roll(player, kept, strategy)


def guard(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Name a number, roll 4. Discard > that number, place the rest."""
    threshold = strategy.choose_value([], player)   # strategy names a number pre-roll
    roll = _roll(4, rng)
    kept = [d for d in roll if d <= threshold]
    _place_roll(player, kept, strategy)


def hunt(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 2 + paw_prints dice. Place any 2, discard the rest."""
    roll = _roll(2 + player.paw_prints, rng)
    kept = strategy.choose_dice_subset(roll, player, keep_n=2)
    _place_roll(player, kept, strategy)


def scavenge(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 4. May discard any die lower than yard total, then place rest."""
    roll = _roll(4, rng)
    kept = []
    for die in roll:
        if die < player.yard_total and strategy.should_discard_die(die, player):
            pass  # discarded
        else:
            kept.append(die)
    _place_roll(player, kept, strategy)


def search(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 7. Place dice whose total equals exactly 8, discard rest."""
    roll = _roll(7, rng)
    # Strategy selects a subset that sums to 8 (may be empty if impossible)
    kept = strategy.choose_dice_subset_sum(roll, player, target_sum=8)
    _place_roll(player, kept, strategy)


# ── Yellow tricks (roll a few) ────────────────────────────────────────────────

def walk(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 2 dice, then optionally roll 1 more."""
    roll = _roll(2, rng)
    busted = not _place_roll(player, roll, strategy)
    if busted:
        return
    if strategy.should_continue(player, dice_so_far=2, trick='walk'):
        roll2 = _roll(1, rng)
        _place_roll(player, roll2, strategy)


def track(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 3 dice. Treats allow partial reroll."""
    roll = _roll(3, rng)
    # Treat-powered partial reroll (unlike normal full-reroll)
    while player.treats > 0 and strategy.should_reroll(roll, player):
        keep = strategy.choose_dice_subset(roll, player, keep_n=None)
        reroll_n = len(roll) - len(keep)
        player.treats -= 1
        roll = keep + _roll(reroll_n, rng)
    _place_roll(player, roll, strategy)


def trot(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Optionally remove a die from a dog to place elsewhere, then roll 2."""
    # Strategy may move a die between dogs
    strategy.trot_move(player)
    roll = _roll(2, rng)
    _place_roll(player, roll, strategy)


def retrieve(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Place 1 die with value from top dog in deck, then roll 2."""
    if deck:
        top_dog = deck[0]
        if top_dog.spaces:
            free_die_value = top_dog.spaces[0]
            if player.can_place(free_die_value):
                dog = strategy.assign_die(free_die_value, player)
                if dog:
                    dog.place(free_die_value)
            else:
                player.bury(free_die_value)
    roll = _roll(2, rng)
    _place_roll(player, roll, strategy)


def dig(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random,
        all_players: list = None):
    """Per paw print: raise or lower a buried die by 1 (any player). Then roll 2."""
    # Simplified: only modify own yard
    for _ in range(player.paw_prints):
        if player.yard:
            idx, delta = strategy.dig_target(player)
            if idx is not None and 0 <= idx < len(player.yard):
                new_val = player.yard[idx] + delta
                if new_val <= 0:
                    player.yard.pop(idx)
                else:
                    player.yard[idx] = new_val
    roll = _roll(2, rng)
    _place_roll(player, roll, strategy)


# ── Purple tricks (repeat rolls) ─────────────────────────────────────────────

def run(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 3 dice, then optionally keep rolling 1 die at a time."""
    roll = _roll(3, rng)
    busted = not _place_roll(player, roll, strategy)
    if busted:
        return
    dice_rolled = 3
    while strategy.should_continue(player, dice_so_far=dice_rolled, trick='run'):
        roll = _roll(1, rng)
        busted = not _place_roll(player, roll, strategy)
        if busted:
            return
        dice_rolled += 1


def sprint(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 1 die per incomplete dog, then repeat as many times as wanted."""
    incomplete = len(player.incomplete_dogs)
    if incomplete == 0:
        return
    dice_rolled = 0
    while True:
        n = len(player.incomplete_dogs)
        if n == 0:
            break
        roll = _roll(n, rng)
        busted = not _place_roll(player, roll, strategy)
        dice_rolled += n
        if busted:
            return
        if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='sprint'):
            break


def chase(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 1 die, then may add 1 die and repeat."""
    n = 1
    dice_rolled = 0
    while True:
        roll = _roll(n, rng)
        busted = not _place_roll(player, roll, strategy)
        dice_rolled += n
        if busted:
            return
        if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='chase'):
            break
        n += 1


def bolt(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 3-12 dice one at a time. May stop when paw_prints >= dice remaining."""
    total = rng.randint(3, 12)
    dice_rolled = 0
    for i in range(total):
        remaining = total - i
        roll = _roll(1, rng)
        busted = not _place_roll(player, roll, strategy)
        dice_rolled += 1
        if busted:
            return
        # Can stop early if paw_prints >= remaining dice
        if player.paw_prints >= remaining - 1:
            if not strategy.should_continue(player, dice_so_far=dice_rolled, trick='bolt'):
                break


def dogpile(player: 'PlayerState', deck: list, strategy: 'BaseStrategy', rng: random.Random):
    """Roll 3 dice (1 must come from dogs/yard), repeat as wanted."""
    # First iteration requires taking 1 die from dogs or yard
    if not player.yard and not any(any(d.filled) for d in player.dogs):
        return  # nothing to take
    dice_rolled = 0
    while True:
        # Remove one die from dogs/yard as the taken die
        taken = strategy.dogpile_take(player)
        if taken is None:
            break
        roll = [taken] + _roll(2, rng)
        busted = not _place_roll(player, roll, strategy)
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
    # Add face-up/treat state
    return [{'name': t['name'], 'fn': t['fn'], 'colour': t['colour'],
             'face_up': True, 'treats': 0}
            for t in tricks]
