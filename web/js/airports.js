// Airport data (built by scripts/build_airports.py) and lookup helpers.

let all = [];
let byIata = new Map();

export async function loadAirports() {
  const res = await fetch("data/airports.json");
  if (!res.ok) throw new Error(`Could not load airports (${res.status})`);
  all = await res.json();
  byIata = new Map(all.map((a) => [a.iata, a]));
  return all;
}

export const getAirport = (iata) => byIata.get(iata);

export function visibleAirports(includeMedium) {
  return includeMedium ? all : all.filter((a) => a.type === "large_airport");
}

export const label = (a) => `${a.iata} ${a.city || a.name}`;

/** Search by IATA, city or name. Exact IATA first, then prefix matches, then substring. */
export function searchAirports(query, includeMedium, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const a of all) {
    const iata = a.iata.toLowerCase();
    const city = (a.city || "").toLowerCase();
    const name = a.name.toLowerCase();
    let score = -1;
    if (iata === q) score = 0;
    else if (city.startsWith(q)) score = 1;
    else if (name.startsWith(q) || iata.startsWith(q)) score = 2;
    else if (city.includes(q) || name.includes(q)) score = 3;
    if (score < 0) continue;
    if (a.type !== "large_airport") {
      if (!includeMedium && score > 0) continue;
      score += 0.5;
    }
    scored.push([score, a]);
  }
  scored.sort((x, y) => x[0] - y[0] || x[1].iata.localeCompare(y[1].iata));
  return scored.slice(0, limit).map(([, a]) => a);
}
