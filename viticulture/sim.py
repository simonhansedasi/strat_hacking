from __future__ import annotations
import random
import statistics
from dataclasses import dataclass, field

from viticulture.cards import VineCard, OrderCard
from viticulture.game import (
    GameState, PlayerBoard, ActionSpace,
    new_game, draw_vine, draw_order,
    do_harvest, do_make_wine, year_end,
    STRUCTURES, WAKEUP_BONUSES, WIN_VP, MAX_YEARS,
)
from viticulture.strategies import BaseStrategy


@dataclass
class GameResult:
    winner: int
    final_vp: list[int]
    years: int
    orders_filled: list[int]


@dataclass
class SimStats:
    n_games: int
    n_players: int
    strategy_names: list[str]
    win_rate: list[float]
    avg_vp: list[float]
    std_vp: list[float]
    avg_years: float
    avg_orders_filled: list[float]
    all_vp: list[list[int]] = field(repr=False, default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"Viticulture — {self.n_games} games, {self.n_players} players",
            "",
            f"{'Strategy':<20} {'Win%':>6} {'Avg VP':>7} {'Std VP':>7} {'Orders/g':>9}",
            "-" * 52,
        ]
        for i, name in enumerate(self.strategy_names):
            lines.append(
                f"{name:<20} {self.win_rate[i]*100:>5.1f}%"
                f" {self.avg_vp[i]:>7.1f}"
                f" {self.std_vp[i]:>7.1f}"
                f" {self.avg_orders_filled[i]:>9.2f}"
            )
        lines.append(f"\nAvg game length: {self.avg_years:.1f} years")
        return "\n".join(lines)


def _apply_wakeup_bonus(board: PlayerBoard, pos: int, gs: GameState) -> None:
    bonus = WAKEUP_BONUSES[pos]
    board.lira += bonus['lira']
    board.vp += bonus['vp']
    for _ in range(bonus['draw_vine']):
        draw_vine(board, gs)
    for _ in range(bonus['draw_order']):
        draw_order(board, gs)


def _execute_summer(action: str, strategy: BaseStrategy,
                    board: PlayerBoard, gs: GameState) -> None:
    """Execute a summer action (no placement bookkeeping)."""
    if action == 'draw_vine':
        draw_vine(board, gs)

    elif action == 'give_tour':
        board.lira += 3 if 'tastingroom' in board.structures else 2

    elif action == 'sell_grapes':
        board.lira += sum(board.crush_red) + sum(board.crush_white)
        board.crush_red.clear()
        board.crush_white.clear()

    elif action == 'plant_vine':
        plantable = [v for v in board.hand_vines if board.can_plant(v)]
        if plantable:
            idx = strategy.choose_vine_to_plant(board.hand_vines, board, gs)
            vine = board.hand_vines[idx]
            if board.can_plant(vine):
                field_indices = board.plantable_fields(vine)
                fi = strategy.choose_field_to_plant(vine, field_indices, board)
                board.fields[fi].vines.append(vine)
                board.hand_vines.pop(idx)

    elif action == 'build_structure':
        affordable = [s for s, c in STRUCTURES.items()
                      if s not in board.structures and board.lira >= c]
        choice = strategy.choose_structure(affordable, board, gs)
        if choice and choice in affordable:
            board.lira -= STRUCTURES[choice]
            board.structures.add(choice)

    elif action == 'harvest_field':
        harvestable = board.harvestable_fields()
        if harvestable:
            fi = strategy.choose_field_to_harvest(harvestable, board)
            do_harvest(board, fi)


def _execute_winter(action: str, strategy: BaseStrategy,
                    board: PlayerBoard, gs: GameState) -> None:
    """Execute a winter action (no placement bookkeeping)."""
    if action == 'draw_order':
        draw_order(board, gs)

    elif action == 'make_wine':
        wines = strategy.choose_wines_to_make(board, gs)
        if wines:
            do_make_wine(board, wines)

    elif action == 'fill_order':
        fillable = board.fillable_orders()
        idx = strategy.choose_order_to_fill(fillable, board, gs)
        if idx is not None and fillable:
            board.fill_order(fillable[idx])

    elif action == 'train_worker':
        if board.lira >= 4 and board.max_workers < 6:
            board.lira -= 4
            board.max_workers += 1
            board.workers += 1

    elif action == 'harvest_field':
        harvestable = board.harvestable_fields()
        if harvestable:
            fi = strategy.choose_field_to_harvest(harvestable, board)
            do_harvest(board, fi)


