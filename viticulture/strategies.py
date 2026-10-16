from __future__ import annotations
import random
from typing import Optional

from viticulture.cards import VineCard, OrderCard
from viticulture.game import (
    ActionSpace, PlayerBoard, GameState, STRUCTURES, WINE_TYPES,
    draw_vine, draw_order,
)


class BaseStrategy:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def choose_wakeup(self, available: list[int], gs: GameState, pid: int) -> int:
        return self.rng.choice(available)

    def summer_action(self, spaces: list[ActionSpace], board: PlayerBoard,
                      gs: GameState, pid: int) -> Optional[str]:
        valid = [s.name for s in spaces if s.available_for_regular()]
        return self.rng.choice(valid) if valid else None

    def choose_vine_to_plant(self, hand: list[VineCard], board: PlayerBoard,
                              gs: GameState) -> int:
        return self.rng.randrange(len(hand))

    def choose_field_to_plant(self, vine: VineCard, field_indices: list[int],
                               board: PlayerBoard) -> int:
        return self.rng.choice(field_indices)

    def choose_structure(self, affordable: list[str], board: PlayerBoard,
                         gs: GameState) -> Optional[str]:
        return self.rng.choice(affordable) if affordable else None

    def choose_field_to_harvest(self, harvestable: list[int],
                                 board: PlayerBoard) -> int:
        return self.rng.choice(harvestable)

    def winter_action(self, spaces: list[ActionSpace], board: PlayerBoard,
                      gs: GameState, pid: int) -> Optional[str]:
        valid = [s.name for s in spaces if s.available_for_regular()]
        return self.rng.choice(valid) if valid else None

    def choose_wines_to_make(self, board: PlayerBoard,
                              gs: GameState) -> list[tuple]:
        """Return list of (wine_type, [grape_values]) to make."""
        wines = []
        reds = sorted(board.crush_red, reverse=True)
        whites = sorted(board.crush_white, reverse=True)
        if reds:
            wines.append(('red', [reds[0]]))
            reds = reds[1:]
        if whites:
            wines.append(('white', [whites[0]]))
        return wines

    def choose_order_to_fill(self, fillable: list[OrderCard], board: PlayerBoard,
                              gs: GameState) -> Optional[int]:
        return 0 if fillable else None


# ---------------------------------------------------------------------------
# RandomStrategy — uniform random baseline
# ---------------------------------------------------------------------------

class RandomStrategy(BaseStrategy):
    pass  # all hooks already random in BaseStrategy


# ---------------------------------------------------------------------------
# ExpansionStrategy — build infrastructure, maximize production volume
# ---------------------------------------------------------------------------

