import pytest

from scraper.geo import airports_in_radius, haversine_km

AIRPORTS = [
    {"iata": "CPH", "lat": 55.6179, "lon": 12.656},
    {"iata": "BLL", "lat": 55.7403, "lon": 9.157},
    {"iata": "AAL", "lat": 57.0948, "lon": 9.8499},
    {"iata": "HAM", "lat": 53.6304, "lon": 9.9882},
    {"iata": "JFK", "lat": 40.6394, "lon": -73.7793},
]


def test_haversine_zero():
    assert haversine_km(55.6, 12.6, 55.6, 12.6) == 0


def test_haversine_one_degree_on_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


def test_haversine_cph_jfk():
    assert haversine_km(55.6179, 12.656, 40.6394, -73.7793) == pytest.approx(6190, abs=15)


def test_haversine_symmetric():
    a = haversine_km(55.6, 12.6, 40.6, -73.7)
    assert a == pytest.approx(haversine_km(40.6, -73.7, 55.6, 12.6))


def test_antipodes_do_not_crash():
    assert haversine_km(0, 0, 0, 180) == pytest.approx(20015, abs=5)


def test_airports_in_radius_sorted_and_includes_center():
    hits = airports_in_radius(AIRPORTS, AIRPORTS[0], 300)
    codes = [a["iata"] for a, _ in hits]
    assert codes[0] == "CPH" and hits[0][1] == 0
    assert set(codes) == {"CPH", "BLL", "AAL", "HAM"}
    dists = [d for _, d in hits]
    assert dists == sorted(dists)


def test_airports_in_radius_boundary_inclusive():
    d = haversine_km(55.6179, 12.656, 55.7403, 9.157)
    assert "BLL" in [a["iata"] for a, _ in airports_in_radius(AIRPORTS, AIRPORTS[0], d)]
    assert "BLL" not in [a["iata"] for a, _ in airports_in_radius(AIRPORTS, AIRPORTS[0], d - 0.01)]


def test_airports_in_radius_zero_radius():
    assert [a["iata"] for a, _ in airports_in_radius(AIRPORTS, AIRPORTS[0], 0)] == ["CPH"]
