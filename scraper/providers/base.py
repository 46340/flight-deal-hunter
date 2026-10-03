"""Provider interface shared by Google Flights, the paid API and the mock."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..blocking import BlockedError  # noqa: F401  (re-exported for providers)
from ..models import Fare, LegKey


class NoFlights(Exception):
    """The source answered properly and there is nothing for this query."""


class EmptyResponse(Exception):
    """The source answered with nothing usable (empty or unparseable). Counts toward blocking."""


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def one_way(self, leg: LegKey) -> Fare:
        """Cheapest one-way fare. Raises NoFlights, EmptyResponse or BlockedError."""

    @abstractmethod
    def itinerary(self, legs: tuple[LegKey, ...], kind: str) -> Fare:
        """Cheapest single ticket covering all legs ("round-trip" or "multi-city").

        The returned price must be the total for the whole itinerary.
        """

    def available(self) -> bool:
        """False when the provider cannot take more requests (e.g. spend cap reached)."""
        return True
