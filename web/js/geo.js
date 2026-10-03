// Distance helpers. Mirrors scraper/geo.py; keep the two in sync.

const EARTH_RADIUS_KM = 6371.0088;
const rad = (d) => (d * Math.PI) / 180;

export function haversineKm(lat1, lon1, lat2, lon2) {
  const dp = rad(lat2 - lat1);
  const dl = rad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Airports within radiusKm of center (inclusive), nearest first, as {airport, km}. */
export function airportsInRadius(airports, center, radiusKm) {
  const hits = [];
  for (const ap of airports) {
    const km = haversineKm(center.lat, center.lon, ap.lat, ap.lon);
    if (km <= radiusKm) hits.push({ airport: ap, km });
  }
  hits.sort((a, b) => a.km - b.km || a.airport.iata.localeCompare(b.airport.iata));
  return hits;
}