class ExpansionStrategy(BaseStrategy):
    """Build trellis/irrigation early, plant vines aggressively, harvest often."""

    _STRUCTURE_PRIORITY = ['trellis', 'irrigation', 'medium_cellar', 'windmill',
                           'large_cellar', 'cottage', 'tastingroom']

    def choose_wakeup(self, available, gs, pid):
        # Prefer draw_vine bonus (pos 2) then lira bonuses
        for pref in [2, 1, 4, 3, 0, 5, 6]:
            if pref in available:
                return pref
        return available[0]

    def summer_action(self, spaces, board, gs, pid):
        space_map = {s.name: s for s in spaces}

        # 1. Build trellis/irrigation if affordable and not built
        if space_map.get('build_structure', None) and \
                space_map['build_structure'].available_for_regular():
            needed = [s for s in ['trellis', 'irrigation']
                      if s not in board.structures and board.lira >= STRUCTURES[s]]
            if needed:
                return 'build_structure'

        # 2. Plant if we have a plantable vine
        plantable = [v for v in board.hand_vines if board.can_plant(v)]
        if plantable and space_map.get('plant_vine') and \
                space_map['plant_vine'].available_for_regular():
            return 'plant_vine'

        # 3. Harvest if fields are ready
        if board.harvestable_fields() and \
                space_map.get('harvest_field') and \
                space_map['harvest_field'].available_for_regular():
            return 'harvest_field'

        # 4. Draw vine to fill hand
        if len(board.hand_vines) < 3 and \
                space_map.get('draw_vine') and \
                space_map['draw_vine'].available_for_regular():
            return 'draw_vine'

        # 5. Give tour for lira
        if board.lira < 3 and space_map.get('give_tour') and \
                space_map['give_tour'].available_for_regular():
            return 'give_tour'

        # 6. Build other structures
        if space_map.get('build_structure') and \
                space_map['build_structure'].available_for_regular():
            return 'build_structure'

        # fallback: any available
        valid = [s.name for s in spaces if s.available_for_regular()]
        return self.rng.choice(valid) if valid else None

    def choose_structure(self, affordable, board, gs):
        for s in self._STRUCTURE_PRIORITY:
            if s in affordable and s not in board.structures:
                return s
        return affordable[0] if affordable else None

    def choose_vine_to_plant(self, hand, board, gs):
        # Prefer highest-value plantable vine
        plantable = [(i, v) for i, v in enumerate(hand) if board.can_plant(v)]
        if not plantable:
            return 0
        return max(plantable, key=lambda iv: iv[1].planting_value)[0]

    def choose_field_to_plant(self, vine, field_indices, board):
        # Plant in the smallest field that fits, to preserve larger fields for bigger vines
        return min(field_indices, key=lambda i: board.fields[i].capacity)

    def winter_action(self, spaces, board, gs, pid):
        space_map = {s.name: s for s in spaces}

        def avail(name):
            return space_map.get(name) and space_map[name].available_for_regular()

        # Fill orders if we can
        if board.fillable_orders() and avail('fill_order'):
            return 'fill_order'

        # Make wine from grapes
        if (board.crush_red or board.crush_white) and avail('make_wine'):
            return 'make_wine'

        # Draw order
        if len(board.hand_orders) < 3 and avail('draw_order'):
            return 'draw_order'

        # Harvest in winter if fields ready and didn't in summer
        if board.harvestable_fields() and avail('harvest_field'):
            return 'harvest_field'

        valid = [s.name for s in spaces if s.available_for_regular()]
        return self.rng.choice(valid) if valid else None


# ---------------------------------------------------------------------------
# OrderRushStrategy — fill orders fast, prioritize VP through residuals
# ---------------------------------------------------------------------------

