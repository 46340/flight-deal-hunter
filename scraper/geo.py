"""Distance helpers. Mirrored in web/js/geo.js; keep the two in sync."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def airports_in_radius(airports: list[dict], center: dict, radius_km: float) -> list[tuple[dict, float]]:
    """Airports within radius_km of center (inclusive), nearest first, as (airport, distance_km)."""
    hits = []
    for ap in airports:
        d = haversine_km(center["lat"], center["lon"], ap["lat"], ap["lon"])
        if d <= radius_km:
            hits.append((ap, d))
    hits.sort(key=lambda h: (h[1], h[0]["iata"]))
    return hits
