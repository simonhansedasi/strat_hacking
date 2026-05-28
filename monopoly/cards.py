"""
Chance and Community Chest decks for Monopoly.

Each card is a dict describing its effect. Decks are shuffled at game start
and cycle (reshuffle when exhausted). draw_card() mutates the deck in place.
"""
from __future__ import annotations
import random
from monopoly.board import (
    JAIL_INDEX, GO_INDEX,
    nearest_railroad, nearest_utility,
)


# ── Card definitions ──────────────────────────────────────────────────────────
# kind values:
#   'move_to'       : move to target index (collect Go if passed)
#   'move_back'     : move back n spaces (no Go collection)
#   'collect'       : gain amount from bank
#   'pay'           : pay amount to bank
#   'jail'          : go directly to jail
#   'get_out_of_jail': player gains a get-out-of-jail-free card
#   'per_house'     : pay house_cost per house + hotel_cost per hotel
#   'nearest_railroad': advance to nearest railroad (collect Go if passed)
#   'nearest_utility' : advance to nearest utility (collect Go if passed)

CHANCE_CARDS: list[dict] = [
    {'kind': 'move_to',           'target': 0,   'desc': 'Advance to Go'},
    {'kind': 'move_to',           'target': 24,  'desc': 'Advance to Illinois Ave'},
    {'kind': 'move_to',           'target': 11,  'desc': 'Advance to St. Charles Place'},
    {'kind': 'nearest_railroad',                 'desc': 'Advance to nearest Railroad (x2 rent)'},
    {'kind': 'nearest_railroad',                 'desc': 'Advance to nearest Railroad (x2 rent)'},
    {'kind': 'nearest_utility',                  'desc': 'Advance to nearest Utility (10x dice)'},
    {'kind': 'collect',           'amount': 50,  'desc': 'Bank pays dividend $50'},
    {'kind': 'get_out_of_jail',                  'desc': 'Get Out of Jail Free'},
    {'kind': 'move_back',         'spaces': 3,   'desc': 'Go back 3 spaces'},
    {'kind': 'jail',                             'desc': 'Go to Jail'},
    {'kind': 'per_house',   'house_cost': 25, 'hotel_cost': 100,
                                                 'desc': 'General Repairs: $25/house, $100/hotel'},
    {'kind': 'pay',               'amount': 15,  'desc': 'Pay poor tax $15'},
    {'kind': 'move_to',           'target': 5,   'desc': 'Advance to Reading Railroad'},
    {'kind': 'move_to',           'target': 39,  'desc': 'Advance to Boardwalk'},
    {'kind': 'collect',           'amount': 150, 'desc': 'Building loan matures: collect $150'},
    {'kind': 'collect',           'amount': 100, 'desc': 'Crossword competition: collect $100'},
]

COMMUNITY_CHEST_CARDS: list[dict] = [
    {'kind': 'move_to',           'target': 0,   'desc': 'Advance to Go'},
    {'kind': 'collect',           'amount': 200, 'desc': 'Bank error in your favor: collect $200'},
    {'kind': 'pay',               'amount': 50,  'desc': 'Doctor fee: pay $50'},
    {'kind': 'collect',           'amount': 50,  'desc': 'Sale of stock: collect $50'},
    {'kind': 'get_out_of_jail',                  'desc': 'Get Out of Jail Free'},
    {'kind': 'jail',                             'desc': 'Go to Jail'},
    {'kind': 'collect',           'amount': 100, 'desc': 'Holiday fund matures: collect $100'},
    {'kind': 'collect',           'amount': 20,  'desc': 'Income tax refund: collect $20'},
    {'kind': 'collect',           'amount': 10,  'desc': 'Life insurance matures: collect $10'},
    {'kind': 'pay',               'amount': 100, 'desc': 'Hospital fees: pay $100'},
    {'kind': 'pay',               'amount': 150, 'desc': 'School fees: pay $150'},
    {'kind': 'collect',           'amount': 25,  'desc': 'Consultancy fee: collect $25'},
    {'kind': 'per_house',   'house_cost': 40, 'hotel_cost': 115,
                                                 'desc': 'Street repairs: $40/house, $115/hotel'},
    {'kind': 'collect',           'amount': 10,  'desc': 'Second prize in beauty contest: $10'},
    {'kind': 'collect',           'amount': 100, 'desc': 'Inherit $100'},
    {'kind': 'pay',               'amount': 50,  'desc': 'Pay hospital $50'},
]


# ── Deck management ───────────────────────────────────────────────────────────

def deal_decks(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """Shuffle and return (chance_deck, community_chest_deck)."""
    chance = list(CHANCE_CARDS)
    cc     = list(COMMUNITY_CHEST_CARDS)
    rng.shuffle(chance)
    rng.shuffle(cc)
    return chance, cc


def draw_card(deck: list[dict], source: list[dict], rng: random.Random) -> dict:
    """Draw from top of deck. Reshuffles from source when exhausted."""
    if not deck:
        deck.extend(source)
        rng.shuffle(deck)
    return deck.pop(0)
