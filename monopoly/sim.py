"""
Monopoly game simulation.

run_game()  — single game, returns GameResult
simulate()  — multi-game stats, returns SimStats
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from monopoly.board import BOARD, Property, Railroad, Utility, JAIL_INDEX, GO_TO_JAIL
from monopoly.game import (
    PlayerState, PropertyState, GameState,
    roll_dice, _advance, _move_to, _land, _send_to_jail,
    resolve_bankruptcy, build_phase, unmortgage_phase,
)
from monopoly.cards import deal_decks
from monopoly.strategies import BaseStrategy


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_TURNS      = 500
STARTING_CASH  = 1500
WIN_CONDITION  = 'last_standing'   # or 'richest_at_timeout'


# ── Game result ────────────────────────────────────────────────────────────────

@dataclass
class GameResult:
    winner: int
    scores: list[int]          # final cash per player
    turns: int
    properties: list[int]      # properties owned per player at game end
    bankruptcies: int
    timed_out: bool


# ── Single game ────────────────────────────────────────────────────────────────

def run_game(
    strategies: list[BaseStrategy],
    rng: random.Random,
    max_turns: int = MAX_TURNS,
) -> GameResult:
    n = len(strategies)

    players = [PlayerState(cash=STARTING_CASH) for _ in range(n)]
    for i, p in enumerate(players):
        p.set_index(i)

    prop_states = [PropertyState() for _ in BOARD]
    chance_deck, cc_deck = deal_decks(rng)

    gs = GameState(
        players=players,
        prop_states=prop_states,
        chance_deck=chance_deck,
        cc_deck=cc_deck,
        rng=rng,
    )

    winner = None
    timed_out = False

    for turn in range(max_turns):
        gs.turn = turn
        for pi in range(n):
            player = players[pi]
            if player.bankrupt:
                continue

            # ── Jail handling ──────────────────────────────────────────────
            if player.in_jail:
                action = strategies[pi].jail_action(player, gs)
                if action == 'card' and player.get_out_cards > 0:
                    player.get_out_cards -= 1
                    player.in_jail = False
                    player.jail_turns = 0
                elif action == 'pay':
                    player.cash -= 50
                    player.in_jail = False
                    player.jail_turns = 0
                else:
                    # Roll for doubles
                    d1, d2 = roll_dice(rng)
                    if d1 == d2:
                        player.in_jail = False
                        player.jail_turns = 0
                        _advance(player, d1 + d2)
                        _land(player, gs, d1 + d2)
                    else:
                        player.jail_turns += 1
                        if player.jail_turns >= 3:
                            player.cash -= 50
                            player.in_jail = False
                            player.jail_turns = 0
                            _advance(player, d1 + d2)
                            _land(player, gs, d1 + d2)
                        # else: stay in jail, turn ends
            else:
                # ── Normal turn ────────────────────────────────────────────
                player.doubles_streak = 0
                while True:
                    d1, d2 = roll_dice(rng)
                    doubles = d1 == d2
                    total = d1 + d2

                    if doubles:
                        player.doubles_streak += 1
                        if player.doubles_streak >= 3:
                            _send_to_jail(player)
                            break
                    else:
                        player.doubles_streak = 0

                    _advance(player, total)

                    # Check for Go To Jail landing (also inside _land, but handle here first)
                    if player.position == GO_TO_JAIL:
                        _send_to_jail(player)
                        break

                    _land(player, gs, total)

                    # Buy opportunity
                    pos = player.position
                    ps = prop_states[pos]
                    if (ps.owner is None
                            and not ps.mortgaged
                            and isinstance(BOARD[pos], (Property, Railroad, Utility))):
                        if strategies[pi].should_buy(pos, player, gs):
                            price = BOARD[pos].price
                            if player.cash >= price:
                                ps.owner = pi
                                player.cash -= price

                    # Bankruptcy check
                    if player.cash < 0:
                        resolve_bankruptcy(player, gs, strategies[pi])
                        if player.bankrupt:
                            # Release all properties back to bank
                            for i, p2 in enumerate(prop_states):
                                if p2.owner == pi:
                                    p2.owner = None
                                    p2.houses = 0
                                    p2.mortgaged = False
                            break

                    if not doubles or player.in_jail:
                        break   # end turn unless doubles (and not just jailed)

            if player.bankrupt:
                active = [i for i, p in enumerate(players) if not p.bankrupt]
                if len(active) == 1:
                    winner = active[0]
                    break
                continue

            # ── Build and unmortgage phase ─────────────────────────────────
            build_phase(pi, player, gs, strategies[pi])
            unmortgage_phase(pi, player, gs, strategies[pi])

        if winner is not None:
            break
    else:
        # Timeout: richest player wins
        timed_out = True
        active = [i for i, p in enumerate(players) if not p.bankrupt]
        winner = max(active, key=lambda i: players[i].cash + sum(
            getattr(BOARD[j], 'mortgage_value', 0) * (1 if prop_states[j].mortgaged else 2)
            for j, ps in enumerate(prop_states) if ps.owner == i
        ))

    props_owned = [
        sum(1 for ps in prop_states if ps.owner == i)
        for i in range(n)
    ]

    return GameResult(
        winner=winner,
        scores=[p.cash for p in players],
        turns=gs.turn + 1,
        properties=props_owned,
        bankruptcies=sum(1 for p in players if p.bankrupt),
        timed_out=timed_out,
    )


# ── Multi-game simulation ─────────────────────────────────────────────────────

@dataclass
class SimStats:
    n_games:        int
    n_players:      int
    strategy_names: list[str]
    win_rates:      list[float]
    avg_cash:       list[float]
    avg_properties: list[float]
    avg_turns:      float
    timeout_rate:   float

    def __str__(self):
        lines = [f"Simulation: {self.n_games} games, {self.n_players} players",
                 f"  avg turns/game: {self.avg_turns:.1f}  "
                 f"timeout rate: {self.timeout_rate:.1%}"]
        for i, name in enumerate(self.strategy_names):
            lines.append(
                f"  {name:20s}  win={self.win_rates[i]:.1%}  "
                f"avg_cash={self.avg_cash[i]:.0f}  "
                f"avg_props={self.avg_properties[i]:.1f}"
            )
        return '\n'.join(lines)


def simulate(
    strategy_factories: list,
    strategy_names: list[str],
    n_games: int = 10_000,
    seed: int = 42,
) -> SimStats:
    rng = random.Random(seed)
    n = len(strategy_factories)

    wins         = [0]   * n
    cash         = [0.0] * n
    props        = [0.0] * n
    total_turns  = 0
    timeouts     = 0

    for _ in range(n_games):
        game_rng = random.Random(rng.randint(0, 2**31))
        strats = [f(game_rng) for f in strategy_factories]
        result = run_game(strats, game_rng)
        wins[result.winner] += 1
        total_turns += result.turns
        if result.timed_out:
            timeouts += 1
        for i in range(n):
            cash[i]  += result.scores[i]
            props[i] += result.properties[i]

    return SimStats(
        n_games=n_games,
        n_players=n,
        strategy_names=strategy_names,
        win_rates=[w / n_games for w in wins],
        avg_cash=[c / n_games for c in cash],
        avg_properties=[p / n_games for p in props],
        avg_turns=total_turns / n_games,
        timeout_rate=timeouts / n_games,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from monopoly.strategies import (
        AlwaysBuyStrategy, ColorFocusStrategy, OrangeRedStrategy,
        RailroadStrategy, CashHoarderStrategy,
    )

    factories = [
        lambda rng: AlwaysBuyStrategy(rng),
        lambda rng: OrangeRedStrategy(rng),
        lambda rng: ColorFocusStrategy(rng),
        lambda rng: RailroadStrategy(rng),
        lambda rng: CashHoarderStrategy(rng),
    ]
    names = ['AlwaysBuy', 'OrangeRed', 'ColorFocus', 'Railroad', 'CashHoarder']

    print("Running 5,000 games...")
    stats = simulate(factories, names, n_games=5_000)
    print(stats)
