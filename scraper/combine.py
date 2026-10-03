"""Stage 2: combine one-way legs into trips and pick which ones to re-price."""

from __future__ import annotations

import heapq
from datetime import date

from .models import Fare, LegKey, Search, Trip
from .planner import date_pairs, outbound_dates

# Per date pair, only the K cheapest legs in each direction can produce top trips.
LEGS_PER_DATE = 40


def build_trips(search: Search, fares: dict[LegKey, Fare | None], today: date) -> list[Trip]:
    """All priced trips for a search, cheapest first. Legs missing from `fares` are skipped."""
    if search.trip_type == "one-way":
        trips = []
        for d in outbound_dates(search, today):
            for o in search.origins:
                for dest in search.destinations:
                    key = LegKey(o, dest, d, search.currency)
                    fare = fares.get(key)
                    if fare is not None:
                        trips.append(Trip(out=key, out_fare=fare))
        trips.sort(key=lambda t: t.final_price)
        return trips

    def cheapest(day: date, froms: list[str], tos: list[str]) -> list[tuple[LegKey, Fare]]:
        found = []
        for a in froms:
            for b in tos:
                if a == b:
                    continue
                key = LegKey(a, b, day, search.currency)
                fare = fares.get(key)
                if fare is not None:
                    found.append((key, fare))
        return heapq.nsmallest(LEGS_PER_DATE, found, key=lambda kf: kf[1].price)

    out_cache: dict[date, list] = {}
    ret_cache: dict[date, list] = {}
    trips = []
    for out_day, ret_day in date_pairs(search, today):
        if out_day not in out_cache:
            out_cache[out_day] = cheapest(out_day, search.origins, search.destinations)
        if ret_day not in ret_cache:
            ret_cache[ret_day] = cheapest(ret_day, search.destinations, search.origins)
        for ok, of in out_cache[out_day]:
            for rk, rf in ret_cache[ret_day]:
                trips.append(Trip(out=ok, out_fare=of, ret=rk, ret_fare=rf))
    trips.sort(key=lambda t: t.separate_total)
    return trips


def select_for_repricing(
    trips: list[Trip], search: Search, settings: dict, keep_keys: set[str] = frozenset()
) -> list[Trip]:
    """Trips to re-price as a single ticket, in priority order, capped per search.

    0. Trips that were available deals last run (keep_keys), so a cheap single
       ticket is not lost just because its separate-ticket total went up.
    1. The N cheapest by separate-ticket total.
    2. Anything within cap x factor (so every potential deal gets a single-ticket check).
    3. The cheapest same-airport-pair trips per (origin, destination), because a
       round-trip ticket is often far cheaper than two one-ways on the same route.
    """
    if search.trip_type == "one-way":
        return []
    top_n = int(settings["reprice_top_n"])
    limit = search.price_cap * float(settings["reprice_cap_factor"])
    per_pair = int(settings["reprice_per_pair"])
    max_total = int(settings["reprice_max_per_search"])

    chosen: dict[str, Trip] = {}

    def add(t: Trip) -> bool:
        if len(chosen) >= max_total:
            return False
        chosen.setdefault(t.key, t)
        return True

    for t in trips:
        if t.key in keep_keys:
            add(t)
    for t in trips[:top_n]:
        add(t)
    for t in trips:  # sorted, so stop at the first one above the limit
        if t.separate_total > limit or not add(t):
            break
    pair_counts: dict[tuple[str, str], int] = {}
    for t in trips:
        if t.itinerary_kind != "round-trip":
            continue
        pair = (t.out.origin, t.out.destination)
        if pair_counts.get(pair, 0) >= per_pair:
            continue
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        if not add(t):
            break
    return list(chosen.values())


def itinerary_cache_key(trip: Trip) -> tuple:
    return (trip.itinerary_kind, trip.legs)


def is_deal(trip: Trip, search: Search) -> bool:
    return trip.final_price <= search.price_cap
