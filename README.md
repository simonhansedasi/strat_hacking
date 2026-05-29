# StratHacking

Multi-game strategy simulation lab. Each game is a self-contained Python module. Simulate thousands of games and compare strategy win rates head-to-head.

## Games

### Spots

Dice-placement dog game. First to score 6 dogs wins. Bust risk (yard sum > 7) is the central tension.

6 strategies from random baseline to exact bust-probability math. Key finding: `BustAwareStrategy` uses per-decision expected-value calculations; `FastAndLooseStrategy` accepts busts as the price of speed.

### Monopoly

No trading, no auctions. Pure individual strategy: buy/build/jail/mortgage decisions. 5-player games have ~60% timeout rate — monopolies are hard to form without trading.

5 strategies from always-buy to railroad-focused cash hoarder.

### Yahtzee

Single-player scoring. Strategies compared by average total score across N independent games.

| Strategy        | Avg   | Std  | Bonus% | Ytz/g |
|-----------------|-------|------|--------|-------|
| Random          | 45.7  | 18.1 |   0.0% |  0.00 |
| Greedy          | 210.8 | 50.8 |   8.6% |  0.36 |
| UpperBonusHunter| 160.2 | 40.6 |   4.4% |  0.18 |
| YahtzeeHunter   | 155.2 | 66.1 |   2.4% |  0.58 |
| Balanced        | 201.0 | 46.6 |  36.3% |  0.18 |

Greedy wins on average. Balanced hits the upper bonus 4x more often. YahtzeeHunter has the highest variance.

### Qwixx

Multiplayer dice game (5-player head-to-head). Scoring is triangular: n crosses = n*(n+1)/2 points.

| Strategy     | Avg  | Std  | Win%  | Pen/g |
|--------------|------|------|-------|-------|
| Random       |  7.0 |  9.5 |  7.2% |  2.31 |
| Aggressive   |  9.0 | 10.4 |  6.7% |  2.53 |
| Conservative |  6.0 |  8.9 |  3.4% |  2.55 |
| LockHunter   |  3.4 | 13.3 |  7.1% |  3.01 |
| Balanced     | 27.2 | 14.7 | 72.4% |  1.81 |

Balanced dominates with 72.4% win rate. Key insight: consecutive crosses (gap=0) over jumping to higher positions. Triangular scoring means more total crosses beats any individual high-position cross.

## Running simulations

```python
from qwixx.sim import simulate
from qwixx.strategies import BalancedStrategy, AggressiveStrategy

stats = simulate(
    [lambda rng: BalancedStrategy(rng), lambda rng: AggressiveStrategy(rng)],
    ['Balanced', 'Aggressive'],
    n_games=20_000,
)
print(stats)
```

Or run any game directly: `python -m yahtzee.sim`, `python -m qwixx.sim`, etc.

## Stack

Python, NumPy, matplotlib, pandas
