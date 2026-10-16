"""
Royal Game of Ur simulation.

2-player head-to-head game. simulate() runs a round-robin tournament:
every strategy pair plays n_games games (half as player 0, half as player 1
to cancel first-player advantage), and results are aggregated.

run_game(strategies, rng)   — one game; returns winner index (0 or 1)
simulate(factories, names)  — round-robin; returns SimStats
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from itertools import combinations

from ur.game import GameState, roll_dice

MAX_TURNS = 8_000


def run_game(strategies: list, rng: random.Random) -> int:
    """Return winner index (0 or 1), or -1 on timeout."""
    gs = GameState()
    for _ in range(MAX_TURNS):
        if gs.is_over():
            break
        player = gs.current
        roll = roll_dice(rng)
        valid = gs.valid_moves(player, roll)
        if valid:
            idx = strategies[player].choose_move(valid, gs, player, roll)
            extra = gs.apply_move(player, idx, roll)
            if not extra:
                gs.current = 1 - player
        else:
            gs.current = 1 - player
    return gs.winner()


@dataclass
class SimStats:
    names:       list[str]
    h2h:         dict[tuple[int, int], int]  # (i, j) -> wins by i vs j
    total_wins:  list[int]
    total_played: list[int]
    n_games:     int

    def win_rate(self, i: int) -> float:
        return self.total_wins[i] / self.total_played[i] if self.total_played[i] else 0.0

    def h2h_rate(self, i: int, j: int) -> float:
        w = self.h2h.get((i, j), 0)
        total = w + self.h2h.get((j, i), 0)
        return w / total if total else 0.0

    def __str__(self) -> str:
        n = len(self.names)
        lines = [f"Royal Game of Ur — round-robin, {self.n_games:,} games per pair\n"]
        col_w = max(len(nm) for nm in self.names) + 2
        header = f"  {'Strategy':<{col_w}}" + "".join(
            f"{nm[:9]:>10}" for nm in self.names
        ) + f"{'Win%':>8}"
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for i, name in enumerate(self.names):
            row = f"  {name:<{col_w}}"
            for j in range(n):
                if i == j:
                    row += f"{'—':>10}"
                else:
                    row += f"{self.h2h_rate(i, j):>9.1%} "
            row += f"{self.win_rate(i):>7.1%}"
            lines.append(row)
        return "\n".join(lines)


def simulate(
    strategy_factories: list,
    strategy_names:     list[str],
    n_games:            int = 2_000,
    seed:               int = 42,
) -> SimStats:
    """
    Round-robin tournament. Each pair plays n_games games total
    (n_games // 2 with each seating) to cancel first-player advantage.
    """
    rng = random.Random(seed)
    n = len(strategy_factories)
    h2h: dict[tuple[int, int], int] = {}
    per_seating = max(1, n_games // 2)

    for i, j in combinations(range(n), 2):
        for _ in range(per_seating):
            game_rng = random.Random(rng.randint(0, 2**31))
            s = [strategy_factories[i](game_rng), strategy_factories[j](game_rng)]
            w = run_game(s, game_rng)
            if w == 0:
                h2h[(i, j)] = h2h.get((i, j), 0) + 1
            elif w == 1:
                h2h[(j, i)] = h2h.get((j, i), 0) + 1

        for _ in range(per_seating):
            game_rng = random.Random(rng.randint(0, 2**31))
            s = [strategy_factories[j](game_rng), strategy_factories[i](game_rng)]
            w = run_game(s, game_rng)
            if w == 0:
                h2h[(j, i)] = h2h.get((j, i), 0) + 1
            elif w == 1:
                h2h[(i, j)] = h2h.get((i, j), 0) + 1

    total_wins = [
        sum(h2h.get((i, j), 0) for j in range(n) if j != i) for i in range(n)
    ]
    total_played = [
        sum(
            h2h.get((i, j), 0) + h2h.get((j, i), 0) for j in range(n) if j != i
        )
        for i in range(n)
    ]
    return SimStats(
        names=strategy_names,
        h2h=h2h,
        total_wins=total_wins,
        total_played=total_played,
        n_games=n_games,
    )


if __name__ == "__main__":
    from ur.strategies import (
        RandomStrategy, ProgressStrategy, SafeStrategy,
        AggressiveStrategy, RosetteHunterStrategy, BalancedStrategy,
    )

    factories = [
        lambda rng: RandomStrategy(rng),
        lambda rng: ProgressStrategy(rng),
        lambda rng: SafeStrategy(rng),
        lambda rng: AggressiveStrategy(rng),
        lambda rng: RosetteHunterStrategy(rng),
        lambda rng: BalancedStrategy(rng),
    ]
    names = ["Random", "Progress", "Safe", "Aggressive", "RosetteHunter", "Balanced"]

    print("Simulating Royal Game of Ur (round-robin)...")
    stats = simulate(factories, names, n_games=4_000)
    print(stats)
