"""
Game simulation for Spots.

Game rules:
- Each player has a hand of dog cards (dealt from shuffled deck).
- Each round, each player chooses a face-up trick, executes it, flips trick face-down.
- When all tricks are face-down, flip all face-up again (new cycle).
  When a cycle resets, 1 treat token is placed on each trick from the shared supply.
- On execution: treats on a trick go to the player who uses it, then treats reset to 0.
- After a player's turn: score any completed dogs (remove from hand, add to scored pile).
- If a player busts: all dice on dogs and in yard are cleared and returned to supply.
- Win condition: first player to score 6 dogs wins.

Hard limits enforced: 20 treat tokens, 40 dice (shared physical components).
"""
from __future__ import annotations
import json
import os
import random
from dataclasses import dataclass, field
from typing import Optional

from spots.game import DogCard, PlayerState, Pool
from spots.tricks import deal_tricks
from spots.strategies import BaseStrategy

# ── Constants ──────────────────────────────────────────────────────────────────

WIN_DOGS       = 6
STARTING_HAND  = 3
MAX_DOGS       = 6
DATA_DIR       = os.path.join(os.path.dirname(__file__), 'data')


# ── Dog deck loading ───────────────────────────────────────────────────────────

def load_dog_deck(path: str = None) -> list[DogCard]:
    if path is None:
        path = os.path.join(DATA_DIR, 'dogs.json')
    with open(path) as f:
        data = json.load(f)
    return [DogCard(name=d['name'], spaces=d['spaces'],
                    paw_prints=d.get('paw_prints', 0))
            for d in data]


# ── Game result ────────────────────────────────────────────────────────────────

@dataclass
class GameResult:
    winner: int
    scores: list[int]
    treats: list[int]
    turns: int
    busts: list[int]


# ── Pool helpers ───────────────────────────────────────────────────────────────

def _dice_in_use(players: list[PlayerState]) -> int:
    total = 0
    for p in players:
        for d in p.dogs:
            total += sum(d.filled)   # list[bool] — sum counts True
        total += len(p.yard)
    return total


def _return_dice_for_bust(player: PlayerState, pool: Pool) -> None:
    count = sum(sum(d.filled) for d in player.dogs) + len(player.yard)
    player.bust()
    pool.dice += count


def _return_dice_for_score(player: PlayerState, pool: Pool) -> int:
    complete = player.complete_dogs
    count = sum(sum(d.filled) for d in complete)
    scored = player.score_complete_dogs()
    pool.dice += count
    return scored


# ── Single game ────────────────────────────────────────────────────────────────

def run_game(
    strategies: list[BaseStrategy],
    rng: random.Random,
    starting_hand: int = STARTING_HAND,
    win_dogs: int = WIN_DOGS,
) -> GameResult:
    n_players = len(strategies)

    deck = load_dog_deck()
    rng.shuffle(deck)
    players = [PlayerState() for _ in range(n_players)]
    for player in players:
        for _ in range(starting_hand):
            if deck:
                player.dogs.append(deck.pop(0))

    pool = Pool(treats=20, dice=40 - _dice_in_use(players))
    tricks = deal_tricks(rng)
    bust_counts = [0] * n_players
    turns = 0
    winner = None

    while winner is None:
        for pi, (player, strategy) in enumerate(zip(players, strategies)):
            turns += 1

            face_up = [t for t in tricks if t['face_up']]
            if not face_up:
                break
            chosen = strategy.choose_trick(player, tricks)

            # Tile treats go to player; they were already drawn from pool when placed.
            player.treats += chosen.get('treats', 0)
            chosen['treats'] = 0

            # Execute trick
            fn = chosen['fn']
            fn_name = fn.__name__
            if fn_name == 'stay':
                facedown_count = sum(1 for t in tricks if not t['face_up'] and t is not chosen)
                fn(player, deck, strategy, rng, pool, facedown_count=facedown_count)
            elif fn_name == 'dig':
                fn(player, deck, strategy, rng, pool, all_players=players)
            else:
                fn(player, deck, strategy, rng, pool)

            # Handle bust
            if player.is_busted:
                bust_counts[pi] += 1
                _return_dice_for_bust(player, pool)

            # Score completed dogs, return their dice
            _return_dice_for_score(player, pool)

            # Draw replacement dogs
            while len(player.dogs) < min(starting_hand, MAX_DOGS) and deck:
                player.dogs.append(deck.pop(0))

            if player.scored >= win_dogs:
                winner = pi
                break

            # Flip trick face-down
            chosen['face_up'] = False

            # Cycle reset: flip all face-up and place 1 treat on each from supply
            if all(not t['face_up'] for t in tricks):
                for t in tricks:
                    t['face_up'] = True
                    if pool.treats > 0:
                        t['treats'] += 1
                        pool.treats -= 1

        if winner is not None:
            break

        if turns > 2000:
            winner = max(range(n_players),
                         key=lambda i: (players[i].scored, players[i].treats))
            break

    return GameResult(
        winner=winner,
        scores=[p.scored for p in players],
        treats=[p.treats for p in players],
        turns=turns,
        busts=bust_counts,
    )


# ── Multi-game simulation ──────────────────────────────────────────────────────

@dataclass
class SimStats:
    n_games:        int
    n_players:      int
    strategy_names: list[str]
    win_rates:      list[float]
    avg_score:      list[float]
    avg_treats:     list[float]
    avg_busts:      list[float]
    avg_turns:      float

    def __str__(self):
        lines = [f"Simulation: {self.n_games} games, {self.n_players} players"]
        for i, name in enumerate(self.strategy_names):
            lines.append(
                f"  {name:20s}  win={self.win_rates[i]:.1%}  "
                f"avg_score={self.avg_score[i]:.2f}  "
                f"avg_busts={self.avg_busts[i]:.2f}  "
                f"avg_treats={self.avg_treats[i]:.2f}"
            )
        lines.append(f"  avg turns/game: {self.avg_turns:.1f}")
        return '\n'.join(lines)


def simulate(
    strategy_factories: list,
    strategy_names: list[str],
    n_games: int = 10_000,
    seed: int = 42,
) -> SimStats:
    rng = random.Random(seed)
    n = len(strategy_factories)

    wins        = [0]   * n
    scores      = [0.0] * n
    treats      = [0.0] * n
    busts       = [0.0] * n
    total_turns = 0

    for _ in range(n_games):
        game_rng = random.Random(rng.randint(0, 2**31))
        strategies = [f(game_rng) for f in strategy_factories]
        result = run_game(strategies, game_rng)
        wins[result.winner] += 1
        total_turns += result.turns
        for i in range(n):
            scores[i] += result.scores[i]
            treats[i] += result.treats[i]
            busts[i]  += result.busts[i]

    return SimStats(
        n_games=n_games,
        n_players=n,
        strategy_names=strategy_names,
        win_rates=[w / n_games for w in wins],
        avg_score=[s / n_games for s in scores],
        avg_treats=[t / n_games for t in treats],
        avg_busts=[b / n_games for b in busts],
        avg_turns=total_turns / n_games,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from spots.strategies import RandomStrategy, GreedyStrategy, ConservativeStrategy

    factories = [
        lambda rng: RandomStrategy(rng),
        lambda rng: GreedyStrategy(rng),
        lambda rng: ConservativeStrategy(rng),
        lambda rng: GreedyStrategy(rng),
    ]
    names = ['Random', 'Greedy-1', 'Conservative', 'Greedy-2']

    print("Running 5,000 games…")
    stats = simulate(factories, names, n_games=5_000)
    print(stats)
