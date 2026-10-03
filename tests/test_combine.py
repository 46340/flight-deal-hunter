from datetime import date, timedelta

from scraper.combine import build_trips, is_deal, select_for_repricing
from scraper.models import Fare, LegKey, Trip

from .conftest import TODAY, make_search


def leg(o, d, day, cur="DKK"):
    return LegKey(o, d, date(2026, 11, day), cur)


def fare(p):
    return Fare(price=p, currency="DKK", airlines=["X"], url=f"u{p}")


def test_build_return_trips_respect_stay_and_mix_airports():
    s = make_search(origins=["CPH", "HAM"], destinations=["JFK", "IAD"],
                    earliest_out="2026-11-01", latest_return="2026-11-05", min_stay=2, max_stay=3)
    fares = {
        leg("CPH", "JFK", 1): fare(1000),
        leg("IAD", "HAM", 4): fare(900),
        leg("IAD", "HAM", 2): fare(100),  # stay 1: too short
        leg("JFK", "CPH", 5): fare(1200),  # stay 4 from day 1: too long
        leg("HAM", "IAD", 2): None,  # no flights
    }
    trips = build_trips(s, fares, TODAY)
    assert [t.key for t in trips] == ["CPH-JFK-2026-11-01|IAD-HAM-2026-11-04"]
    assert trips[0].separate_total == 1900
    assert trips[0].itinerary_kind == "multi-city"


def test_build_trips_sorted_and_complete():
    s = make_search(origins=["CPH"], destinations=["JFK"], earliest_out="2026-11-01",
                    latest_return="2026-11-04", min_stay=1, max_stay=3)
    fares = {leg("CPH", "JFK", d): fare(1000 + d) for d in range(1, 4)}
    fares.update({leg("JFK", "CPH", d): fare(500 + d) for d in range(2, 5)})
    trips = build_trips(s, fares, TODAY)
    assert len(trips) == 6  # (1,2)(1,3)(1,4)(2,3)(2,4)(3,4)
    totals = [t.separate_total for t in trips]
    assert totals == sorted(totals)


def test_one_way_trips():
    s = make_search(trip_type="one-way", origins=["CPH", "HAM"], destinations=["JFK"],
                    earliest_out="2026-11-01", latest_return="2026-11-02")
    fares = {leg("CPH", "JFK", 1): fare(800), leg("HAM", "JFK", 2): fare(700), leg("CPH", "JFK", 2): None}
    trips = build_trips(s, fares, TODAY)
    assert [t.final_price for t in trips] == [700, 800]
    assert all(t.ticket_type == "single" for t in trips)
    assert select_for_repricing(trips, s, {}) == []


def test_final_price_is_min_of_single_and_separate():
    t = Trip(out=leg("CPH", "JFK", 1), out_fare=fare(1000), ret=leg("JFK", "CPH", 5), ret_fare=fare(1000))
    assert t.itinerary_kind == "round-trip"
    assert (t.final_price, t.ticket_type) == (2000, "separate")
    assert t.links == ["u1000", "u1000"]
    t.single = fare(1500)
    assert (t.final_price, t.ticket_type, t.links) == (1500, "single", ["u1500"])
    t.single = fare(2500)
    assert (t.final_price, t.ticket_type) == (2000, "separate")


def test_deal_detection_at_cap():
    s = make_search(price_cap=2000)
    t = Trip(out=leg("CPH", "JFK", 1), out_fare=fare(1000), ret=leg("JFK", "CPH", 5), ret_fare=fare(1000))
    assert is_deal(t, s)
    t.ret_fare = fare(1001)
    assert not is_deal(t, s)
    t.single = fare(1999)
    assert is_deal(t, s)


def _trips(n, start=1000, step=100, kind="round-trip"):
    out = []
    for i in range(n):
        dest = "JFK"
        back_to = "CPH" if kind == "round-trip" else "HAM"
        out.append(Trip(out=LegKey("CPH", dest, date(2026, 11, 1), "DKK"), out_fare=fare(start + i * step),
                        ret=LegKey(dest, back_to, date(2026, 11, 2) + timedelta(days=i), "DKK"), ret_fare=fare(0)))
    return out


def test_selection_top_n_and_near_cap(settings):
    settings.update(reprice_top_n=3, reprice_cap_factor=1.3, reprice_per_pair=0, reprice_max_per_search=100)
    s = make_search(price_cap=1500)
    trips = _trips(20)  # 1000, 1100, ... 2900
    chosen = select_for_repricing(trips, s, settings)
    prices = sorted(t.separate_total for t in chosen)
    assert prices == [p for p in range(1000, 2000, 100) if p <= 1950]  # top 3 + all <= 1950


def test_selection_respects_max(settings):
    settings.update(reprice_top_n=30, reprice_cap_factor=10, reprice_max_per_search=5)
    chosen = select_for_repricing(_trips(50), make_search(price_cap=1500), settings)
    assert len(chosen) == 5
    assert sorted(t.separate_total for t in chosen) == [1000, 1100, 1200, 1300, 1400]


def test_selection_adds_cheapest_round_trip_per_pair(settings):
    settings.update(reprice_top_n=2, reprice_cap_factor=0.1, reprice_per_pair=1, reprice_max_per_search=60)
    s = make_search(price_cap=100)
    rt_other_pair = Trip(out=LegKey("HAM", "IAD", date(2026, 11, 1), "DKK"), out_fare=fare(9000),
                         ret=LegKey("IAD", "HAM", date(2026, 11, 5), "DKK"), ret_fare=fare(0))
    trips = sorted(_trips(5) + [rt_other_pair], key=lambda t: t.separate_total)
    chosen = select_for_repricing(trips, s, settings)
    assert rt_other_pair in chosen
    assert len(chosen) == 3


def test_open_jaw_trips_are_never_repriced(settings):
    settings.update(reprice_top_n=30, reprice_cap_factor=10)
    assert select_for_repricing(_trips(5, kind="multi-city"), make_search(price_cap=5000), settings) == []


def test_selection_keeps_previous_deals(settings):
    settings.update(reprice_top_n=1, reprice_cap_factor=0, reprice_per_pair=0)
    trips = _trips(10)
    keep = {trips[7].key}
    chosen = select_for_repricing(trips, make_search(price_cap=100), settings, keep_keys=keep)
    assert trips[7] in chosen and trips[0] in chosen and len(chosen) == 2
