# strat_hacking

Strategy simulation and analysis engine for the board game **Spots**.

## Project layout

```
strat_hacking/
└── spots/
    ├── game.py          # Core data classes: DogCard, PlayerState, Pool
    ├── tricks.py        # All 22 trick implementations + registry + deal_tricks()
    ├── strategies.py    # Strategy interface + 6 concrete strategies
    ├── sim.py           # run_game(), simulate(), run_game_detailed()
    ├── prob.py          # Exact/MC bust probability math + treat_value()
    ├── analysis.py      # Matplotlib plots (save to PNG, run standalone)
    ├── data/
    │   └── dogs.json    # Full 32-dog deck with spaces[] and paw_prints
    └── notebooks/
        ├── spots_sim.ipynb
        ├── dog_analysis.ipynb
        └── dog_entry.ipynb
```

## Game rules (summary)

- **Win**: first to score 6 dogs
- Each player starts with 3 dogs; draw replacements to keep at 3 (max 6)
- Each turn: pick a face-up trick → execute → flip it face-down
- When all tricks are face-down, flip all up and place 1 treat each from pool
- **Bust**: yard sum > 7 → all dice on dogs + in yard cleared
- **Shared limits**: 20 treat tokens, 40 dice total
- **Paw prints**: some dogs grant paw prints which boost certain tricks (beg, hunt, dig, bolt)

## Trick colours

| Colour | Tricks | Effect type |
|--------|--------|-------------|
| Always | Howl, Roll Over | draw dog / re-use buried dice |
| Green | Beg, Chew, Gobble, Play Dead, Stay | treat economy |
| Blue | Fetch, Guard, Hunt, Scavenge, Search | choose-your-dice |
| Yellow | Walk, Track, Trot, Retrieve, Dig | small controlled rolls |
| Purple | Run, Sprint, Chase, Bolt, Dogpile | press-your-luck chains |

One trick per colour is dealt each game (plus both Always tricks) = 6 tricks total.

## Strategy interface (BaseStrategy)

All strategies inherit from `BaseStrategy` and override relevant hooks:

- `choose_trick(player, tricks)` — pick which face-up trick to use
- `assign_die(die, player)` → DogCard | None — which dog gets this die
- `should_continue(player, dice_so_far, trick)` → bool — keep rolling?
- `choose_value(roll, player)` → int — for fetch/guard
- `choose_dice_subset(roll, player, keep_n)` → list — for hunt/track
- `should_discard_die(die, player)` → bool — for scavenge
- `choose_dice_subset_sum(roll, player, target_sum)` → list — for search
- `should_reroll(roll, player)` → bool — for track (costs 1 treat)
- `trot_move(player)` — reposition an already-placed die
- `dig_target(player)` → (idx, delta) — nudge a buried die
- `dogpile_take(player)` → int | None — pull a die off a dog/yard

## Implemented strategies

| Name | Core idea |
|------|-----------|
| `RandomStrategy` | Uniform random on every decision. Baseline. |
| `OneAtATimeStrategy` | Complete one dog before touching the next; bust-aware stopping |
| `FullPackStrategy` | Maximize to 6 dogs; spread dice for max placement surface |
| `TreatGamblerStrategy` | Accumulate treats → splurge on rolling chains with rerolls |
| `FastAndLooseStrategy` | Always roll more; accepts busts as cost of speed |
| `BustAwareStrategy` | Exact bust probability math drives every rolling decision |

## Running simulations

```python
from spots.sim import simulate
from spots.strategies import BustAwareStrategy, OneAtATimeStrategy

stats = simulate(
    [lambda rng: BustAwareStrategy(rng), lambda rng: OneAtATimeStrategy(rng)],
    ['BustAware', 'OneAtATime'],
    n_games=10_000,
)
print(stats)
```

## Probability utilities (prob.py)

- `bust_prob_no_placement(yard_total, n_dice)` — worst-case exact
- `bust_prob_with_placement(yard_total, n_dice, open_spaces)` — exact (≤7 dice) or MC
- `expected_placed(n_dice, open_spaces)` — expected placements, greedy strategy
- `treat_value(roll, yard_total, open_spaces)` — EV of spending a treat to reroll
- `monte_carlo_bust_prob(...)` — fallback for large n_dice

## Status

All core systems are in place and functional. The notebooks and PNGs are exploratory outputs from earlier analysis sessions. Next work is likely new strategies, parameter tuning, or deeper dog-card analysis.
