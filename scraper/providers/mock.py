"""Deterministic fake prices for offline end-to-end runs."""

from __future__ import annotations

import hashlib
import random
from urllib.parse import quote

from ..blocking import BlockedError
from ..geo import haversine_km
from ..models import Fare, LegKey
from .base import NoFlights, Provider

AIRLINES = ["SAS", "Norwegian", "Lufthansa", "KLM", "Delta", "United", "Icelandair", "Finnair", "British Airways"]


def google_flights_url(text: str) -> str:
    return "https://www.google.com/travel/flights?q=" + quote(text)


class MockProvider(Provider):
    name = "mock"

    def __init__(self, airports: dict[str, dict] | None = None, seed: int = 0, block_after: int | None = None):
        self.airports = airports or {}
        self.seed = seed
        self.block_after = block_after
        self.calls = 0

    def _rng(self, *parts) -> random.Random:
        h = hashlib.sha256(repr((self.seed, parts)).encode()).hexdigest()
        return random.Random(int(h[:16], 16))

    def _distance(self, a: str, b: str) -> float:
        pa, pb = self.airports.get(a), self.airports.get(b)
        if not pa or not pb:
            return 1500.0
        return haversine_km(pa["lat"], pa["lon"], pb["lat"], pb["lon"])

    def _tick(self) -> None:
        self.calls += 1
        if self.block_after is not None and self.calls > self.block_after:
            raise BlockedError("mock: simulated captcha")

    def one_way(self, leg: LegKey) -> Fare:
        self._tick()
        rng = self._rng("ow", leg)
        if rng.random() < 0.03:
            raise NoFlights(leg.label())
        base = 250 + self._distance(leg.origin, leg.destination) * 0.45
        price = round(base * rng.uniform(0.6, 1.7))
        return Fare(
            price=price,
            currency=leg.currency,
            airlines=rng.sample(AIRLINES, k=rng.choice([1, 1, 2])),
            url=google_flights_url(f"Flights from {leg.origin} to {leg.destination} on {leg.date} one way"),
        )

    def itinerary(self, legs: tuple[LegKey, ...], kind: str) -> Fare:
        self._tick()
        rng = self._rng("it", kind, legs)
        parts = []
        for leg in legs:
            r = self._rng("ow", leg)
            r.random()
            parts.append(round((250 + self._distance(leg.origin, leg.destination) * 0.45) * r.uniform(0.6, 1.7)))
        factor = rng.uniform(0.55, 1.05) if kind == "round-trip" else rng.uniform(0.8, 1.2)
        out, ret = legs[0], legs[-1]
        text = f"Flights from {out.origin} to {out.destination} on {out.date} returning {ret.date}"
        if kind == "multi-city":
            text = f"Multi-city {out.origin} to {out.destination} on {out.date}, {ret.origin} to {ret.destination} on {ret.date}"
        return Fare(
            price=round(sum(parts) * factor),
            currency=legs[0].currency,
            airlines=rng.sample(AIRLINES, k=rng.choice([1, 2])),
            url=google_flights_url(text),
        )
