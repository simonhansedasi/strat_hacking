"""
Monopoly board definition.

All 40 spaces hardcoded. Properties carry their full rent tables.
Railroads and utilities have special rent logic handled in game.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Space:
    index: int
    name: str
    kind: str  # 'go'|'property'|'railroad'|'utility'|'tax'|'chance'|
               # 'community_chest'|'jail'|'go_to_jail'|'free_parking'


@dataclass
class Property(Space):
    color: str
    price: int
    rent: list[int]        # [base, 1h, 2h, 3h, 4h, hotel]
    house_cost: int
    mortgage_value: int


@dataclass
class Railroad(Space):
    price: int = 200
    mortgage_value: int = 100
    # Rent: 25/50/100/200 depending on how many railroads owner holds


@dataclass
class Utility(Space):
    price: int = 150
    mortgage_value: int = 75
    # Rent: 4x dice if own 1, 10x dice if own both


# ── Color groups (for monopoly detection) ─────────────────────────────────────

COLOR_GROUPS: dict[str, list[int]] = {}  # populated after BOARD is defined


# ── Full 40-space board ────────────────────────────────────────────────────────

def _p(idx, name, color, price, rent, house_cost) -> Property:
    return Property(
        index=idx, name=name, kind='property', color=color,
        price=price, rent=rent, house_cost=house_cost,
        mortgage_value=price // 2,
    )


def _r(idx, name) -> Railroad:
    return Railroad(index=idx, name=name, kind='railroad')


def _u(idx, name) -> Utility:
    return Utility(index=idx, name=name, kind='utility')


def _s(idx, name, kind) -> Space:
    return Space(index=idx, name=name, kind=kind)


BOARD: list[Space] = [
    _s(0,  'Go',                    'go'),
    _p(1,  'Mediterranean Ave',     'brown',      60,  [2, 10,  30,  90, 160, 250],  50),
    _s(2,  'Community Chest',       'community_chest'),
    _p(3,  'Baltic Ave',            'brown',      60,  [4, 20,  60, 180, 320, 450],  50),
    _s(4,  'Income Tax',            'tax'),
    _r(5,  'Reading Railroad'),
    _p(6,  'Oriental Ave',          'light_blue', 100, [6, 30,  90, 270, 400, 550],  50),
    _s(7,  'Chance',                'chance'),
    _p(8,  'Vermont Ave',           'light_blue', 100, [6, 30,  90, 270, 400, 550],  50),
    _p(9,  'Connecticut Ave',       'light_blue', 120, [8, 40, 100, 300, 450, 600],  50),
    _s(10, 'Jail / Just Visiting',  'jail'),
    _p(11, 'St. Charles Place',     'pink',       140, [10, 50, 150, 450, 625, 750],  100),
    _u(12, 'Electric Company'),
    _p(13, 'States Ave',            'pink',       140, [10, 50, 150, 450, 625, 750],  100),
    _p(14, 'Virginia Ave',          'pink',       160, [12, 60, 180, 500, 700, 900],  100),
    _r(15, 'Pennsylvania Railroad'),
    _p(16, 'St. James Place',       'orange',     180, [14, 70, 200, 550, 750, 950],  100),
    _s(17, 'Community Chest',       'community_chest'),
    _p(18, 'Tennessee Ave',         'orange',     180, [14, 70, 200, 550, 750, 950],  100),
    _p(19, 'New York Ave',          'orange',     200, [16, 80, 220, 600, 800, 1000], 100),
    _s(20, 'Free Parking',          'free_parking'),
    _p(21, 'Kentucky Ave',          'red',        220, [18, 90, 250, 700, 875, 1050], 150),
    _s(22, 'Chance',                'chance'),
    _p(23, 'Indiana Ave',           'red',        220, [18, 90, 250, 700, 875, 1050], 150),
    _p(24, 'Illinois Ave',          'red',        240, [20, 100, 300, 750, 925, 1100], 150),
    _r(25, 'B&O Railroad'),
    _p(26, 'Atlantic Ave',          'yellow',     260, [22, 110, 330, 800, 975, 1150], 150),
    _p(27, 'Ventnor Ave',           'yellow',     260, [22, 110, 330, 800, 975, 1150], 150),
    _u(28, 'Water Works'),
    _p(29, 'Marvin Gardens',        'yellow',     280, [24, 120, 360, 850, 1025, 1200], 150),
    _s(30, 'Go To Jail',            'go_to_jail'),
    _p(31, 'Pacific Ave',           'green',      300, [26, 130, 390, 900, 1100, 1275], 200),
    _p(32, 'North Carolina Ave',    'green',      300, [26, 130, 390, 900, 1100, 1275], 200),
    _s(33, 'Community Chest',       'community_chest'),
    _p(34, 'Pennsylvania Ave',      'green',      320, [28, 150, 450, 1000, 1200, 1400], 200),
    _r(35, 'Short Line Railroad'),
    _s(36, 'Chance',                'chance'),
    _p(37, 'Park Place',            'dark_blue',  350, [35, 175, 500, 1100, 1300, 1500], 200),
    _s(38, 'Luxury Tax',            'tax'),
    _p(39, 'Boardwalk',             'dark_blue',  400, [50, 200, 600, 1400, 1700, 2000], 200),
]

# ── Derived lookups ────────────────────────────────────────────────────────────

RAILROAD_INDICES: list[int] = [s.index for s in BOARD if isinstance(s, Railroad)]
UTILITY_INDICES:  list[int] = [s.index for s in BOARD if isinstance(s, Utility)]

# Color groups: color -> list of board indices
for _space in BOARD:
    if isinstance(_space, Property):
        COLOR_GROUPS.setdefault(_space.color, []).append(_space.index)

TAX_AMOUNTS: dict[int, int] = {4: 200, 38: 75}   # Income Tax, Luxury Tax

JAIL_INDEX    = 10
GO_TO_JAIL    = 30
GO_INDEX      = 0
GO_SALARY     = 200

# Nearest railroad / utility from a given position (for Chance cards)
def nearest_railroad(pos: int) -> int:
    for r in sorted(RAILROAD_INDICES):
        if r > pos:
            return r
    return RAILROAD_INDICES[0]   # wrap around


def nearest_utility(pos: int) -> int:
    for u in sorted(UTILITY_INDICES):
        if u > pos:
            return u
    return UTILITY_INDICES[0]
