"""
Yahtzee simulation.

Yahtzee is single-player, so strategies are compared across independent game
runs rather than head-to-head. simulate() runs each strategy N times and
returns SimStats with score distributions and key performance metrics.

run_game()  — single game for one strategy; returns GameResult
simulate()  — N games per strategy; returns SimStats
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from yahtzee.game import (
    Scorecard, roll_dice, joker_forced_upper,
    N_DICE, MAX_ROLLS,
)
from yahtzee.strategies import BaseStrategy


# ── Game result ────────────────────────────────────────────────────────────────

@dataclass
class GameResult:
    score:            int
    upper_total:      int
    got_upper_bonus:  bool
    yahtzee_count:    int   # yahtzees scored including bonus rolls
    category_scores:  dict  # category -> points recorded


# ── Single game ────────────────────────────────────────────────────────────────

def run_game(strategy: BaseStrategy, rng: random.Random) -> GameResult:
    sc = Scorecard()
    yahtzee_count = 0

    while not sc.is_complete:
        # Roll 1 — no keep decision yet
        dice = roll_dice(N_DICE, rng)

        # Rolls 2 and 3 — keep decisions
        for roll_num in range(1, MAX_ROLLS):
            if sc.is_complete:
                break
            keep = strategy.choose_keep(dice, roll_num, sc)
            # Validate: keep must be a sub-multiset of dice
            keep = _validated_keep(keep, dice)
            n_reroll = N_DICE - len(keep)
            dice = list(keep) + roll_dice(n_reroll, rng)

        # Score a category
        cat = strategy.choose_category(dice, sc)
        if cat not in sc.available:
            # Fallback: pick any open category
            cat = sc.available[0]

        # Track yahtzees before scoring changes sc state
        if len(set(dice)) == 1:
            if sc.scores.get('yahtzee') == 50:
                yahtzee_count += 1   # bonus yahtzee
            elif cat == 'yahtzee':
                yahtzee_count += 1   # primary yahtzee

        sc.score_category(cat, dice)

    return GameResult(
        score=sc.total,
        upper_total=sc.upper_total,
        got_upper_bonus=sc.got_upper_bonus,
        yahtzee_count=yahtzee_count,
        category_scores=dict(sc.scores),
    )


def _validated_keep(keep: list[int], dice: list[int]) -> list[int]:
    """Clip keep to a valid sub-multiset of dice."""
    pool = list(dice)
    result = []
    for v in keep:
        if v in pool:
            result.append(v)
            pool.remove(v)
    return result


# ── Multi-game simulation ──────────────────────────────────────────────────────

@dataclass
class SimStats:
    n_games:         int
    strategy_names:  list[str]
    avg_score:       list[float]
    std_score:       list[float]
    median_score:    list[float]
    bonus_rate:      list[float]   # fraction of games earning upper bonus
    avg_yahtzees:    list[float]
    pct_250_plus:    list[float]   # fraction of games >= 250
    pct_300_plus:    list[float]   # fraction of games >= 300
    all_scores:      list[list[int]] = field(repr=False)   # raw scores per strategy

    def __str__(self):
        lines = [f"Yahtzee simulation: {self.n_games} games per strategy\n"]
        header = (
            f"  {'Strategy':<20}  {'Avg':>6}  {'Std':>6}  {'Med':>6}"
            f"  {'Bonus%':>7}  {'Ytz/g':>6}  {'>=250':>6}  {'>=300':>6}"
        )
        lines.append(header)
        lines.append('  ' + '-' * (len(header) - 2))
        for i, name in enumerate(self.strategy_names):
            lines.append(
                f"  {name:<20}  {self.avg_score[i]:>6.1f}  {self.std_score[i]:>6.1f}"
                f"  {self.median_score[i]:>6.0f}"
                f"  {self.bonus_rate[i]:>7.1%}  {self.avg_yahtzees[i]:>6.2f}"
                f"  {self.pct_250_plus[i]:>6.1%}  {self.pct_300_plus[i]:>6.1%}"
            )
        return '\n'.join(lines)


def simulate(
    strategy_factories: list,
    strategy_names: list[str],
    n_games: int = 10_000,
    seed: int = 42,
) -> SimStats:
    rng = random.Random(seed)
    n   = len(strategy_factories)

    all_scores   = [[] for _ in range(n)]
    upper_totals = [[]] * n
    bonus_hits   = [0]   * n
    yahtzee_sums = [0.0] * n
    upper_totals = [[] for _ in range(n)]

    for _ in range(n_games):
        for i, factory in enumerate(strategy_factories):
            game_rng = random.Random(rng.randint(0, 2**31))
            strategy = factory(game_rng)
            result   = run_game(strategy, game_rng)
            all_scores[i].append(result.score)
            upper_totals[i].append(result.upper_total)
            if result.got_upper_bonus:
                bonus_hits[i] += 1
            yahtzee_sums[i] += result.yahtzee_count

    def _std(scores: list[int]) -> float:
        if len(scores) < 2:
            return 0.0
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
        return math.sqrt(variance)

    def _median(scores: list[int]) -> float:
        s = sorted(scores)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

    return SimStats(
        n_games=n_games,
        strategy_names=strategy_names,
        avg_score    =[sum(s) / n_games for s in all_scores],
        std_score    =[_std(s)          for s in all_scores],
        median_score =[_median(s)       for s in all_scores],
        bonus_rate   =[b / n_games      for b in bonus_hits],
        avg_yahtzees =[y / n_games      for y in yahtzee_sums],
        pct_250_plus =[sum(s >= 250 for s in ss) / n_games for ss in all_scores],
        pct_300_plus =[sum(s >= 300 for s in ss) / n_games for ss in all_scores],
        all_scores   =all_scores,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from yahtzee.strategies import (
        RandomStrategy, GreedyStrategy, UpperBonusHunter,
        YahtzeeHunter, BalancedStrategy,
    )

    factories = [
        lambda rng: RandomStrategy(rng),
        lambda rng: GreedyStrategy(rng),
        lambda rng: UpperBonusHunter(rng),
        lambda rng: YahtzeeHunter(rng),
        lambda rng: BalancedStrategy(rng),
    ]
    names = ['Random', 'Greedy', 'UpperBonusHunter', 'YahtzeeHunter', 'Balanced']

    print("Running 10,000 games per strategy...")
    stats = simulate(factories, names, n_games=10_000)
    print(stats)
