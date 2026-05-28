"""
Monopoly game state and mechanics.

No trading, no auctions. Players buy on landing if affordable and willing.
Bankruptcy resolution: mortgage → sell houses → declare bankrupt.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from monopoly.board import (
    BOARD, JAIL_INDEX, GO_TO_JAIL, GO_INDEX, GO_SALARY, TAX_AMOUNTS,
    RAILROAD_INDICES, UTILITY_INDICES, COLOR_GROUPS,
    Property, Railroad, Utility, Space,
    nearest_railroad, nearest_utility,
)
from monopoly.cards import (
    CHANCE_CARDS, COMMUNITY_CHEST_CARDS, deal_decks, draw_card,
)

if TYPE_CHECKING:
    from monopoly.strategies import BaseStrategy


# ── Property ownership state ──────────────────────────────────────────────────

@dataclass
class PropertyState:
    owner: Optional[int] = None   # player index, or None = bank
    houses: int = 0               # 0-4 houses, 5 = hotel
    mortgaged: bool = False


# ── Player state ──────────────────────────────────────────────────────────────

@dataclass
class PlayerState:
    cash: int = 1500
    position: int = 0
    jail_turns: int = 0        # 0 = free, 1-3 = consecutive jail turns served
    in_jail: bool = False
    get_out_cards: int = 0
    doubles_streak: int = 0    # consecutive doubles this turn
    bankrupt: bool = False

    def net_worth(self, prop_states: list[PropertyState]) -> int:
        total = self.cash
        for idx, ps in enumerate(prop_states):
            if ps.owner != self._index:
                continue
            space = BOARD[idx]
            mv = getattr(space, 'mortgage_value', 0)
            if ps.mortgaged:
                total += mv
            else:
                total += mv * 2
                if isinstance(space, Property):
                    total += ps.houses * space.house_cost
        return total

    def set_index(self, i: int):
        self._index = i


# ── Game state ────────────────────────────────────────────────────────────────

@dataclass
class GameState:
    players: list[PlayerState]
    prop_states: list[PropertyState]      # indexed by board position
    chance_deck: list[dict]
    cc_deck: list[dict]
    rng: random.Random
    turn: int = 0

    def active_players(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if not p.bankrupt]

    def owns_color_group(self, player_idx: int, color: str) -> bool:
        indices = COLOR_GROUPS.get(color, [])
        return all(
            self.prop_states[i].owner == player_idx and not self.prop_states[i].mortgaged
            for i in indices
        )

    def railroads_owned(self, player_idx: int) -> int:
        return sum(1 for i in RAILROAD_INDICES
                   if self.prop_states[i].owner == player_idx
                   and not self.prop_states[i].mortgaged)

    def utilities_owned(self, player_idx: int) -> int:
        return sum(1 for i in UTILITY_INDICES
                   if self.prop_states[i].owner == player_idx
                   and not self.prop_states[i].mortgaged)


# ── Dice ──────────────────────────────────────────────────────────────────────

def roll_dice(rng: random.Random) -> tuple[int, int]:
    return rng.randint(1, 6), rng.randint(1, 6)


# ── Movement ──────────────────────────────────────────────────────────────────

def _move_to(player: PlayerState, target: int, collect_go: bool = True) -> int:
    """Move player to target. Return Go salary collected (0 or 200)."""
    if collect_go and target <= player.position and target != player.position:
        player.cash += GO_SALARY
        player.position = target
        return GO_SALARY
    player.position = target
    return 0


def _advance(player: PlayerState, steps: int) -> int:
    """Move forward steps spaces. Return Go salary if passed."""
    new_pos = (player.position + steps) % 40
    crossed_go = new_pos < player.position or steps >= 40
    player.position = new_pos
    if crossed_go and new_pos != GO_INDEX:
        player.cash += GO_SALARY
        return GO_SALARY
    return 0


# ── Card resolution ───────────────────────────────────────────────────────────

def resolve_card(player: PlayerState, card: dict, gs: GameState, dice_sum: int = 0) -> None:
    kind = card['kind']
    if kind == 'move_to':
        target = card['target']
        _move_to(player, target, collect_go=True)
        if player.position == GO_TO_JAIL:
            _send_to_jail(player)
        else:
            _land(player, gs, dice_sum)
    elif kind == 'move_back':
        player.position = (player.position - card['spaces']) % 40
        _land(player, gs, dice_sum)
    elif kind == 'collect':
        player.cash += card['amount']
    elif kind == 'pay':
        player.cash -= card['amount']
    elif kind == 'jail':
        _send_to_jail(player)
    elif kind == 'get_out_of_jail':
        player.get_out_cards += 1
    elif kind == 'per_house':
        houses = sum(ps.houses for i, ps in enumerate(gs.prop_states)
                     if ps.owner == player._index and isinstance(BOARD[i], Property)
                     and ps.houses < 5)
        hotels = sum(1 for i, ps in enumerate(gs.prop_states)
                     if ps.owner == player._index and isinstance(BOARD[i], Property)
                     and ps.houses == 5)
        player.cash -= houses * card['house_cost'] + hotels * card['hotel_cost']
    elif kind == 'nearest_railroad':
        target = nearest_railroad(player.position)
        _move_to(player, target, collect_go=True)
        _land(player, gs, dice_sum, railroad_double=True)
    elif kind == 'nearest_utility':
        target = nearest_utility(player.position)
        _move_to(player, target, collect_go=True)
        _land(player, gs, dice_sum, utility_tenx=True)


# ── Jail ──────────────────────────────────────────────────────────────────────

def _send_to_jail(player: PlayerState) -> None:
    player.position = JAIL_INDEX
    player.in_jail = True
    player.jail_turns = 0
    player.doubles_streak = 0


# ── Rent ─────────────────────────────────────────────────────────────────────

def _calculate_rent(pos: int, ps: PropertyState, gs: GameState,
                    dice_sum: int, railroad_double: bool = False,
                    utility_tenx: bool = False) -> int:
    if ps.mortgaged:
        return 0
    space = BOARD[pos]
    owner = ps.owner
    if isinstance(space, Property):
        if ps.houses == 0:
            # Double rent if owner has color monopoly and no houses built yet
            base = space.rent[0]
            if gs.owns_color_group(owner, space.color):
                return base * 2
            return base
        return space.rent[ps.houses]   # rent[1..5]
    elif isinstance(space, Railroad):
        n = gs.railroads_owned(owner)
        base = [0, 25, 50, 100, 200][n]
        return base * 2 if railroad_double else base
    elif isinstance(space, Utility):
        n = gs.utilities_owned(owner)
        mult = 10 if (n == 2 or utility_tenx) else 4
        return dice_sum * mult
    return 0


# ── Landing ───────────────────────────────────────────────────────────────────

def _land(player: PlayerState, gs: GameState, dice_sum: int,
          railroad_double: bool = False, utility_tenx: bool = False) -> None:
    pos = player.position
    space = BOARD[pos]

    if space.kind == 'go_to_jail':
        _send_to_jail(player)
        return

    if space.kind in ('chance', 'community_chest'):
        if space.kind == 'chance':
            card = draw_card(gs.chance_deck, CHANCE_CARDS, gs.rng)
        else:
            card = draw_card(gs.cc_deck, COMMUNITY_CHEST_CARDS, gs.rng)
        resolve_card(player, card, gs, dice_sum)
        return

    if space.kind == 'tax':
        player.cash -= TAX_AMOUNTS.get(pos, 0)
        return

    ps = gs.prop_states[pos]
    if ps.owner is None and isinstance(space, (Property, Railroad, Utility)):
        return   # strategy decides to buy in the main game loop

    if ps.owner is not None and ps.owner != player._index and not ps.mortgaged:
        rent = _calculate_rent(pos, ps, gs, dice_sum, railroad_double, utility_tenx)
        player.cash -= rent
        gs.players[ps.owner].cash += rent


# ── Bankruptcy resolution ─────────────────────────────────────────────────────

def resolve_bankruptcy(player: PlayerState, gs: GameState, strategy: 'BaseStrategy') -> None:
    """Attempt to raise cash by mortgaging and selling houses. Declare bankrupt if still broke."""
    # 1. Sell houses first (half house_cost each)
    while player.cash < 0:
        sold = False
        for idx, ps in enumerate(gs.prop_states):
            if ps.owner == player._index and isinstance(BOARD[idx], Property) and ps.houses > 0:
                ps.houses -= 1
                player.cash += BOARD[idx].house_cost // 2
                sold = True
                break
        if not sold:
            break

    # 2. Mortgage properties
    while player.cash < 0:
        target = strategy.choose_mortgage(player, gs)
        if target is None:
            break
        ps = gs.prop_states[target]
        if ps.owner == player._index and not ps.mortgaged:
            ps.mortgaged = True
            player.cash += BOARD[target].mortgage_value

    if player.cash < 0:
        player.bankrupt = True


# ── Build phase (after landing, before next player) ──────────────────────────

def build_phase(player_idx: int, player: PlayerState, gs: GameState,
                strategy: 'BaseStrategy') -> None:
    """Let strategy build houses on any monopoly it holds."""
    if player.cash <= 0:
        return
    ps = gs.prop_states
    for color, indices in COLOR_GROUPS.items():
        # Inline owns_color_group to avoid repeated method call overhead
        if not all(ps[i].owner == player_idx and not ps[i].mortgaged for i in indices):
            continue
        while strategy.should_build(color, player, gs):
            # Even-build rule: build on property with fewest houses
            candidates = [
                (gs.prop_states[i].houses, i) for i in indices
                if not gs.prop_states[i].mortgaged
                and gs.prop_states[i].houses < 5
            ]
            if not candidates:
                break
            _, target_idx = min(candidates)
            space = BOARD[target_idx]
            cost = space.house_cost
            if player.cash < cost:
                break
            gs.prop_states[target_idx].houses += 1
            player.cash -= cost


# ── Unmortgage phase ──────────────────────────────────────────────────────────

def unmortgage_phase(player_idx: int, player: PlayerState, gs: GameState,
                     strategy: 'BaseStrategy') -> None:
    """Let strategy lift mortgages (costs 110% of mortgage value)."""
    while True:
        target = strategy.choose_unmortgage(player, gs)
        if target is None:
            break
        ps = gs.prop_states[target]
        if ps.owner != player_idx or not ps.mortgaged:
            break
        cost = int(BOARD[target].mortgage_value * 1.1)
        if player.cash < cost:
            break
        ps.mortgaged = False
        player.cash -= cost
