"""
Strategy interface and implementations for Monopoly.

BaseStrategy defines all decision hooks. Concrete strategies override them.
No trading, no auctions — decisions are: buy, build, jail, mortgage/unmortgage.

  AlwaysBuyStrategy   — buy every unowned property you can afford; build to 3 houses fast
  ColorFocusStrategy  — buy only to complete or extend color groups; pass on isolated singles
  OrangeRedStrategy   — prioritize orange+red (statistically most-landed due to jail);
                        buy others opportunistically
  RailroadStrategy    — heavily weight railroads + utilities; stay in jail (safer late game)
  CashHoarderStrategy — only buy cheap properties; build slowly; hoard cash reserves
"""
from __future__ import annotations
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from monopoly.game import PlayerState, GameState
from monopoly.board import (
    BOARD, COLOR_GROUPS, RAILROAD_INDICES, UTILITY_INDICES,
    Property, Railroad, Utility,
)


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseStrategy:
    def should_buy(self, pos: int, player: 'PlayerState', gs: 'GameState') -> bool:
        """Return True to buy the unowned property at pos."""
        return False

    def should_build(self, color: str, player: 'PlayerState', gs: 'GameState') -> bool:
        """Return True to place another house on the cheapest slot in this color group."""
        return False

    def jail_action(self, player: 'PlayerState', gs: 'GameState') -> str:
        """'pay' | 'roll' | 'card'"""
        return 'roll'

    def choose_mortgage(self, player: 'PlayerState', gs: 'GameState') -> Optional[int]:
        """Return a board index to mortgage, or None. Called during bankruptcy resolution."""
        # Default: mortgage lowest-value unmortgaged property owned
        candidates = [
            (BOARD[i].mortgage_value, i)
            for i, ps in enumerate(gs.prop_states)
            if ps.owner == player._index and not ps.mortgaged
        ]
        if not candidates:
            return None
        return min(candidates)[1]

    def choose_unmortgage(self, player: 'PlayerState', gs: 'GameState') -> Optional[int]:
        """Return a board index to unmortgage, or None."""
        return None


# ── AlwaysBuy ─────────────────────────────────────────────────────────────────

class AlwaysBuyStrategy(BaseStrategy):
    """
    Buy every unowned property you can afford (keep $50 buffer).
    Build aggressively to 3 houses once you have a monopoly — that's where
    the rent curve jumps most dramatically.
    Pay out of jail immediately (you want to be on the board rolling).
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def should_buy(self, pos, player, gs):
        space = BOARD[pos]
        price = getattr(space, 'price', 0)
        return player.cash - price >= 50

    def should_build(self, color, player, gs):
        indices = COLOR_GROUPS[color]
        min_houses = min(gs.prop_states[i].houses for i in indices)
        if min_houses >= 3:
            return False   # 3 houses is the sweet spot; don't over-invest
        space = BOARD[indices[0]]
        cost = getattr(space, 'house_cost', 0)
        return player.cash - cost >= 100

    def jail_action(self, player, gs):
        if player.get_out_cards > 0:
            return 'card'
        return 'pay'   # get back on the board

    def choose_unmortgage(self, player, gs):
        candidates = [
            (BOARD[i].mortgage_value, i)
            for i, ps in enumerate(gs.prop_states)
            if ps.owner == player._index and ps.mortgaged
        ]
        for _, idx in sorted(candidates, reverse=True):
            cost = int(BOARD[idx].mortgage_value * 1.1)
            if player.cash - cost >= 200:
                return idx
        return None


# ── ColorFocus ────────────────────────────────────────────────────────────────

class ColorFocusStrategy(BaseStrategy):
    """
    Only buy if it completes or extends a color group you're already in.
    Skip isolated singles that don't pair with anything you hold.
    Build heavily once you have the monopoly — go all the way to hotels.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def _group_interest(self, pos: int, player_idx: int, gs: 'GameState') -> bool:
        space = BOARD[pos]
        if not isinstance(space, Property):
            return True   # always interested in railroads/utilities
        color = space.color
        group = COLOR_GROUPS[color]
        already_own = sum(1 for i in group if gs.prop_states[i].owner == player_idx)
        return already_own > 0 or len(group) == 2   # short groups worth targeting

    def should_buy(self, pos, player, gs):
        space = BOARD[pos]
        price = getattr(space, 'price', 0)
        if player.cash - price < 100:
            return False
        return self._group_interest(pos, player._index, gs)

    def should_build(self, color, player, gs):
        indices = COLOR_GROUPS[color]
        max_houses = max(gs.prop_states[i].houses for i in indices)
        if max_houses >= 5:
            return False
        space = BOARD[indices[0]]
        cost = getattr(space, 'house_cost', 0)
        return player.cash - cost >= 150

    def jail_action(self, player, gs):
        if player.get_out_cards > 0:
            return 'card'
        # Stay in jail if we already have monopolies (safer to collect rent from safety)
        has_monopoly = any(
            gs.owns_color_group(player._index, c)
            for c in COLOR_GROUPS
        )
        if has_monopoly and player.jail_turns < 2:
            return 'roll'
        return 'pay'

    def choose_unmortgage(self, player, gs):
        # Prioritize unmortgaging properties in color groups we own
        for color, indices in COLOR_GROUPS.items():
            if gs.owns_color_group(player._index, color):
                for i in indices:
                    ps = gs.prop_states[i]
                    if ps.mortgaged and ps.owner == player._index:
                        cost = int(BOARD[i].mortgage_value * 1.1)
                        if player.cash - cost >= 200:
                            return i
        return None


