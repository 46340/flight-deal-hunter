// Query budget. Mirrors scraper/planner.py; keep the two in sync
// (tests/fixtures/estimate_cases.json is shared by both test suites).

export const SECONDS_PER_QUERY = 5;
const DAY = 86400000;

export const parseDate = (s) => {
  const [y, m, d] = s.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
};
export const fmtDate = (t) => new Date(t).toISOString().slice(0, 10);
export const addDays = (s, n) => fmtDate(parseDate(s) + n * DAY);
export const todayUtc = () => fmtDate(Date.now());

function range(start, end) {
  const out = [];
  for (let t = parseDate(start); t <= parseDate(end); t += DAY) out.push(fmtDate(t));
  return out;
}
const maxDate = (a, b) => (a > b ? a : b);
const minDate = (a, b) => (a < b ? a : b);

export function outboundDates(s, today) {
  const start = maxDate(s.earliest_out, today);
  if (s.trip_type === "one-way") return range(start, s.latest_return);
  return range(start, addDays(s.latest_return, -s.min_stay));
}

export function returnDates(s, today) {
  if (s.trip_type === "one-way") return [];
  const outs = outboundDates(s, today);
  if (!outs.length) return [];
  const start = addDays(outs[0], s.min_stay);
  const end = minDate(s.latest_return, addDays(outs[outs.length - 1], s.max_stay));
  return range(start, end);
}

/** Leg keys "FROM-TO-DATE-CUR": |O| x |D| x outbound dates + |D| x |O| x return dates. */
export function legsForSearch(s, today) {
  const legs = [];
  const cur = s.currency || "DKK";
  for (const d of outboundDates(s, today))
    for (const o of s.origins) for (const x of s.destinations) if (o !== x) legs.push(`${o}-${x}-${d}-${cur}`);
  for (const d of returnDates(s, today))
    for (const x of s.destinations) for (const o of s.origins) if (o !== x) legs.push(`${x}-${o}-${d}-${cur}`);
  return legs;
}

export const stage2Reserve = (s, settings) => (s.trip_type === "one-way" ? 0 : settings.reprice_max_per_search);

export const expiresOf = (s) => s.expires || addDays(s.created, s.tracking_days ?? 10);
export const isActive = (s, today) => s.status === "active" && today <= expiresOf(s);

/**
 * Estimate for one search plus the whole run if it were saved.
 * `others` are the other saved searches (the one being edited excluded).
 */
export function estimate(search, others, settings, today) {
  const own = legsForSearch(search, today);
  const seen = new Set();
  let reserve = 0;
  for (const o of others) {
    if (!isActive(o, today)) continue;
    for (const k of legsForSearch(o, today)) seen.add(k);
    reserve += stage2Reserve(o, settings);
  }
  const otherLegs = seen.size;
  let shared = 0;
  for (const k of own) {
    if (seen.has(k)) shared++;
    else seen.add(k);
  }
  const ownReserve = stage2Reserve(search, settings);
  const counts = search.status === "active";
  const total = counts ? seen.size + reserve + ownReserve : otherLegs + reserve;
  const cap = settings.max_searches_per_run;
  return {
    legs: own.length,
    shared,
    reserve: ownReserve,
    searchTotal: own.length + ownReserve,
    runTotal: total,
    cap,
    over: total > cap,
    minutes: Math.ceil((total * SECONDS_PER_QUERY) / 60),
    searchMinutes: Math.ceil(((own.length + ownReserve) * SECONDS_PER_QUERY) / 60),
  };
}

/** Concrete ways to get under the cap, cheapest-to-apply first. */
export function suggestions(search, others, settings, today, distances = {}) {
  const est = estimate(search, others, settings, today);
  if (!est.over) return [];
  const fits = (s) => !estimate(s, others, settings, today).over;
  const tips = [];
  const excess = est.runTotal - est.cap;
  tips.push(`Over the cap by ${excess} queries.`);

  // Shorter window: move latest return earlier.
  for (let cut = 1; ; cut++) {
    const latest = addDays(search.latest_return, -cut);
    if (latest < maxDate(search.earliest_out, today)) break;
    const s = { ...search, latest_return: latest };
    if (outboundDates(s, today).length === 0) break;
    if (fits(s)) {
      tips.push(`End the window on ${latest} instead of ${search.latest_return} (${cut} day${cut > 1 ? "s" : ""} shorter).`);
      break;
    }
  }

  // Fewer airports: drop the farthest ones from whichever side is bigger.
  const s = { ...search, origins: [...search.origins], destinations: [...search.destinations] };
  const dropped = [];
  const far = (list, side) => [...list].sort((a, b) => (distances[side]?.[b] ?? 0) - (distances[side]?.[a] ?? 0));
  while (!fits(s) && s.origins.length + s.destinations.length > 2) {
    const side = s.origins.length >= s.destinations.length && s.origins.length > 1 ? "origins" : "destinations";
    if (s[side].length <= 1) break;
    const victim = far(s[side], side)[0];
    s[side] = s[side].filter((x) => x !== victim);
    dropped.push(victim);
  }
  if (dropped.length && fits(s)) tips.push(`Uncheck ${dropped.length} airport${dropped.length > 1 ? "s" : ""}: ${dropped.join(", ")}.`);

  if (search.trip_type === "return" && search.max_stay > search.min_stay) {
    // Stay range barely changes stage 1, but say so to avoid wasted effort.
    tips.push("Narrowing the stay range does not help much: every date in the window is still searched.");
  }
  const activeOthers = others.filter((o) => isActive(o, today));
  if (activeOthers.length) tips.push(`Or pause another active search (${activeOthers.map((o) => o.name || o.id).join(", ")}).`);
  tips.push(`Or raise the per-run cap in Settings (currently ${est.cap}).`);
  return tips;
}