def _run_season(strategies: list[BaseStrategy], gs: GameState,
                season: str, spaces: list[ActionSpace]) -> None:
    """Run one season: players take turns placing workers until all pass."""
    n = len(strategies)
    passed = [False] * n
    space_map = {s.name: s for s in spaces}
    execute = _execute_summer if season == 'summer' else _execute_winter

    while not all(passed):
        for pid in gs.wake_order:
            if passed[pid]:
                continue
            board = gs.boards[pid]
            strategy = strategies[pid]

            if board.workers == 0 and not board.grande:
                passed[pid] = True
                continue

            regular_spaces = [s for s in spaces if s.available_for_regular()]
            grande_only = ([s for s in spaces if s.available_for_grande()
                            and not s.available_for_regular()]
                           if board.grande else [])

            if not regular_spaces and not grande_only:
                passed[pid] = True
                continue

            if season == 'summer':
                action = strategy.summer_action(regular_spaces or grande_only, board, gs, pid)
            else:
                action = strategy.winter_action(regular_spaces or grande_only, board, gs, pid)

            if action is None:
                passed[pid] = True
                continue

            target_space = space_map.get(action)
            if target_space is None:
                passed[pid] = True
                continue

            if target_space.available_for_regular() and board.workers > 0:
                target_space.place_regular()
                board.workers -= 1
                execute(action, strategy, board, gs)
            elif target_space.available_for_grande() and board.grande:
                target_space.place_grande()
                board.grande = False
                execute(action, strategy, board, gs)
            else:
                passed[pid] = True


def run_game(strategies: list[BaseStrategy], rng: random.Random) -> GameResult:
    n = len(strategies)
    gs = new_game(n, rng)

    for year in range(1, MAX_YEARS + 1):
        # Spring: wake-up selection
        available_positions = list(range(7))
        rng.shuffle(gs.wake_order)  # randomize initial choice order
        chosen = {}
        for pid in gs.wake_order:
            remaining = [p for p in available_positions if p not in chosen.values()]
            pos = strategies[pid].choose_wakeup(remaining, gs, pid)
            chosen[pid] = pos
            _apply_wakeup_bonus(gs.boards[pid], pos, gs)

        # Sort wake_order by chosen position (earlier = first player)
        gs.wake_order = sorted(range(n), key=lambda p: chosen[p])

        # Summer
        _run_season(strategies, gs, 'summer', gs.summer_spaces)

        # Winter
        _run_season(strategies, gs, 'winter', gs.winter_spaces)

        # Year end
        year_end(gs)

        # Check win
        winners = [i for i, b in enumerate(gs.boards) if b.vp >= WIN_VP]
        if winners:
            winner = max(winners, key=lambda i: gs.boards[i].vp)
            return GameResult(
                winner=winner,
                final_vp=[b.vp for b in gs.boards],
                years=year,
                orders_filled=[b.orders_filled for b in gs.boards],
            )

    # Timeout: highest VP wins
    winner = max(range(n), key=lambda i: gs.boards[i].vp)
    return GameResult(
        winner=winner,
        final_vp=[b.vp for b in gs.boards],
        years=MAX_YEARS,
        orders_filled=[b.orders_filled for b in gs.boards],
    )


def simulate(strategy_factories: list, strategy_names: list[str],
             n_games: int = 5_000, seed: int = 42) -> SimStats:
    rng = random.Random(seed)
    n = len(strategy_factories)
    wins = [0] * n
    all_vp: list[list[int]] = [[] for _ in range(n)]
    all_years: list[int] = []
    all_orders: list[list[int]] = [[] for _ in range(n)]

    for _ in range(n_games):
        game_rng = random.Random(rng.randint(0, 2**31))
        strategies = [f(game_rng) for f in strategy_factories]
        result = run_game(strategies, game_rng)

        wins[result.winner] += 1
        all_years.append(result.years)
        for i in range(n):
            all_vp[i].append(result.final_vp[i])
            all_orders[i].append(result.orders_filled[i])

    return SimStats(
        n_games=n_games,
        n_players=n,
        strategy_names=strategy_names,
        win_rate=[w / n_games for w in wins],
        avg_vp=[statistics.mean(vp) for vp in all_vp],
        std_vp=[statistics.stdev(vp) for vp in all_vp],
        avg_years=statistics.mean(all_years),
        avg_orders_filled=[statistics.mean(o) for o in all_orders],
        all_vp=all_vp,
    )


if __name__ == '__main__':
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from viticulture.strategies import (
        RandomStrategy, ExpansionStrategy, OrderRushStrategy, BalancedStrategy,
    )

    factories = [
        lambda rng: RandomStrategy(rng),
        lambda rng: ExpansionStrategy(rng),
        lambda rng: OrderRushStrategy(rng),
        lambda rng: BalancedStrategy(rng),
    ]
    names = ['Random', 'Expansion', 'OrderRush', 'Balanced']

    print("Running 5000 games...")
    stats = simulate(factories, names, n_games=5_000)
    print(stats)