# ── OrangeRed ─────────────────────────────────────────────────────────────────

class OrangeRedStrategy(BaseStrategy):
    """
    Target orange (16-19) and red (21-24) properties — statistically most
    landed on because players coming out of jail hit them first.
    Buy others opportunistically if affordable. Build orange/red first.
    Always pay out of jail (you want to be rolling, not sitting).
    """

    PRIORITY_COLORS = {'orange', 'red'}

    def __init__(self, rng: random.Random):
        self.rng = rng

    def should_buy(self, pos, player, gs):
        space = BOARD[pos]
        price = getattr(space, 'price', 0)
        if player.cash - price < 50:
            return False
        if isinstance(space, Property) and space.color in self.PRIORITY_COLORS:
            return player.cash - price >= 50   # very willing for orange/red
        return player.cash - price >= 150       # conservative for everything else

    def should_build(self, color, player, gs):
        indices = COLOR_GROUPS[color]
        min_houses = min(gs.prop_states[i].houses for i in indices)
        # Build orange/red aggressively; others only to 2 houses
        max_target = 4 if color in self.PRIORITY_COLORS else 2
        if min_houses >= max_target:
            return False
        space = BOARD[indices[0]]
        cost = getattr(space, 'house_cost', 0)
        reserve = 100 if color in self.PRIORITY_COLORS else 200
        return player.cash - cost >= reserve

    def jail_action(self, player, gs):
        if player.get_out_cards > 0:
            return 'card'
        return 'pay'   # always get back on the board

    def choose_unmortgage(self, player, gs):
        for color in ('orange', 'red'):
            for i in COLOR_GROUPS.get(color, []):
                ps = gs.prop_states[i]
                if ps.mortgaged and ps.owner == player._index:
                    cost = int(BOARD[i].mortgage_value * 1.1)
                    if player.cash - cost >= 150:
                        return i
        return None


# ── Railroad ──────────────────────────────────────────────────────────────────

class RailroadStrategy(BaseStrategy):
    """
    Collect all 4 railroads and both utilities. Ignore development (can't build on them).
    Stay in jail late game — safer than rolling and landing on developed properties.
    Buy properties only as a cash sink if flush, but never at the expense of railroads.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng

    def should_buy(self, pos, player, gs):
        space = BOARD[pos]
        price = getattr(space, 'price', 0)
        if isinstance(space, (Railroad, Utility)):
            return player.cash - price >= 100
        # Buy properties only if very flush — they're not the focus
        return player.cash - price >= 600

    def should_build(self, color, player, gs):
        space = BOARD[COLOR_GROUPS[color][0]]
        cost = getattr(space, 'house_cost', 0)
        return player.cash - cost >= 800   # very conservative; rarely builds

    def jail_action(self, player, gs):
        if player.get_out_cards > 0:
            return 'card'
        # Stay in jail if opponents have developed properties — safer
        n_active = len(gs.active_players())
        total_houses = sum(ps.houses for ps in gs.prop_states)
        if total_houses > 6 * n_active and player.jail_turns < 3:
            return 'roll'   # try for doubles, don't pay
        return 'pay'

    def choose_unmortgage(self, player, gs):
        # Prioritize unmortgaging railroads/utilities
        for i in RAILROAD_INDICES + UTILITY_INDICES:
            ps = gs.prop_states[i]
            if ps.mortgaged and ps.owner == player._index:
                cost = int(BOARD[i].mortgage_value * 1.1)
                if player.cash - cost >= 200:
                    return i
        return None


# ── CashHoarder ───────────────────────────────────────────────────────────────

class CashHoarderStrategy(BaseStrategy):
    """
    Only buy cheap properties (price <= 200). Keep large cash reserves.
    Build slowly and only when comfortably flush. Stay in jail late game.
    The bet: you'll never go bankrupt, and you'll win attrition games.
    """

    BUY_MAX_PRICE  = 200
    CASH_RESERVE   = 500
    BUILD_RESERVE  = 600

    def __init__(self, rng: random.Random):
        self.rng = rng

    def should_buy(self, pos, player, gs):
        space = BOARD[pos]
        price = getattr(space, 'price', 0)
        if price > self.BUY_MAX_PRICE:
            return False
        return player.cash - price >= self.CASH_RESERVE

    def should_build(self, color, player, gs):
        indices = COLOR_GROUPS[color]
        min_houses = min(gs.prop_states[i].houses for i in indices)
        if min_houses >= 2:
            return False   # never go past 2 houses
        space = BOARD[indices[0]]
        cost = getattr(space, 'house_cost', 0)
        return player.cash - cost >= self.BUILD_RESERVE

    def jail_action(self, player, gs):
        if player.get_out_cards > 0:
            return 'card'
        # Stay in jail most of the time — safe cash accumulation
        if player.jail_turns < 3:
            return 'roll'
        return 'pay'

    def choose_unmortgage(self, player, gs):
        candidates = [
            (BOARD[i].mortgage_value, i)
            for i, ps in enumerate(gs.prop_states)
            if ps.owner == player._index and ps.mortgaged
        ]
        for _, idx in sorted(candidates):
            cost = int(BOARD[idx].mortgage_value * 1.1)
            if player.cash - cost >= self.CASH_RESERVE * 2:
                return idx
        return None
