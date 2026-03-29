"""
Core game objects for Spots.

Dog cards have fixed spaces showing required die values (1–6).
A space is filled when the matching die is placed on it.
Placing a die in the yard buries it — yard sum > 7 = bust.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import copy


@dataclass
class DogCard:
    name: str
    spaces: list[int]       # required die values, e.g. [1, 3, 3, 5]
    paw_prints: int = 0     # contributes to player's total paw print count
    filled: list[bool] = field(default_factory=list)

    def __post_init__(self):
        if not self.filled:
            self.filled = [False] * len(self.spaces)

    @property
    def open_spaces(self) -> list[int]:
        """Die values still needed."""
        return [v for v, f in zip(self.spaces, self.filled) if not f]

    @property
    def is_complete(self) -> bool:
        return all(self.filled)

    def place(self, value: int) -> bool:
        """Place a die on the first unfilled matching space. Returns True if placed."""
        for i, (v, f) in enumerate(zip(self.spaces, self.filled)):
            if v == value and not f:
                self.filled[i] = True
                return True
        return False

    def can_accept(self, value: int) -> bool:
        return value in self.open_spaces

    def reset(self):
        self.filled = [False] * len(self.spaces)

    def __repr__(self):
        spaces_str = ' '.join(
            f'[{v}]' if not f else f' {v} '
            for v, f in zip(self.spaces, self.filled)
        )
        return f"DogCard({self.name!r} | {spaces_str} | paws={self.paw_prints})"


@dataclass
class PlayerState:
    dogs: list[DogCard] = field(default_factory=list)
    yard: list[int] = field(default_factory=list)   # buried dice
    treats: int = 0
    scored: int = 0                                  # completed dogs total

    BUST_THRESHOLD = 7

    @property
    def yard_total(self) -> int:
        return sum(self.yard)

    @property
    def is_busted(self) -> bool:
        return self.yard_total > self.BUST_THRESHOLD

    @property
    def paw_prints(self) -> int:
        return sum(d.paw_prints for d in self.dogs)

    @property
    def incomplete_dogs(self) -> list[DogCard]:
        return [d for d in self.dogs if not d.is_complete]

    @property
    def complete_dogs(self) -> list[DogCard]:
        return [d for d in self.dogs if d.is_complete]

    def can_place(self, value: int) -> bool:
        """Can this die value be placed on any dog?"""
        return any(d.can_accept(value) for d in self.incomplete_dogs)

    def place_on_dog(self, value: int) -> bool:
        """Place die on first dog that accepts it. Returns True if placed."""
        for dog in self.incomplete_dogs:
            if dog.place(value):
                return True
        return False

    def bury(self, value: int) -> bool:
        """Add die to yard. Returns False (busted) if yard total now exceeds threshold."""
        self.yard.append(value)
        return not self.is_busted

    def bust(self):
        """Bust: discard all dice on dogs and in yard."""
        for dog in self.dogs:
            dog.reset()
        self.yard.clear()

    def score_complete_dogs(self) -> int:
        """Score all complete dogs, return count scored."""
        completed = self.complete_dogs
        for dog in completed:
            self.dogs.remove(dog)
        self.scored += len(completed)
        return len(completed)

    def all_open_spaces(self) -> list[int]:
        """All die values still needed across all incomplete dogs."""
        return [v for dog in self.incomplete_dogs for v in dog.open_spaces]


@dataclass
class Pool:
    """
    Shared physical components — hard limits enforced by the simulation.
    treats: tokens in the central supply (not held by any player or tile).
    dice:   dice currently available to roll (not placed on dogs or in yards).
    """
    treats: int = 20
    dice: int = 40
