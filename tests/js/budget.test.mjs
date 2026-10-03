import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { outboundDates, returnDates, legsForSearch, estimate, suggestions, addDays, isActive } from "../../web/js/budget.js";
import { haversineKm, airportsInRadius } from "../../web/js/geo.js";

const cases = JSON.parse(readFileSync(new URL("../fixtures/estimate_cases.json", import.meta.url))).cases;
const settings = { max_searches_per_run: 800, reprice_max_per_search: 60 };
const base = { status: "active", created: "2026-10-01", tracking_days: 30, currency: "DKK", min_stay: 1, max_stay: 7 };

test("estimate cases shared with Python", () => {
  for (const c of cases) {
    const s = { ...base, ...c.search };
    assert.equal(outboundDates(s, c.today).length, c.outbound_dates, c.name);
    assert.equal(returnDates(s, c.today).length, c.return_dates, c.name);
    assert.equal(legsForSearch(s, c.today).length, c.expected, c.name);
  }
});

test("haversine matches Python", () => {
  assert.ok(Math.abs(haversineKm(0, 0, 0, 1) - 111.195) < 0.01);
  assert.ok(Math.abs(haversineKm(55.6179, 12.656, 40.6394, -73.7793) - 6190) < 15);
});

test("airports in radius inclusive and sorted", () => {
  const aps = [
    { iata: "CPH", lat: 55.6179, lon: 12.656 },
    { iata: "BLL", lat: 55.7403, lon: 9.157 },
    { iata: "JFK", lat: 40.6394, lon: -73.7793 },
  ];
  const d = haversineKm(55.6179, 12.656, 55.7403, 9.157);
  assert.deepEqual(airportsInRadius(aps, aps[0], d).map((h) => h.airport.iata), ["CPH", "BLL"]);
  assert.deepEqual(airportsInRadius(aps, aps[0], d - 0.01).map((h) => h.airport.iata), ["CPH"]);
});

test("run estimate dedups across searches and adds reserve", () => {
  const today = "2026-10-03";
  const a = { ...base, id: "a", trip_type: "return", origins: ["CPH"], destinations: ["JFK"], earliest_out: "2026-11-01", latest_return: "2026-11-05" };
  const b = { ...a, id: "b", origins: ["CPH", "HAM"] };
  const e = estimate(b, [a], settings, today);
  assert.equal(e.legs, 16);
  assert.equal(e.shared, 8);
  assert.equal(e.runTotal, 16 + 60 + 60);
  assert.equal(e.over, false);
});

test("paused search does not count", () => {
  const today = "2026-10-03";
  const a = { ...base, id: "a", trip_type: "one-way", origins: ["CPH"], destinations: ["JFK"], earliest_out: "2026-11-01", latest_return: "2026-11-05" };
  assert.equal(estimate({ ...a, status: "paused" }, [], settings, today).runTotal, 0);
  assert.equal(isActive({ ...a, created: "2026-09-01", tracking_days: 10 }, today), false);
});

test("suggestions fit under the cap", () => {
  const today = "2026-10-03";
  const s = { ...base, id: "big", trip_type: "return", origins: ["CPH", "BLL", "AAL", "HAM"], destinations: ["JFK", "EWR", "IAD", "BOS"],
    earliest_out: "2026-11-01", latest_return: "2026-11-30" };
  const tight = { ...settings, max_searches_per_run: 300 };
  assert.ok(estimate(s, [], tight, today).over);
  const tips = suggestions(s, [], tight, today, { origins: { CPH: 0, BLL: 250, AAL: 230, HAM: 290 }, destinations: { JFK: 0, EWR: 30, IAD: 340, BOS: 300 } });
  const windowTip = tips.find((t) => t.startsWith("End the window"));
  assert.ok(windowTip, tips.join("\n"));
  const latest = windowTip.match(/on (\d{4}-\d{2}-\d{2})/)[1];
  assert.equal(estimate({ ...s, latest_return: latest }, [], tight, today).over, false);
  assert.equal(estimate({ ...s, latest_return: addDays(latest, 1) }, [], tight, today).over, true);
  const apTip = tips.find((t) => t.startsWith("Uncheck"));
  assert.ok(apTip && apTip.includes("HAM"), apTip);
  assert.equal(suggestions({ ...s, origins: ["CPH"], destinations: ["JFK"] }, [], tight, today).length, 0);
});
