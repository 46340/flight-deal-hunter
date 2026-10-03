"""Read, merge and write data/results/<search_id>.json and data/runs.json.

Only compact summaries are stored, never raw provider responses.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Search, Trip

MAX_RUN_ENTRIES = 400  # roughly 4 months at 3 runs per day


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def empty_result(search: Search) -> dict:
    return {"search_id": search.id, "currency": search.currency, "deals": [], "cheapest_per_run": [], "runs": []}


def trip_summary(trip: Trip) -> dict:
    s = {
        "out_date": trip.out.date.isoformat(),
        "out_from": trip.out.origin,
        "out_to": trip.out.destination,
        "price": round(trip.final_price, 2),
        "ticket_type": trip.ticket_type,
        "airlines": trip.airlines,
        "links": trip.links,
    }
    if trip.ret is not None:
        s.update(ret_date=trip.ret.date.isoformat(), ret_from=trip.ret.origin, ret_to=trip.ret.destination)
        s["separate_price"] = round(trip.separate_total, 2)
    return s


def deal_legs(d: dict) -> list[tuple[str, str, str]]:
    legs = [(d["out_from"], d["out_to"], d["out_date"])]
    if d.get("ret_date"):
        legs.append((d["ret_from"], d["ret_to"], d["ret_date"]))
    return legs


def active_deal_keys(result: dict) -> set[str]:
    return {d["key"] for d in result.get("deals", []) if d.get("available")}


def merge_run(
    result: dict,
    search: Search,
    run: dict,
    trips: list[Trip],
    fully_searched: bool,
    answered: set[tuple[str, str, str]],
    today: date,
) -> dict:
    """Fold one run into a search's result file.

    trips: every priced trip built this run (any price).
    fully_searched: every planned leg for this search got a real answer.
    answered: (origin, destination, iso date) of legs that got a real answer this run
        (a fare or a confirmed "no flights"). Only a deal whose legs are all answered
        can flip to unavailable; legs skipped because of a block never count.
    """
    run_id = run["run"]
    result["currency"] = search.currency
    deals = {d["key"]: d for d in result.get("deals", [])}

    current = set()
    for t in trips:
        if t.final_price > search.price_cap:
            continue
        current.add(t.key)
        entry = deals.get(t.key, {"key": t.key, "first_seen": run_id})
        entry.update(trip_summary(t))
        entry["last_seen"] = run_id
        entry["available"] = True
        deals[t.key] = entry

    for key, d in deals.items():
        if key in current:
            continue
        if date.fromisoformat(d["out_date"]) < today:
            d["available"] = False
        elif all(leg in answered for leg in deal_legs(d)):
            d["available"] = False
        # otherwise not checked this run: leave as it was

    result["deals"] = sorted(deals.values(), key=lambda d: (d["price"], d["out_date"]))

    if fully_searched and trips and run["status"] in ("ok", "partial"):
        cheapest = min(trips, key=lambda t: t.final_price)
        entry = {"run": run_id, **trip_summary(cheapest)}
        entry.pop("links", None)
        result.setdefault("cheapest_per_run", []).append(entry)
        result["cheapest_per_run"] = result["cheapest_per_run"][-MAX_RUN_ENTRIES:]

    result.setdefault("runs", []).append(run)
    result["runs"] = result["runs"][-MAX_RUN_ENTRIES:]
    result["updated"] = run_id
    return result
