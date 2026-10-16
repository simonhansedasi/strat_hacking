from __future__ import annotations
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class VineCard:
    name: str
    red: int            # red grape value produced on harvest
    white: int          # white grape value produced on harvest
    needs_trellis: bool
    needs_irrigation: bool

    @property
    def planting_value(self) -> int:
        return self.red + self.white


@dataclass(frozen=True)
class OrderCard:
    name: str
    requirements: tuple  # tuple of (wine_type, min_value) pairs
    vp: int
    residual: int


VINE_DECK: list[VineCard] = [
    # No prereqs — easy to plant early
    VineCard("Pinot",         red=1, white=1, needs_trellis=False, needs_irrigation=False),
    VineCard("Pinot Grigio",  red=0, white=1, needs_trellis=False, needs_irrigation=False),
    VineCard("Trebbiano",     red=1, white=0, needs_trellis=False, needs_irrigation=False),
    VineCard("Sangiovese",    red=1, white=0, needs_trellis=False, needs_irrigation=False),
    VineCard("Vermentino",    red=0, white=1, needs_trellis=False, needs_irrigation=False),
    # Needs trellis only
    VineCard("Merlot",        red=2, white=0, needs_trellis=True,  needs_irrigation=False),
    VineCard("Cabernet",      red=2, white=0, needs_trellis=True,  needs_irrigation=False),
    VineCard("Syrah",         red=3, white=0, needs_trellis=True,  needs_irrigation=False),
    VineCard("Tempranillo",   red=2, white=1, needs_trellis=True,  needs_irrigation=False),
    VineCard("Nebbiolo",      red=3, white=0, needs_trellis=True,  needs_irrigation=False),
    # Needs irrigation only
    VineCard("Chardonnay",    red=0, white=2, needs_trellis=False, needs_irrigation=True),
    VineCard("Riesling",      red=0, white=2, needs_trellis=False, needs_irrigation=True),
    VineCard("Gewurztraminer",red=0, white=3, needs_trellis=False, needs_irrigation=True),
    VineCard("Sauvignon",     red=1, white=2, needs_trellis=False, needs_irrigation=True),
    VineCard("Viognier",      red=0, white=3, needs_trellis=False, needs_irrigation=True),
    # Needs both
    VineCard("Malvasia",      red=2, white=2, needs_trellis=True,  needs_irrigation=True),
    VineCard("Grenache",      red=3, white=1, needs_trellis=True,  needs_irrigation=True),
    VineCard("Mourvedre",     red=1, white=3, needs_trellis=True,  needs_irrigation=True),
    VineCard("Primitivo",     red=3, white=2, needs_trellis=True,  needs_irrigation=True),
    VineCard("Zinfandel",     red=2, white=3, needs_trellis=True,  needs_irrigation=True),
]

ORDER_DECK: list[OrderCard] = [
    # Single red wine
    OrderCard("Bistro",        (("red", 2),),                          vp=1, residual=0),
    OrderCard("Trattoria",     (("red", 3),),                          vp=2, residual=1),
    OrderCard("Osteria",       (("red", 4),),                          vp=2, residual=1),
    OrderCard("Enoteca",       (("red", 5),),                          vp=3, residual=2),
    OrderCard("Ristorante",    (("red", 6),),                          vp=4, residual=2),
    # Single white wine
    OrderCard("Cafe",          (("white", 2),),                        vp=1, residual=0),
    OrderCard("Brasserie",     (("white", 3),),                        vp=2, residual=1),
    OrderCard("Winebar",       (("white", 4),),                        vp=2, residual=1),
    OrderCard("Sommelier",     (("white", 5),),                        vp=3, residual=2),
    OrderCard("Chateau",       (("white", 6),),                        vp=4, residual=2),
    # Mixed (red + white)
    OrderCard("Auberge",       (("red", 2), ("white", 2)),             vp=3, residual=1),
    OrderCard("Taverna",       (("red", 3), ("white", 3)),             vp=4, residual=2),
    OrderCard("Cellar Door",   (("red", 4), ("white", 2)),             vp=4, residual=2),
    OrderCard("Vineyard Tour", (("red", 2), ("white", 4)),             vp=4, residual=2),
    OrderCard("Grand Cru",     (("red", 5), ("white", 4)),             vp=6, residual=3),
    # Rosé
    OrderCard("Patio",         (("rose", 4),),                         vp=3, residual=1),
    OrderCard("Garden Party",  (("rose", 5),),                         vp=4, residual=2),
    OrderCard("Terrasse",      (("rose", 6),),                         vp=5, residual=2),
    # Sparkling
    OrderCard("Celebration",   (("sparkling", 7),),                    vp=4, residual=2),
    OrderCard("Premier Cuvee", (("sparkling", 8),),                    vp=5, residual=3),
]


def make_vine_deck(rng: random.Random) -> list[VineCard]:
    deck = list(VINE_DECK)
    rng.shuffle(deck)
    return deck


def make_order_deck(rng: random.Random) -> list[OrderCard]:
    deck = list(ORDER_DECK)
    rng.shuffle(deck)
    return deck
