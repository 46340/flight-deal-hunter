from datetime import date

from scraper.models import Fare, LegKey, Trip
from scraper.store import empty_result, merge_run

from .conftest import make_search


def trip(day_out, day_ret, price):
    return Trip(out=LegKey("CPH", "JFK", date(2026, 11, day_out), "DKK"), out_fare=Fare(price, "DKK", ["SK"], "a"),
                ret=LegKey("JFK", "CPH", date(2026, 11, day_ret), "DKK"), ret_fare=Fare(0, "DKK", ["SK"], "b"))


def answered_for(*trips):
    return {(k.origin, k.destination, k.date.isoformat()) for t in trips for k in t.legs}


def run(rid, status="ok"):
    return {"run": rid, "searches": 1, "provider": "mock", "status": status, "errors": []}


TODAY = date(2026, 10, 3)


def test_first_and_last_seen():
    s = make_search(price_cap=2000)
    r = empty_result(s)
    t = trip(1, 5, 1500)
    merge_run(r, s, run("r1"), [t], True, answered_for(t), TODAY)
    merge_run(r, s, run("r2"), [trip(1, 5, 1400)], True, answered_for(t), TODAY)
    (d,) = r["deals"]
    assert (d["first_seen"], d["last_seen"], d["price"], d["available"]) == ("r1", "r2", 1400, True)
    assert d["ticket_type"] == "separate" and d["links"] == ["a", "b"]


def test_deal_goes_unavailable_only_when_rechecked():
    s = make_search(price_cap=2000)
    r = empty_result(s)
    t1, t2 = trip(1, 5, 1500), trip(2, 6, 1500)
    merge_run(r, s, run("r1"), [t1, t2], True, answered_for(t1, t2), TODAY)
    # r2: t1 was searched and is now too expensive; t2's legs were never searched (block)
    merge_run(r, s, run("r2", "blocked"), [trip(1, 5, 2500)], False, answered_for(t1), TODAY)
    status = {d["key"]: d["available"] for d in r["deals"]}
    assert status[t1.key] is False
    assert status[t2.key] is True
    assert {d["key"]: d["last_seen"] for d in r["deals"]}[t2.key] == "r1"


def test_departed_deals_marked_unavailable():
    s = make_search(price_cap=2000)
    r = empty_result(s)
    t = trip(1, 5, 1500)
    merge_run(r, s, run("r1"), [t], True, answered_for(t), TODAY)
    merge_run(r, s, run("r2"), [], True, set(), date(2026, 11, 2))
    assert r["deals"][0]["available"] is False


def test_cheapest_per_run_even_above_cap_and_skipped_when_incomplete():
    s = make_search(price_cap=100)
    r = empty_result(s)
    merge_run(r, s, run("r1"), [trip(1, 5, 900), trip(1, 6, 800)], True, set(), TODAY)
    assert r["deals"] == []
    assert [c["price"] for c in r["cheapest_per_run"]] == [800]
    merge_run(r, s, run("r2", "blocked"), [trip(1, 5, 50)], False, set(), TODAY)
    assert len(r["cheapest_per_run"]) == 1
    assert [x["status"] for x in r["runs"]] == ["ok", "blocked"]


def test_no_raw_responses_stored():
    s = make_search(price_cap=2000)
    r = empty_result(s)
    t = trip(1, 5, 1500)
    merge_run(r, s, run("r1"), [t], True, answered_for(t), TODAY)
    assert set(r) == {"search_id", "currency", "deals", "cheapest_per_run", "runs", "updated"}
