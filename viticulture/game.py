from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Optional

from viticulture.cards import VineCard, OrderCard, make_vine_deck, make_order_deck

STRUCTURES: dict[str, int] = {
    'trellis':       2,
    'irrigation':    3,
    'medium_cellar': 4,
    'cottage':       4,
    'windmill':      5,
    'large_cellar':  6,
    'tastingroom':   6,
}

WINE_TYPES = ('red', 'white', 'rose', 'sparkling')

# Wake-up track positions 0-6; each slot gives (lira, vp, draw_vine, draw_order)
WAKEUP_BONUSES: list[dict] = [
    {'lira': 0, 'vp': 0, 'draw_vine': 0, 'draw_order': 0},  # pos 0: first, no bonus
    {'lira': 1, 'vp': 0, 'draw_vine': 0, 'draw_order': 0},  # pos 1: +$1
    {'lira': 0, 'vp': 0, 'draw_vine': 1, 'draw_order': 0},  # pos 2: draw vine
    {'lira': 0, 'vp': 0, 'draw_vine': 0, 'draw_order': 1},  # pos 3: draw order
    {'lira': 2, 'vp': 0, 'draw_vine': 0, 'draw_order': 0},  # pos 4: +$2
    {'lira': 1, 'vp': 0, 'draw_vine': 1, 'draw_order': 0},  # pos 5: +$1 + draw vine
    {'lira': 3, 'vp': 0, 'draw_vine': 0, 'draw_order': 0},  # pos 6: +$3 (last, loses tempo)
]

MAX_WORKERS = 6
MAX_GRAPE_VALUE = 9
MIN_SPARKLING_VALUE = 7
WIN_VP = 25
MAX_YEARS = 30


@dataclass
class Field:
    capacity: int
    vines: list = field(default_factory=list)

    def planted_value(self) -> int:
        return sum(v.planting_value for v in self.vines)

    def can_plant(self, vine: VineCard) -> bool:
        return self.planted_value() + vine.planting_value <= self.capacity

    def red_production(self) -> int:
        return sum(v.red for v in self.vines)

    def white_production(self) -> int:
        return sum(v.white for v in self.vines)

    def is_empty(self) -> bool:
        return len(self.vines) == 0


@dataclass
class ActionSpace:
    name: str
    season: str
    slots: int
    occupied: int = 0
    grande_here: bool = False

    def available_for_regular(self) -> bool:
        return self.occupied < self.slots

    def available_for_grande(self) -> bool:
        return not self.grande_here

    def place_regular(self) -> None:
        self.occupied += 1

    def place_grande(self) -> None:
        self.grande_here = True

    def reset(self) -> None:
        self.occupied = 0
        self.grande_here = False


@dataclass
class PlayerBoard:
    fields: list          # [Field(5), Field(6), Field(7)]
    structures: set       # built structure names
    hand_vines: list
    hand_orders: list
    crush_red: list       # list of int grape values
    crush_white: list     # list of int grape values
    cellar: dict          # wine_type -> set of int values
    lira: int
    vp: int
    residual: int
    workers: int
    grande: bool
    max_workers: int
    windmill_used: bool   # reset each year
    orders_filled: int    # cumulative

    def has_structure(self, name: str) -> bool:
        return name in self.structures

    def can_plant(self, vine: VineCard) -> bool:
        if vine.needs_trellis and 'trellis' not in self.structures:
            return False
        if vine.needs_irrigation and 'irrigation' not in self.structures:
            return False
        return any(f.can_plant(vine) for f in self.fields)

    def plantable_fields(self, vine: VineCard) -> list[int]:
        return [i for i, f in enumerate(self.fields) if f.can_plant(vine)]

    def harvestable_fields(self) -> list[int]:
        return [i for i, f in enumerate(self.fields) if not f.is_empty()]

    def add_grape(self, color: str, value: int) -> None:
        pad = self.crush_red if color == 'red' else self.crush_white
        total = sum(pad) + value
        if total <= MAX_GRAPE_VALUE:
            pad.append(value)
        else:
            # overflow: keep existing grapes, discard incoming
            pass

    def wine_slot_free(self, wtype: str, value: int) -> bool:
        return value not in self.cellar[wtype]

    def store_wine(self, wtype: str, value: int) -> bool:
        if self.wine_slot_free(wtype, value):
            self.cellar[wtype].add(value)
            return True
        return False

    def fillable_orders(self) -> list[OrderCard]:
        result = []
        for order in self.hand_orders:
            if self._can_fill(order):
                result.append(order)
        return result

    def _can_fill(self, order: OrderCard) -> bool:
        for wtype, min_val in order.requirements:
            if not any(v >= min_val for v in self.cellar[wtype]):
                return False
        return True

    def fill_order(self, order: OrderCard) -> None:
        for wtype, min_val in order.requirements:
            candidates = sorted([v for v in self.cellar[wtype] if v >= min_val])
            self.cellar[wtype].discard(candidates[0])
        self.vp += order.vp
        self.residual = min(self.residual + order.residual, 5)
        self.hand_orders.remove(order)
        self.orders_filled += 1


