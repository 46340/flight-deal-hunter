"""Run the scraper.

    python -m scraper.run --dry-run     print planned searches and query count
    python -m scraper.run --mock        full run with fake prices, no network
    python -m scraper.run               real run (Google Flights)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from . import hooks
from .blocking import BlockDetector, BlockedError
from .combine import build_trips, is_deal, itinerary_cache_key, select_for_repricing
from .models import ConfigError, Fare, LegKey, Search
from .planner import RunPlan, plan_run
from .providers.base import EmptyResponse, NoFlights, Provider
from .store import active_deal_keys, empty_result, load_json, merge_run, write_json

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SETTINGS = {
    "max_searches_per_run": 800,
    "delay_min_s": 2,
    "delay_max_s": 5,
    "max_retries": 3,
    "block_threshold": 10,
    "reprice_top_n": 30,
    "reprice_cap_factor": 1.3,
    "reprice_per_pair": 2,
    "reprice_max_per_search": 60,
    "paid_fallback": {"enabled": False, "provider": "ignav", "spend_cap_usd": 10},
}


def load_settings(path: Path) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(load_json(path, {}))
    return settings


def load_searches(path: Path) -> tuple[list[Search], list[str]]:
    raw = load_json(path, {"searches": []})
    searches, errors, ids = [], [], set()
    for d in raw.get("searches", []):
        try:
            s = Search.from_dict(d)
        except ConfigError as exc:
            errors.append(str(exc))
            continue
        if s.id in ids:
            errors.append(f"duplicate search id {s.id}")
            continue
        ids.add(s.id)
        searches.append(s)
    return searches, errors


def load_airports() -> dict[str, dict]:
    data = load_json(ROOT / "web" / "data" / "airports.json", [])
    return {a["iata"]: a for a in data}


# Outcomes of a single query besides a Fare.
UNCONFIRMED = object()  # empty/unparseable reply: "no flights" only if no block follows
FAILED = object()  # errors after all retries: leg stays unsearched


@dataclass
class RunState:
    """What happened to every query this run."""

    fares: dict[LegKey, Fare | None] = field(default_factory=dict)  # None = no flights
    itineraries: dict[tuple, Fare | None] = field(default_factory=dict)
    queries: int = 0
    leg_errors: dict[LegKey, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)  # run-level (blocks, provider switches)
    blocked: bool = False
    provider_used: set[str] = field(default_factory=set)


class Runner:
    def __init__(self, providers: list[Provider], settings: dict, sleep: bool = True):
        self.providers = providers  # first is primary, the rest are fallbacks used only when blocked
        self.settings = settings
        self.sleep = sleep
        self.state = RunState()
        self.detector: BlockDetector = BlockDetector(int(settings["block_threshold"]))

    @property
    def provider(self) -> Provider | None:
        while self.providers and not self.providers[0].available():
            self.providers.pop(0)
        return self.providers[0] if self.providers else None

    def _pause(self) -> None:
        if self.sleep:
            time.sleep(random.uniform(float(self.settings["delay_min_s"]), float(self.settings["delay_max_s"])))

    def _forget_pending(self) -> int:
        dropped = self.detector.discard()
        for kind, key in dropped:
            if kind == "leg":
                self.state.fares.pop(key, None)
            elif kind == "itinerary":
                self.state.itineraries.pop(key, None)
        return len(dropped)

    def _on_blocked(self, reason: str) -> bool:
        """Switch to the next provider if any. Returns False when the run must stop."""
        name = self.providers[0].name if self.providers else "?"
        n = self._forget_pending()
        self.state.errors.append(f"{name} blocked: {reason} ({n} unconfirmed replies discarded)")
        if self.providers:
            self.providers.pop(0)
        if self.provider is None:
            self.state.blocked = True
            return False
        self.state.errors.append(f"switched to {self.provider.name}")
        return True

    def _call(self, kind: str, key, fn):
        """One query with retries, block detection and fallback.

        Returns a Fare, None (confirmed no flights), UNCONFIRMED or FAILED.
        Raises BlockedError when every provider is blocked.
        """
        retries = int(self.settings["max_retries"])
        while True:
            provider = self.provider
            if provider is None:
                raise BlockedError("no provider available")
            switched = False
            for attempt in range(retries + 1):
                if self.state.queries:
                    self._pause()
                self.state.queries += 1
                self.state.provider_used.add(provider.name)
                try:
                    fare = fn(provider)
                except NoFlights:
                    self.detector.ok()
                    return None
                except EmptyResponse:
                    if self.detector.empty((kind, key)):
                        if not self._on_blocked(f"{self.detector.threshold} empty replies in a row"):
                            raise BlockedError("empty replies") from None
                        switched = True
                        break
                    return UNCONFIRMED
                except BlockedError as exc:
                    if not self._on_blocked(str(exc)):
                        raise
                    switched = True
                    break
                except Exception as exc:  # network errors, parser crashes
                    if attempt < retries:
                        if self.sleep:
                            time.sleep(2 ** (attempt + 1))
                        continue
                    msg = f"{type(exc).__name__}: {exc}"[:200]
                    if kind == "leg":
                        self.state.leg_errors[key] = msg
                    else:
                        self.state.errors.append(f"re-price {key[0]}: {msg}")
                    # Repeated hard failures also look like a block.
                    if self.detector.empty(("failed", key)):
                        if not self._on_blocked(f"{self.detector.threshold} failed replies in a row"):
                            raise BlockedError(msg) from None
                    return FAILED
                else:
                    self.detector.ok()
                    return fare
            if not switched:
                return FAILED
            # provider switched: retry the same query on the next one

    def fetch_legs(self, legs: list[LegKey], log=print) -> None:
        for i, leg in enumerate(legs, 1):
            result = self._call("leg", leg, lambda p: p.one_way(leg))
            if result is UNCONFIRMED:
                self.state.fares[leg] = None  # removed again if a block follows
            elif result is not FAILED:
                self.state.fares[leg] = result
            if i % 50 == 0:
                log(f"  stage 1: {i}/{len(legs)} legs")

    def reprice(self, trips) -> bool:
        """Re-price trips as single tickets. Returns False if interrupted by a block."""
        for t in trips:
            ck = itinerary_cache_key(t)
            if ck not in self.state.itineraries:
                try:
                    result = self._call("itinerary", ck, lambda p: p.itinerary(t.legs, t.itinerary_kind))
                except BlockedError:
                    return False
                if result is FAILED:
                    continue
                self.state.itineraries[ck] = None if result is UNCONFIRMED else result
            t.single = self.state.itineraries.get(ck)
        return True

    def finish(self) -> None:
        """Settle replies still waiting for confirmation at the end of the run."""
        if self.state.blocked:
            self._forget_pending()
        else:
            self.detector.ok()


def now_id() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_plan(plan: RunPlan, searches: list[Search], today: date) -> None:
    print(f"Plan for {today.isoformat()}")
    for s in searches:
        if not s.is_active(today):
            why = "paused" if s.status != "active" else f"expired {s.expires.isoformat()}"
            print(f"  - {s.id}: inactive ({why})")
    for s in plan.included:
        legs = plan.search_legs[s.id]
        print(
            f"  + {s.id}: {s.trip_type}, {len(s.origins)} origins x {len(s.destinations)} destinations, "
            f"{s.earliest_out} to {s.latest_return}, stay {s.min_stay}-{s.max_stay} d, cap {s.price_cap:g} {s.currency}, "
            f"{len(legs)} legs"
        )
    for s, why in plan.skipped:
        print(f"  ! {s.id}: skipped, {why}")
    total_legs = sum(len(v) for v in plan.search_legs.values())
    print(
        f"Stage 1: {len(plan.legs)} unique legs ({total_legs - len(plan.legs)} shared legs deduplicated)\n"
        f"Stage 2: up to {plan.stage2_reserve} re-pricing queries\n"
        f"Total: up to {plan.total_queries} queries, about {plan.est_seconds / 60:.0f} min"
    )


def execute(
    searches: list[Search],
    settings: dict,
    providers: list[Provider],
    data_dir: Path,
    today: date,
    sleep: bool = True,
    log=print,
) -> dict:
    run_id = now_id()
    plan = plan_run(searches, today, settings)
    runner = Runner(list(providers), settings, sleep=sleep)
    results_dir = data_dir / "results"

    log(f"Run {run_id}: {len(plan.included)} searches, {len(plan.legs)} legs")
    try:
        runner.fetch_legs(plan.legs, log=log)
    except BlockedError:
        log("  blocked during stage 1, stopping")

    # Stage 2 for every search first, then settle and write, so that a block
    # late in the run still discards every unconfirmed reply before we trust it.
    work = []
    for s in plan.included:
        path = results_dir / f"{s.id}.json"
        result = load_json(path, None) or empty_result(s)
        trips = build_trips(s, runner.state.fares, today)
        errors_before = len(runner.state.errors)
        before = runner.state.queries
        if s.trip_type == "one-way":
            stage2_ok = True
        elif runner.state.blocked:
            stage2_ok = False
        else:
            chosen = select_for_repricing(trips, s, settings, keep_keys=active_deal_keys(result))
            stage2_ok = runner.reprice(chosen)
        stage2_errors = runner.state.errors[errors_before:]
        work.append((s, path, result, trips, stage2_ok, stage2_errors, runner.state.queries - before))
    runner.finish()

    fares = runner.state.fares
    summaries = []
    for s, path, result, trips, stage2_ok, stage2_errors, stage2_queries in work:
        legs = plan.search_legs[s.id]
        answered_legs = [leg for leg in legs if leg in fares]
        fully = len(answered_legs) == len(legs)
        leg_errors = [f"{leg.label()}: {runner.state.leg_errors[leg]}" for leg in legs if leg in runner.state.leg_errors]
        # Drop single-ticket prices whose replies were discarded after a block.
        for t in trips:
            if t.single is not None and itinerary_cache_key(t) not in runner.state.itineraries:
                t.single = None
        trips = [t for t in trips if all(leg in fares and fares[leg] is not None for leg in t.legs)]
        trips.sort(key=lambda t: t.final_price)

        complete = fully and stage2_ok
        if runner.state.blocked and not complete:
            status = "blocked"
        elif complete and not leg_errors and not stage2_errors:
            status = "ok"
        else:
            status = "partial"
        # Without a complete stage 2, separate-ticket prices may hide a cheaper
        # single ticket, so do not let this run mark anything unavailable.
        answered = {(k.origin, k.destination, k.date.isoformat()) for k in answered_legs} if stage2_ok else set()
        run_errors = [e for e in runner.state.errors if "blocked" in e or "switched" in e] if status != "ok" else []
        run = {
            "run": run_id,
            "searches": len(answered_legs) + len([leg for leg in legs if leg in runner.state.leg_errors]) + stage2_queries,
            "provider": "+".join(sorted(runner.state.provider_used)) or "none",
            "status": status,
            "errors": (run_errors + leg_errors + stage2_errors)[:10],
        }
        merge_run(result, s, run, trips, fully_searched=complete, answered=answered, today=today)
        write_json(path, result)
        deals = [t for t in trips if is_deal(t, s)]
        summaries.append({"search_id": s.id, "status": status, "deals": len(deals), "trips": len(trips)})
        log(f"  {s.id}: {status}, {len(trips)} trips, {len(deals)} deals")

    for s, why in plan.skipped:
        print(f"  ! {s.id}: skipped, {why}")
    total_legs = sum(len(v) for v in plan.search_legs.values())
    print(
        f"Stage 1: {len(plan.legs)} unique legs ({total_legs - len(plan.legs)} shared legs deduplicated)\n"
        f"Stage 2: up to {plan.stage2_reserve} re-pricing queries\n"
        f"Total: up to {plan.total_queries} queries, about {plan.est_seconds / 60:.0f} min"
    )


def execute(
    searches: list[Search],
    settings: dict,
    providers: list[Provider],
    data_dir: Path,
    today: date,
    sleep: bool = True,
    log=print,
) -> dict:
    run_id = now_id()
    plan = plan_run(searches, today, settings)
    runner = Runner(list(providers), settings, sleep=sleep)
    results_dir = data_dir / "results"

    log(f"Run {run_id}: {len(plan.included)} searches, {len(plan.legs)} legs")
    try:
        runner.fetch_legs(plan.legs, log=log)
    except BlockedError:
        log("  blocked during stage 1, stopping")
    # Unconfirmed empties left at the end are trusted only if the run was not blocked.
    if runner.state.blocked:
        for item in runner.detector.discard():
            runner._forget(item)
    else:
        runner.detector.ok()

    fares = runner.state.fares
    summaries = []
    for s in plan.included:
        path = results_dir / f"{s.id}.json"
        result = load_json(path, None) or empty_result(s)
        legs = plan.search_legs[s.id]
        answered_legs = [leg for leg in legs if leg in fares]
        fully = len(answered_legs) == len(legs)
        trips = build_trips(s, fares, today)
        before = runner.state.queries
        stage2_ok = True
        if not runner.state.blocked:
            chosen = select_for_repricing(trips, s, settings, keep_keys=active_deal_keys(result))
            stage2_ok = runner.reprice(chosen)
        else:
            stage2_ok = s.trip_type == "one-way"
        trips.sort(key=lambda t: t.final_price)

        if runner.state.blocked and not (fully and stage2_ok):
            status = "blocked"
        elif fully and stage2_ok and not runner.state.errors:
            status = "ok"
        else:
            status = "partial"
        # Without a complete stage 2, separate-ticket prices may hide a cheaper
        # single ticket, so do not let this run mark anything unavailable.
        answered = {(k.origin, k.destination, k.date.isoformat()) for k in answered_legs} if stage2_ok else set()
        run = {
            "run": run_id,
            "searches": sum(1 for leg in legs if leg in fares) + (runner.state.queries - before),
            "provider": "+".join(sorted(runner.state.provider_used)) or "none",
            "status": status,
            "errors": runner.state.errors[-10:],
        }
        merge_run(result, s, run, trips, fully_searched=fully and stage2_ok, answered=answered, today=today)
        write_json(path, result)
        deals = [t for t in trips if is_deal(t, s)]
        summaries.append({"search_id": s.id, "status": status, "deals": len(deals), "trips": len(trips)})
        log(f"  {s.id}: {status}, {len(trips)} trips, {len(deals)} deals")

    for s, why in plan.skipped:
        path = results_dir / f"{s.id}.json"
        result = load_json(path, None) or empty_result(s)
        result.setdefault("runs", []).append(
            {"run": run_id, "searches": 0, "provider": "none", "status": "skipped", "errors": [why]}
        )
        write_json(path, result)

    if runner.state.blocked:
        overall = "blocked"
    elif all(x["status"] == "ok" for x in summaries):
        overall = "ok"
    else:
        overall = "partial"
    summary = {
        "run": run_id,
        "status": overall,
        "queries": runner.state.queries,
        "provider": "+".join(sorted(runner.state.provider_used)) or "none",
        "searches": summaries,
        "errors": (runner.state.errors + [f"{k.label()}: {v}" for k, v in runner.state.leg_errors.items()])[:20],
    }
    runs = load_json(data_dir / "runs.json", {"runs": []})
    runs["runs"] = (runs.get("runs", []) + [summary])[-400:]
    write_json(data_dir / "runs.json", runs)
    hooks.on_run_complete(summary)
    return summary


def build_providers(args, settings: dict) -> list[Provider]:
    if args.mock:
        from .providers.mock import MockProvider

        return [MockProvider(load_airports(), seed=args.seed, block_after=args.mock_block_after)]
    from .providers.google import GoogleFlightsProvider

    providers: list[Provider] = [GoogleFlightsProvider()]
    if settings.get("paid_fallback", {}).get("enabled"):
        from .providers.paid import PaidApiProvider

        providers.append(PaidApiProvider.from_env(settings, ROOT / "data" / "spend.json"))
    return providers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scraper.run", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    parser.add_argument("--mock", action="store_true", help="use fake prices, no network, no delays")
    parser.add_argument("--seed", type=int, default=0, help="mock price seed")
    parser.add_argument("--mock-block-after", type=int, help="mock: simulate a block after N queries")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "searches.json")
    parser.add_argument("--settings", type=Path, default=ROOT / "config" / "settings.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--today", type=date.fromisoformat, help="pretend today is this date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    today = args.today or datetime.now(timezone.utc).date()
    settings = load_settings(args.settings)
    searches, errors = load_searches(args.config)
    for e in errors:
        print(f"config error: {e}", file=sys.stderr)

    plan = plan_run(searches, today, settings)
    print_plan(plan, searches, today)
    if args.dry_run:
        return 0
    if not plan.included:
        print("Nothing to do.")
        return 0

    summary = execute(searches, settings, build_providers(args, settings), args.data_dir, today,
                      sleep=not args.mock)
    print(json.dumps({k: summary[k] for k in ("status", "queries", "provider")}))
    return 0 if summary["status"] != "blocked" else 2


if __name__ == "__main__":
    sys.exit(main())
