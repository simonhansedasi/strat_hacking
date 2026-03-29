"""
Game simulation for Spots.

Game rules:
- Each player has a hand of dog cards (dealt from shuffled deck).
- Each round, each player chooses a face-up trick, executes it, flips trick face-down.
- When all tricks are face-down, flip all face-up again (new cycle).
  The last trick flipped face-up in each cycle gains 1 treat token.
  (Simplified: each trick gets +1 treat when cycle resets.)
- On execution: treats on a trick go to the player who uses it, then treats reset to 0.
- After a player's turn: score any completed dogs (remove from hand, add to scored pile).
- If a player busts: all dice on dogs and in yard are cleared (dogs reset, yard cleared).
- Win condition: first player to score 6 dogs wins.
- Ties broken by treats, then arbitrarily.

Dog dealing: each player is dealt a starting hand from the shuffled dog deck.
"""
from __future__ import annotations
import json
import os
import random
import copy
from dataclasses import dataclass, field
from typing import Optional

from spots.game import DogCard, PlayerState
from spots.tricks import deal_tricks
from spots.strategies import BaseStrategy

# ── Constants ──────────────────────────────────────────────────────────────────

WIN_DOGS       = 6       # dogs scored to win
STARTING_HAND  = 3       # dogs dealt to each player at start
MAX_DOGS       = 6       # max dogs a player can hold at once
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
    winner: int              # player index
    scores: list[int]        # dogs scored per player
    treats: list[int]        # treats at end per player
    turns: int               # total turns taken
    busts: list[int]         # bust count per player


# ── Single game ────────────────────────────────────────────────────────────────

def run_game(
    strategies: list[BaseStrategy],
    rng: random.Random,
    starting_hand: int = STARTING_HAND,
    win_dogs: int = WIN_DOGS,
) -> GameResult:
    n_players = len(strategies)

    # Deal dogs
    deck = load_dog_deck()
    rng.shuffle(deck)
    players = [PlayerState() for _ in range(n_players)]
    for player in players:
        for _ in range(starting_hand):
            if deck:
                player.dogs.append(deck.pop(0))

    # Deal tricks — shared trick row (all players see the same tricks)
    tricks = deal_tricks(rng)
    bust_counts = [0] * n_players
    turns = 0
    winner = None

    while winner is None:
        for pi, (player, strategy) in enumerate(zip(players, strategies)):
            turns += 1

            # Howl: if player has room for a dog, the howl trick can draw from deck
            # The deck is passed to trick functions

            # Choose a face-up trick
            face_up = [t for t in tricks if t['face_up']]
            if not face_up:
                # Shouldn't happen but be safe
                break
            chosen = strategy.choose_trick(player, tricks)

            # Collect treats from the trick tile
            player.treats += chosen.get('treats', 0)
            chosen['treats'] = 0

            # Execute trick
            fn = chosen['fn']
            # Some tricks need special kwargs
            fn_name = fn.__name__
            if fn_name == 'stay':
                facedown_count = sum(1 for t in tricks if not t['face_up'] and t is not chosen)
                fn(player, deck, strategy, rng, facedown_count=facedown_count)
            elif fn_name == 'dig':
                fn(player, deck, strategy, rng, all_players=players)
            else:
                fn(player, deck, strategy, rng)

            # Track bust
            if player.is_busted:
                bust_counts[pi] += 1
                player.bust()

            # Score completed dogs
            scored_now = player.score_complete_dogs()
            # Draw replacement dogs from deck
            while len(player.dogs) < min(starting_hand, MAX_DOGS) and deck:
                player.dogs.append(deck.pop(0))

            # Check win
            if player.scored >= win_dogs:
                winner = pi
                break

            # Flip trick face-down
            chosen['face_up'] = False

            # Cycle check: if all tricks are now face-down, flip all face-up
            # and award 1 treat to each (representing the treat tokens)
            if all(not t['face_up'] for t in tricks):
                for t in tricks:
                    t['face_up'] = True
                    t['treats'] += 1

        if winner is not None:
            break

        # Safety valve: avoid infinite games on weird states
        if turns > 2000:
            # Declare winner by score, break ties by treats
            winner = max(range(n_players),
                         key=lambda i: (players[i].scored, players[i].treats))
            break

    scores  = [p.scored  for p in players]
    treats  = [p.treats  for p in players]
    return GameResult(winner=winner, scores=scores, treats=treats,
                      turns=turns, busts=bust_counts)


# ── Multi-game simulation ──────────────────────────────────────────────────────

@dataclass
class SimStats:
    n_games:      int
    n_players:    int
    strategy_names: list[str]
    win_rates:    list[float]
    avg_score:    list[float]
    avg_treats:   list[float]
    avg_busts:    list[float]
    avg_turns:    float

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
    strategy_factories: list,          # list of callables: rng -> Strategy
    strategy_names: list[str],
    n_games: int = 10_000,
    seed: int = 42,
) -> SimStats:
    """
    Run n_games games, rotating which strategy occupies which seat.
    strategy_factories[i] is called each game with the game's rng.
    """
    rng = random.Random(seed)
    n = len(strategy_factories)

    wins      = [0]  * n
    scores    = [0.0] * n
    treats    = [0.0] * n
    busts     = [0.0] * n
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


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from spots.strategies import RandomStrategy, GreedyStrategy, ConservativeStrategy

    factories = [
        lambda rng: RandomStrategy(rng),
        lambda rng: GreedyStrategy(rng),
        lambda rng: ConservativeStrategy(rng),
        lambda rng: GreedyStrategy(rng),   # 2nd greedy as baseline
    ]
    names = ['Random', 'Greedy-1', 'Conservative', 'Greedy-2']

    print("Running 5,000 games…")
    stats = simulate(factories, names, n_games=5_000)
    print(stats)
