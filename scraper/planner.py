"""Turn active searches into the set of one-way legs to query this run.

The query estimate is mirrored in web/js/budget.js; keep the two in sync
(tests/fixtures/estimate_cases.json is shared by both test suites).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import LegKey, Search

# Average seconds per query: mean of the 2 to 5 s delay plus request time.
SECONDS_PER_QUERY = 5.0


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def outbound_dates(search: Search, today: date) -> list[date]:
    start = max(search.earliest_out, today)
    if search.trip_type == "one-way":
        return date_range(start, search.latest_return)
    return date_range(start, search.latest_return - timedelta(days=search.min_stay))


def return_dates(search: Search, today: date) -> list[date]:
    if search.trip_type == "one-way":
        return []
    outs = outbound_dates(search, today)
    if not outs:
        return []
    start = outs[0] + timedelta(days=search.min_stay)
    end = min(search.latest_return, outs[-1] + timedelta(days=search.max_stay))
    return date_range(start, end)


def date_pairs(search: Search, today: date) -> list[tuple[date, date]]:
    """Valid (outbound, return) date pairs: stay between min and max, inside the window."""
    pairs = []
    for out in outbound_dates(search, today):
        for stay in range(search.min_stay, search.max_stay + 1):
            ret = out + timedelta(days=stay)
            if ret > search.latest_return:
                break
            pairs.append((out, ret))
    return pairs


def legs_for_search(search: Search, today: date) -> list[LegKey]:
    """|O| x |D| x outbound dates + |D| x |O| x return dates (same-airport pairs skipped)."""
    legs = []
    for d in outbound_dates(search, today):
        for o in search.origins:
            for dest in search.destinations:
                if o != dest:
                    legs.append(LegKey(o, dest, d, search.currency))
    for d in return_dates(search, today):
        for dest in search.destinations:
            for o in search.origins:
                if o != dest:
                    legs.append(LegKey(dest, o, d, search.currency))
    return legs


def stage2_reserve(search: Search, settings: dict) -> int:
    """Upper bound on re-pricing queries for one search."""
    if search.trip_type == "one-way":
        return 0
    return int(settings["reprice_max_per_search"])


@dataclass
class RunPlan:
    legs: list[LegKey] = field(default_factory=list)  # deduplicated, in query order
    search_legs: dict[str, list[LegKey]] = field(default_factory=dict)
    included: list[Search] = field(default_factory=list)
    skipped: list[tuple[Search, str]] = field(default_factory=list)
    stage2_reserve: int = 0

    @property
    def total_queries(self) -> int:
        return len(self.legs) + self.stage2_reserve

    @property
    def est_seconds(self) -> float:
        return self.total_queries * SECONDS_PER_QUERY


def plan_run(searches: list[Search], today: date, settings: dict) -> RunPlan:
    """Include active searches in config order while the per-run cap allows.

    Legs shared between searches are counted and fetched once.
    """
    cap = int(settings["max_searches_per_run"])
    plan = RunPlan()
    seen: set[LegKey] = set()
    for s in searches:
        if not s.is_active(today):
            continue
        legs = legs_for_search(s, today)
        if not legs:
            plan.skipped.append((s, "no dates left in window"))
            continue
        new = [leg for leg in dict.fromkeys(legs) if leg not in seen]
        reserve = stage2_reserve(s, settings)
        if len(plan.legs) + len(new) + plan.stage2_reserve + reserve > cap:
            plan.skipped.append((s, f"over per-run cap of {cap} queries"))
            continue
        plan.legs.extend(new)
        seen.update(new)
        plan.search_legs[s.id] = legs
        plan.included.append(s)
        plan.stage2_reserve += reserve
    return plan