class OrderRushStrategy(BaseStrategy):
    """Skip heavy structure investment; make wine immediately and fill orders."""

    def choose_wakeup(self, available, gs, pid):
        # Want draw_order or lira
        for pref in [3, 4, 1, 0, 2, 5, 6]:
            if pref in available:
                return pref
        return available[0]

    def summer_action(self, spaces, board, gs, pid):
        space_map = {s.name: s for s in spaces}

        def avail(name):
            return space_map.get(name) and space_map[name].available_for_regular()

        # Plant cheap (no-prereq) vines when possible
        cheap_plantable = [v for v in board.hand_vines
                           if board.can_plant(v) and not v.needs_trellis and not v.needs_irrigation]
        if cheap_plantable and avail('plant_vine'):
            return 'plant_vine'

        # Harvest for grapes
        if board.harvestable_fields() and avail('harvest_field'):
            return 'harvest_field'

        # Draw vine if hand is empty
        if not board.hand_vines and avail('draw_vine'):
            return 'draw_vine'

        # Tour for lira
        if board.lira < 2 and avail('give_tour'):
            return 'give_tour'

        # Sell grapes if crush pad is near full and no wine-making soon
        if (sum(board.crush_red) + sum(board.crush_white)) >= 7 and avail('sell_grapes'):
            return 'sell_grapes'

        valid = [s.name for s in spaces if s.available_for_regular()]
        return self.rng.choice(valid) if valid else None

    def choose_vine_to_plant(self, hand, board, gs):
        # Prefer no-prereq vines
        no_prereq = [i for i, v in enumerate(hand)
                     if board.can_plant(v) and not v.needs_trellis and not v.needs_irrigation]
        if no_prereq:
            return no_prereq[0]
        plantable = [i for i, v in enumerate(hand) if board.can_plant(v)]
        return plantable[0] if plantable else 0

    def choose_field_to_plant(self, vine, field_indices, board):
        return field_indices[0]

    def winter_action(self, spaces, board, gs, pid):
        space_map = {s.name: s for s in spaces}

        def avail(name):
            return space_map.get(name) and space_map[name].available_for_regular()

        # Priority: fill orders → make wine → draw order → train worker → harvest
        if board.fillable_orders() and avail('fill_order'):
            return 'fill_order'
        if (board.crush_red or board.crush_white) and avail('make_wine'):
            return 'make_wine'
        if len(board.hand_orders) < 4 and avail('draw_order'):
            return 'draw_order'
        if board.max_workers < 4 and board.lira >= 4 and avail('train_worker'):
            return 'train_worker'
        if board.harvestable_fields() and avail('harvest_field'):
            return 'harvest_field'

        valid = [s.name for s in spaces if s.available_for_regular()]
        return self.rng.choice(valid) if valid else None

    def choose_wines_to_make(self, board, gs):
        # Make as many wines as possible from all available grapes
        wines = []
        reds = sorted(board.crush_red, reverse=True)
        whites = sorted(board.crush_white, reverse=True)
        # Make single wines for each grape to maximize fills
        for r in reds:
            if board.wine_slot_free('red', min(r, 9)):
                wines.append(('red', [r]))
        for w in whites:
            if board.wine_slot_free('white', min(w, 9)):
                wines.append(('white', [w]))
        return wines

    def choose_order_to_fill(self, fillable, board, gs):
        if not fillable:
            return None
        # Pick highest residual order
        return max(range(len(fillable)), key=lambda i: fillable[i].residual)


# ---------------------------------------------------------------------------
# BalancedStrategy — EV-driven, adapts to game state
# ---------------------------------------------------------------------------