@dataclass
class GameState:
    boards: list
    vine_deck: list
    order_deck: list
    year: int
    summer_spaces: list
    winter_spaces: list
    wake_order: list      # player indices in wake-up order


def make_summer_spaces() -> list[ActionSpace]:
    return [
        ActionSpace('draw_vine',       'summer', slots=2),
        ActionSpace('give_tour',       'summer', slots=1),
        ActionSpace('sell_grapes',     'summer', slots=1),
        ActionSpace('plant_vine',      'summer', slots=1),
        ActionSpace('build_structure', 'summer', slots=1),
        ActionSpace('harvest_field',   'summer', slots=1),
    ]


def make_winter_spaces() -> list[ActionSpace]:
    return [
        ActionSpace('draw_order',    'winter', slots=2),
        ActionSpace('make_wine',     'winter', slots=1),
        ActionSpace('fill_order',    'winter', slots=1),
        ActionSpace('train_worker',  'winter', slots=1),
        ActionSpace('harvest_field', 'winter', slots=1),
    ]


def make_player_board() -> PlayerBoard:
    return PlayerBoard(
        fields=[Field(5), Field(6), Field(7)],
        structures=set(),
        hand_vines=[],
        hand_orders=[],
        crush_red=[],
        crush_white=[],
        cellar={wt: set() for wt in WINE_TYPES},
        lira=3,
        vp=0,
        residual=0,
        workers=2,
        grande=True,
        max_workers=2,
        windmill_used=False,
        orders_filled=0,
    )


def draw_vine(board: PlayerBoard, gs: GameState) -> None:
    if gs.vine_deck:
        board.hand_vines.append(gs.vine_deck.pop())


def draw_order(board: PlayerBoard, gs: GameState) -> None:
    if gs.order_deck:
        board.hand_orders.append(gs.order_deck.pop())


def do_harvest(board: PlayerBoard, field_idx: int) -> None:
    f = board.fields[field_idx]
    red = f.red_production()
    white = f.white_production()
    if red > 0:
        board.add_grape('red', red)
    if white > 0:
        board.add_grape('white', white)


def do_make_wine(board: PlayerBoard, wines: list[tuple]) -> None:
    """wines: list of (wine_type, [grape_values_to_consume])"""
    windmill_triggered = False
    for wtype, grape_vals in wines:
        if wtype == 'red':
            for v in grape_vals:
                if v in board.crush_red:
                    board.crush_red.remove(v)
            value = min(sum(grape_vals), MAX_GRAPE_VALUE)
            stored = board.store_wine('red', value)
        elif wtype == 'white':
            for v in grape_vals:
                if v in board.crush_white:
                    board.crush_white.remove(v)
            value = min(sum(grape_vals), MAX_GRAPE_VALUE)
            stored = board.store_wine('white', value)
        elif wtype == 'rose':
            if not grape_vals or len(grape_vals) != 2:
                continue
            rv, wv = grape_vals[0], grape_vals[1]
            if rv in board.crush_red and wv in board.crush_white:
                board.crush_red.remove(rv)
                board.crush_white.remove(wv)
                value = min(rv + wv - 1, MAX_GRAPE_VALUE)
                stored = board.store_wine('rose', value)
            else:
                continue
        elif wtype == 'sparkling':
            if not grape_vals or len(grape_vals) != 2:
                continue
            w1, w2 = grape_vals[0], grape_vals[1]
            if w1 in board.crush_white and w2 in board.crush_white:
                board.crush_white.remove(w1)
                board.crush_white.remove(w2)
                value = min(w1 + w2 - 1, MAX_GRAPE_VALUE)
                if value >= MIN_SPARKLING_VALUE:
                    stored = board.store_wine('sparkling', value)
                else:
                    stored = False
            else:
                continue
        else:
            stored = False

        if stored and not windmill_triggered and 'windmill' in board.structures and not board.windmill_used:
            board.vp += 1
            board.windmill_used = True
            windmill_triggered = True


def age_wines(board: PlayerBoard) -> None:
    for wtype in WINE_TYPES:
        aged = set()
        for v in sorted(board.cellar[wtype], reverse=True):
            new_v = min(v + 1, MAX_GRAPE_VALUE)
            if new_v not in aged:
                aged.add(new_v)
            else:
                aged.add(v)
        board.cellar[wtype] = aged


def year_end(gs: GameState) -> None:
    for board in gs.boards:
        age_wines(board)
        board.lira += board.residual
        board.workers = board.max_workers
        board.grande = True
        board.windmill_used = False
        if 'cottage' in board.structures:
            draw_vine(board, gs)
    for sp in gs.summer_spaces + gs.winter_spaces:
        sp.reset()
    gs.year += 1


def new_game(n_players: int, rng: random.Random) -> GameState:
    vine_deck = make_vine_deck(rng)
    order_deck = make_order_deck(rng)
    boards = [make_player_board() for _ in range(n_players)]
    gs = GameState(
        boards=boards,
        vine_deck=vine_deck,
        order_deck=order_deck,
        year=1,
        summer_spaces=make_summer_spaces(),
        winter_spaces=make_winter_spaces(),
        wake_order=list(range(n_players)),
    )
    for board in boards:
        draw_vine(board, gs)
        draw_order(board, gs)
    return gs
