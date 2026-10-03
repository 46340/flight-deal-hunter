from datetime import date

import pytest

from scraper.models import ConfigError, LegKey
from scraper.planner import date_pairs, legs_for_search, outbound_dates, plan_run, return_dates

from .conftest import TODAY, make_search


def test_estimate_cases(estimate_cases):
    for case in estimate_cases:
        s = make_search(**case["search"])
        today = date.fromisoformat(case["today"])
        assert len(outbound_dates(s, today)) == case["outbound_dates"], case["name"]
        assert len(return_dates(s, today)) == case["return_dates"], case["name"]
        assert len(legs_for_search(s, today)) == case["expected"], case["name"]


def test_date_pairs_respect_min_max_stay_and_window():
    s = make_search(earliest_out="2026-11-01", latest_return="2026-11-10", min_stay=2, max_stay=4)
    pairs = date_pairs(s, TODAY)
    assert pairs
    for out, ret in pairs:
        assert 2 <= (ret - out).days <= 4
        assert out >= date(2026, 11, 1)
        assert ret <= date(2026, 11, 10)
    assert (date(2026, 11, 1), date(2026, 11, 3)) in pairs
    assert (date(2026, 11, 6), date(2026, 11, 10)) in pairs
    assert (date(2026, 11, 9), date(2026, 11, 10)) not in pairs  # stay 1 < min
    # every valid pair is present: out 1..8, stays limited by window end
    expected = sum(1 for o in range(1, 11) for st in range(2, 5) if o + st <= 10)
    assert len(pairs) == expected


def test_min_stay_zero_allows_same_day():
    s = make_search(earliest_out="2026-11-01", latest_return="2026-11-01", min_stay=0, max_stay=0)
    assert date_pairs(s, TODAY) == [(date(2026, 11, 1), date(2026, 11, 1))]


def test_past_dates_skipped():
    s = make_search(earliest_out="2026-11-01", latest_return="2026-11-10")
    assert outbound_dates(s, date(2026, 11, 5))[0] == date(2026, 11, 5)
    assert all(out >= date(2026, 11, 5) for out, _ in date_pairs(s, date(2026, 11, 5)))


def test_every_return_date_is_reachable():
    s = make_search(earliest_out="2026-11-01", latest_return="2026-11-30", min_stay=3, max_stay=5)
    used = {ret for _, ret in date_pairs(s, TODAY)}
    assert used == set(return_dates(s, TODAY))
    used_out = {out for out, _ in date_pairs(s, TODAY)}
    assert used_out == set(outbound_dates(s, TODAY))


def test_mixed_airports_produce_cross_legs():
    s = make_search(origins=["CPH", "HAM"], destinations=["JFK", "IAD"],
                    earliest_out="2026-11-01", latest_return="2026-11-02", min_stay=1, max_stay=1)
    legs = set(legs_for_search(s, TODAY))
    assert LegKey("CPH", "JFK", date(2026, 11, 1), "DKK") in legs
    assert LegKey("IAD", "HAM", date(2026, 11, 2), "DKK") in legs
    assert len(legs) == 8


def test_plan_dedups_across_searches(settings):
    a = make_search(id="a", origins=["CPH"], destinations=["JFK"], earliest_out="2026-11-01", latest_return="2026-11-05")
    b = make_search(id="b", origins=["CPH", "HAM"], destinations=["JFK"], earliest_out="2026-11-01", latest_return="2026-11-05")
    plan = plan_run([a, b], TODAY, settings)
    assert len(plan.search_legs["a"]) == 8
    assert len(plan.search_legs["b"]) == 16
    assert len(plan.legs) == 16  # a's 8 legs are all inside b
    assert len(set(plan.legs)) == len(plan.legs)


def test_plan_dedup_needs_same_currency(settings):
    a = make_search(id="a", currency="DKK")
    b = make_search(id="b", currency="EUR")
    plan = plan_run([a, b], TODAY, settings)
    assert len(plan.legs) == len(plan.search_legs["a"]) * 2


def test_plan_skips_inactive_and_over_cap(settings):
    settings["max_searches_per_run"] = 100
    paused = make_search(id="p", status="paused")
    expired = make_search(id="e", created="2026-09-01", tracking_days=10)
    big = make_search(id="big", origins=["CPH", "HAM", "BLL"], destinations=["JFK", "EWR"],
                      earliest_out="2026-11-01", latest_return="2026-11-20")
    small = make_search(id="small", earliest_out="2026-11-01", latest_return="2026-11-03")
    plan = plan_run([paused, expired, big, small], TODAY, settings)
    assert [s.id for s in plan.included] == ["small"]
    assert [s.id for s, _ in plan.skipped] == ["big"]
    assert plan.total_queries <= 100


def test_expiry_from_tracking_days():
    s = make_search(created="2026-10-01", tracking_days=10)
    assert s.expires == date(2026, 10, 11)
    assert s.is_active(date(2026, 10, 11))
    assert not s.is_active(date(2026, 10, 12))


@pytest.mark.parametrize("bad", [
    {"id": "../etc"},
    {"origins": ["CPHX"]},
    {"origins": []},
    {"min_stay": 5, "max_stay": 2},
    {"latest_return": "2026-10-01"},
    {"trip_type": "multi"},
])
def test_config_validation(bad):
    with pytest.raises(ConfigError):
        make_search(**bad)