class BalancedStrategy(BaseStrategy):
    """Score each action by expected VP/lira efficiency and pick the best."""

    _STRUCTURE_PRIORITY = ['trellis', 'irrigation', 'windmill', 'medium_cellar',
                           'large_cellar', 'cottage', 'tastingroom']

    def choose_wakeup(self, available, gs, pid):
        # Score: lira value + card draw value; prefer going earlier when equal
        scores = {0: 0, 1: 1, 2: 1.5, 3: 1, 4: 2, 5: 2.5, 6: 3}
        return max(available, key=lambda p: scores.get(p, 0))

    def _score_action(self, name: str, board: PlayerBoard, gs: GameState) -> float:
        plantable = [v for v in board.hand_vines if board.can_plant(v)]
        has_grapes = bool(board.crush_red or board.crush_white)
        has_fields = bool(board.harvestable_fields())
        fillable = board.fillable_orders()

        if name == 'fill_order':
            if fillable:
                best = max(fillable, key=lambda o: o.vp + o.residual)
                return float(best.vp + best.residual * 0.5)
            return -1.0

        if name == 'make_wine':
            return 2.0 if has_grapes else -1.0

        if name == 'harvest_field':
            return 1.5 if has_fields else -1.0

        if name == 'plant_vine':
            return 2.0 if plantable else -1.0

        if name == 'build_structure':
            affordable = [s for s, c in STRUCTURES.items()
                          if s not in board.structures and board.lira >= c]
            if not affordable:
                return -1.0
            # Value of next unbuilt structure
            for s in self._STRUCTURE_PRIORITY:
                if s in affordable:
                    if s in ('trellis', 'irrigation') and not any(
                            not v.needs_trellis and not v.needs_irrigation
                            for v in board.hand_vines):
                        return 2.5
                    if s == 'windmill':
                        return 2.0
                    return 1.5
            return 0.5

        if name == 'draw_order':
            return 1.0 if len(board.hand_orders) < 3 else 0.0

        if name == 'draw_vine':
            return 1.0 if len(board.hand_vines) < 2 else 0.2

        if name == 'give_tour':
            return 1.0 if board.lira < 3 else 0.3

        if name == 'sell_grapes':
            total = sum(board.crush_red) + sum(board.crush_white)
            return 0.8 if total >= 4 else 0.0

        if name == 'train_worker':
            return 1.2 if board.max_workers < 4 and board.lira >= 4 else -1.0

        return 0.0

    def summer_action(self, spaces, board, gs, pid):
        valid = [s for s in spaces if s.available_for_regular()]
        if not valid:
            return None
        return max(valid, key=lambda s: self._score_action(s.name, board, gs)).name

    def winter_action(self, spaces, board, gs, pid):
        valid = [s for s in spaces if s.available_for_regular()]
        if not valid:
            return None
        return max(valid, key=lambda s: self._score_action(s.name, board, gs)).name

    def choose_structure(self, affordable, board, gs):
        for s in self._STRUCTURE_PRIORITY:
            if s in affordable and s not in board.structures:
                return s
        return affordable[0] if affordable else None

    def choose_vine_to_plant(self, hand, board, gs):
        plantable = [(i, v) for i, v in enumerate(hand) if board.can_plant(v)]
        if not plantable:
            return 0
        # Prefer high-value vines; avoid vines that clog hand if prereqs missing
        return max(plantable, key=lambda iv: iv[1].planting_value)[0]

    def choose_field_to_plant(self, vine, field_indices, board):
        return min(field_indices, key=lambda i: board.fields[i].capacity)

    def choose_wines_to_make(self, board, gs):
        wines = []
        # Prefer combining grapes for higher-value wines to match larger orders
        reds = sorted(board.crush_red, reverse=True)
        whites = sorted(board.crush_white, reverse=True)

        # Try to make wines that unlock unfilled orders
        target_vals = {}
        for order in board.hand_orders:
            for wtype, min_val in order.requirements:
                target_vals.setdefault(wtype, []).append(min_val)

        if reds:
            combined = min(sum(reds), 9)
            if target_vals.get('red') and any(combined >= mv for mv in target_vals['red']):
                if board.wine_slot_free('red', combined):
                    wines.append(('red', list(reds)))
                    reds = []
            if reds and board.wine_slot_free('red', min(reds[0], 9)):
                wines.append(('red', [reds[0]]))

        if whites:
            combined = min(sum(whites), 9)
            if target_vals.get('white') and any(combined >= mv for mv in target_vals['white']):
                if board.wine_slot_free('white', combined):
                    wines.append(('white', list(whites)))
                    whites = []
            if whites and board.wine_slot_free('white', min(whites[0], 9)):
                wines.append(('white', [whites[0]]))

        # Attempt rosé if medium_cellar available
        if 'medium_cellar' in board.structures:
            remaining_reds = [r for r in board.crush_red
                              if not any(r in w[1] for w in wines if w[0] == 'red')]
            remaining_whites = [w for w in board.crush_white
                                if not any(w in ww[1] for ww in wines if ww[0] == 'white')]
            if remaining_reds and remaining_whites:
                rv, wv = remaining_reds[0], remaining_whites[0]
                val = min(rv + wv - 1, 9)
                if board.wine_slot_free('rose', val):
                    wines.append(('rose', [rv, wv]))

        return wines

    def choose_order_to_fill(self, fillable, board, gs):
        if not fillable:
            return None
        # Pick order with best VP + residual
        return max(range(len(fillable)), key=lambda i: fillable[i].vp + fillable[i].residual)
