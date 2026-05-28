"""
Qwixx simulation.

Qwixx is multiplayer, so strategies compete head-to-head in each game.
All 5 strategies play in the same game; active player rotates each round.

run_game()  — one game with N strategies; returns GameResult
simulate()  — N games; returns SimStats with per-strategy aggregates
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from qwixx.game import Scoresheet, COLORS, ROWS, MAX_PENALTIES


@dataclass
class GameResult:
    scores:      list[int]
    winner_idx:  int | None       # None on tie
    penalties:   list[int]
    crosses:     list[dict[str, int]]   # per player, per color


def run_game(strategies, rng: random.Random) -> GameResult:
    n = len(strategies)
    sheets = [Scoresheet() for _ in range(n)]
    global_locked: dict[str, bool] = {c: False for c in COLORS}
    locked_count = 0
    active = rng.randint(0, n - 1)

    while True:
        w1, w2 = rng.randint(1, 6), rng.randint(1, 6)
        white_sum = w1 + w2
        colored = {c: rng.randint(1, 6) for c in COLORS if not global_locked[c]}

        active_crossed = False

        # ── Action 1: all players decide simultaneously on white+white sum ────
        action1: dict[int, str] = {}
        for i, (sheet, strat) in enumerate(zip(sheets, strategies)):
            if sheet.is_busted:
                continue
            col = strat.choose_action1(white_sum, sheet, dict(global_locked))
            if col is not None and sheet.can_cross(col, white_sum, global_locked):
                action1[i] = col

        newly_locked: set[str] = set()
        for i, col in action1.items():
            if sheets[i].cross(col, white_sum):
                newly_locked.add(col)
            if i == active:
                active_crossed = True

        for col in newly_locked:
            global_locked[col] = True
            locked_count += 1

        if _game_over(sheets, locked_count):
            break

        # ── Action 2: active player only; one white + one colored die ─────────
        if not sheets[active].is_busted:
            options: list[tuple[str, int]] = []
            for w in (w1, w2):
                for col, die_val in colored.items():
                    val = w + die_val
                    if sheets[active].can_cross(col, val, global_locked):
                        if (col, val) not in options:
                            options.append((col, val))

            choice = strategies[active].choose_action2(
                options, sheets[active], dict(global_locked)
            )
            if choice is not None and choice in options:
                col, val = choice
                if sheets[active].cross(col, val):
                    global_locked[col] = True
                    locked_count += 1
                active_crossed = True

        # Penalty if active player crossed nothing in either action this round
        if not active_crossed and not sheets[active].is_busted:
            sheets[active].penalties += 1

        if _game_over(sheets, locked_count):
            break

        active = (active + 1) % n

    scores = [s.total for s in sheets]
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    return GameResult(
        scores=scores,
        winner_idx=winners[0] if len(winners) == 1 else None,
        penalties=[s.penalties for s in sheets],
        crosses=[{c: s.crosses_in_row(c) for c in COLORS} for s in sheets],
    )


def _game_over(sheets: list[Scoresheet], locked_count: int) -> bool:
    return locked_count >= 2 or any(s.is_busted for s in sheets)


@dataclass
class SimStats:
    n_games:        int
    strategy_names: list[str]
    avg_score:      list[float]
    std_score:      list[float]
    win_rate:       list[float]
    avg_penalties:  list[float]
    avg_crosses:    list[dict[str, float]]
    all_scores:     list[list[int]] = field(repr=False)

    def __str__(self) -> str:
        lines = [f"Qwixx simulation: {self.n_games:,} games, {len(self.strategy_names)} players\n"]
        header = (
            f"  {'Strategy':<20}  {'Avg':>6}  {'Std':>6}  {'Win%':>6}  {'Pen/g':>6}"
            f"  {'Red':>5}  {'Yel':>5}  {'Grn':>5}  {'Blu':>5}"
        )
        lines.append(header)
        lines.append('  ' + '-' * (len(header) - 2))
        for i, name in enumerate(self.strategy_names):
            cx = self.avg_crosses[i]
            lines.append(
                f"  {name:<20}  {self.avg_score[i]:>6.1f}  {self.std_score[i]:>6.1f}"
                f"  {self.win_rate[i]:>6.1%}  {self.avg_penalties[i]:>6.2f}"
                f"  {cx['red']:>5.2f}  {cx['yellow']:>5.2f}"
                f"  {cx['green']:>5.2f}  {cx['blue']:>5.2f}"
            )
        return '\n'.join(lines)


def simulate(
    strategy_factories: list,
    strategy_names:     list[str],
    n_games:            int = 10_000,
    seed:               int = 42,
) -> SimStats:
    rng = random.Random(seed)
    n   = len(strategy_factories)

    all_scores   = [[] for _ in range(n)]
    win_counts   = [0]   * n
    pen_sums     = [0.0] * n
    cross_sums   = [{c: 0.0 for c in COLORS} for _ in range(n)]

    for _ in range(n_games):
        game_rng = random.Random(rng.randint(0, 2**31))
        strats   = [f(game_rng) for f in strategy_factories]
        result   = run_game(strats, game_rng)
        for i in range(n):
            all_scores[i].append(result.scores[i])
            pen_sums[i] += result.penalties[i]
            for c in COLORS:
                cross_sums[i][c] += result.crosses[i][c]
        if result.winner_idx is not None:
            win_counts[result.winner_idx] += 1

    def _std(scores: list[int]) -> float:
        if len(scores) < 2:
            return 0.0
        mean = sum(scores) / len(scores)
        return math.sqrt(sum((s - mean) ** 2 for s in scores) / (len(scores) - 1))

    return SimStats(
        n_games=n_games,
        strategy_names=strategy_names,
        avg_score    =[sum(s) / n_games for s in all_scores],
        std_score    =[_std(s)          for s in all_scores],
        win_rate     =[w / n_games      for w in win_counts],
        avg_penalties=[p / n_games      for p in pen_sums],
        avg_crosses  =[{c: cross_sums[i][c] / n_games for c in COLORS}
                       for i in range(n)],
        all_scores   =all_scores,
    )


if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from qwixx.strategies import (
        RandomStrategy, AggressiveStrategy, ConservativeStrategy,
        LockHunterStrategy, BalancedStrategy,
    )

    factories = [
        lambda rng: RandomStrategy(rng),
        lambda rng: AggressiveStrategy(rng),
        lambda rng: ConservativeStrategy(rng),
        lambda rng: LockHunterStrategy(rng),
        lambda rng: BalancedStrategy(rng),
    ]
    names = ['Random', 'Aggressive', 'Conservative', 'LockHunter', 'Balanced']

    print("Running 10,000 games...")
    stats = simulate(factories, names, n_games=10_000)
    print(stats)
