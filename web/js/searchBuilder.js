// Search builder: origin/destination radius panels, trip settings, query budget, save.

import { getAirport, searchAirports, visibleAirports } from "./airports.js";
import { addDays, estimate, suggestions, todayUtc } from "./budget.js";
import { airportsInRadius } from "./geo.js";
import { SIDE_COLORS } from "./map.js";
import { clear, downloadJson, el, fmtKm, slugId, toast } from "./util.js";

const CURRENCIES = ["DKK", "EUR", "SEK", "NOK", "USD", "GBP", "PLN", "CHF"];
const SIDE_TITLES = { origins: "Origin", destinations: "Destination" };
const DEFAULT_RADIUS = 150;
const MAX_RADIUS = 1500;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const num = (v, fallback = 0) => (Number.isFinite(Number(v)) && v !== "" ? Number(v) : fallback);

function blankState() {
  const today = todayUtc();
  return {
    editing: null, // original search object when editing
    name: "",
    status: "active",
    trip_type: "return",
    earliest_out: addDays(today, 30),
    latest_return: addDays(today, 44),
    min_stay: 1,
    max_stay: 7,
    price_cap: 3000,
    currency: "DKK",
    tracking_days: 10,
    sides: {
      origins: { center: null, radius: DEFAULT_RADIUS, unchecked: new Set() },
      destinations: { center: null, radius: DEFAULT_RADIUS, unchecked: new Set() },
    },
  };
}

export class Builder {
  constructor({ root, map, store, local, onSaved, onIncludeMedium }) {
    Object.assign(this, { root, map, store, local, onSaved, onIncludeMedium });
    this.includeMedium = local.includeMedium;
    this.state = blankState();
    this.saving = false;
    this.build();
  }

  // ---------- state ----------

  open(search = null) {
    const st = blankState();
    if (search) {
      const fields = ["name", "status", "trip_type", "earliest_out", "latest_return", "min_stay", "max_stay", "price_cap", "currency", "tracking_days"];
      for (const f of fields) if (search[f] !== undefined) st[f] = search[f];
      st.editing = search;
      if (search.include_medium) this.setIncludeMedium(true, false);
      for (const side of ["origins", "destinations"]) {
        const prefix = side === "origins" ? "origin" : "destination";
        const center = getAirport(search[`${prefix}_center`]) || getAirport(search[side]?.[0]);
        const s = st.sides[side];
        s.center = center || null;
        s.radius = Number(search[`${prefix}_radius_km`] ?? DEFAULT_RADIUS);
        if (center) {
          const keep = new Set(search[side] || []);
          for (const { airport } of this.hitsFor(s)) if (!keep.has(airport.iata)) s.unchecked.add(airport.iata);
        }
      }
    }
    this.state = st;
    this.syncInputs();
    this.update({ fit: true });
  }

  setIncludeMedium(on, rerender = true) {
    this.includeMedium = on;
    this.inputs.includeMedium.checked = on;
    this.onIncludeMedium(on);
    if (rerender) this.update();
  }

  hitsFor(side) {
    if (!side.center) return [];
    const hits = airportsInRadius(visibleAirports(this.includeMedium), side.center, side.radius);
    if (!hits.some((h) => h.airport.iata === side.center.iata)) hits.unshift({ airport: side.center, km: 0 });
    return hits;
  }

  selected(sideName) {
    const s = this.state.sides[sideName];
    return this.hitsFor(s).filter((h) => !s.unchecked.has(h.airport.iata));
  }

  toSearch() {
    const st = this.state;
    const today = todayUtc();
    const orig = st.editing;
    return {
      id: orig?.id || slugId(st.name || "search"),
      name: st.name.trim() || "Untitled search",
      status: st.status,
      created: orig?.created || today,
      tracking_days: Math.max(1, Math.round(num(st.tracking_days, 10))),
      expires: addDays(today, Math.max(1, Math.round(num(st.tracking_days, 10)))),
      trip_type: st.trip_type,
      origin_center: st.sides.origins.center?.iata || null,
      origin_radius_km: num(st.sides.origins.radius),
      origins: this.selected("origins").map((h) => h.airport.iata),
      destination_center: st.sides.destinations.center?.iata || null,
      destination_radius_km: num(st.sides.destinations.radius),
      destinations: this.selected("destinations").map((h) => h.airport.iata),
      earliest_out: st.earliest_out,
      latest_return: st.latest_return,
      min_stay: Math.max(0, Math.round(num(st.min_stay, 1))),
      max_stay: Math.max(0, Math.round(num(st.max_stay, 7))),
      price_cap: num(st.price_cap),
      currency: st.currency,
      include_medium: this.includeMedium,
    };
  }

  validate(s) {
    const errs = [];
    const today = todayUtc();
    const st = this.state;
    const bad = (v) => !Number.isFinite(Number(v)) || v === "";
    if (bad(st.price_cap) || bad(st.tracking_days) || (s.trip_type === "return" && (bad(st.min_stay) || bad(st.max_stay)))) {
      errs.push("Fill in all number fields.");
    }
    if (!this.state.name.trim()) errs.push("Give the search a name.");
    if (!s.origins.length) errs.push("Pick an origin center and keep at least one origin airport checked.");
    if (!s.destinations.length) errs.push("Pick a destination center and keep at least one destination airport checked.");
    if (!DATE_RE.test(s.earliest_out) || !DATE_RE.test(s.latest_return)) errs.push("Set both dates.");
    else {
      if (s.latest_return < s.earliest_out) errs.push("The latest return date is before the earliest outbound date.");
      if (s.latest_return < today) errs.push("The whole date window is in the past.");
      if (s.trip_type === "return" && addDays(s.earliest_out, s.min_stay) > s.latest_return) errs.push("The window is shorter than the minimum stay.");
    }
    if (s.trip_type === "return") {
      if (!(s.min_stay >= 0)) errs.push("Minimum stay must be 0 or more.");
      if (!(s.max_stay >= s.min_stay)) errs.push("Maximum stay must be at least the minimum stay.");
    }
    if (!(s.price_cap > 0)) errs.push("Set a price cap above 0.");
    if (!(s.tracking_days >= 1)) errs.push("Track for at least 1 day.");
    return errs;
  }

  // ---------- DOM ----------

  build() {
    const root = clear(this.root);
    this.inputs = {};
    this.sidePanels = {};
    const input = (key, attrs, onchange) => {
      const node = el("input", { ...attrs, oninput: () => {
        this.state[key] = attrs.type === "number" ? node.valueAsNumber : node.value;
        onchange?.();
        this.update();
      } });
      this.inputs[key] = node;
      return node;
    };

    this.title = el("h2", {}, "New search");
    const name = input("name", { type: "text", placeholder: "e.g. Denmark to New York", maxlength: 80, autocomplete: "off" });

    this.inputs.includeMedium = el("input", { type: "checkbox", onchange: (e) => this.setIncludeMedium(e.target.checked) });

    const tripType = el(
      "div",
      { class: "segmented", role: "radiogroup" },
      ...["return", "one-way"].map((v) => {
        const r = el("input", { type: "radio", name: "trip_type", value: v, onchange: () => {
          this.state.trip_type = v;
          this.update();
        } });
        this.inputs[`trip_${v}`] = r;
        return el("label", {}, r, v === "return" ? "Return" : "One-way");
      }),
    );

    const currency = el("select", { onchange: (e) => {
      this.state.currency = e.target.value;
      this.update();
    } }, ...CURRENCIES.map((c) => el("option", { value: c }, c)));
    this.inputs.currency = currency;

    const status = el("select", { onchange: (e) => {
      this.state.status = e.target.value;
      this.update();
    } }, el("option", { value: "active" }, "Active"), el("option", { value: "paused" }, "Paused"));
    this.inputs.status = status;

    this.stayRow = el(
      "div",
      { class: "row" },
      el("label", { class: "field" }, "Min stay (days)", input("min_stay", { type: "number", min: 0, max: 60, step: 1 })),
      el("label", { class: "field" }, "Max stay (days)", input("max_stay", { type: "number", min: 0, max: 60, step: 1 })),
    );
    this.outLabel = el("span", {}, "Earliest outbound");
    this.retLabel = el("span", {}, "Latest return");

    this.expiresNote = el("p", { class: "muted small" });
    this.budgetBox = el("div", { class: "budget", "aria-live": "polite" });
    this.errorsBox = el("ul", { class: "errors" });
    this.saveBtn = el("button", { type: "button", class: "btn primary", onclick: () => this.save() }, "Save search");
    this.saveHint = el("p", { class: "muted small" });

    root.append(
      this.title,
      el("label", { class: "field" }, "Name", name),
      el("label", { class: "check" }, this.inputs.includeMedium, "Also show medium airports (e.g. regional airports with scheduled flights)"),
      this.sidePanel("origins"),
      this.sidePanel("destinations"),
      el(
        "section",
        { class: "panel" },
        el("h3", {}, "Trip"),
        tripType,
        el(
          "div",
          { class: "row" },
          el("label", { class: "field" }, this.outLabel, input("earliest_out", { type: "date" })),
          el("label", { class: "field" }, this.retLabel, input("latest_return", { type: "date" })),
        ),
        this.stayRow,
        el(
          "div",
          { class: "row" },
          el("label", { class: "field" }, "Price cap (total)", input("price_cap", { type: "number", min: 1, step: 50, inputmode: "numeric" })),
          el("label", { class: "field narrow" }, "Currency", currency),
        ),
        el(
          "div",
          { class: "row" },
          el("label", { class: "field" }, "Track for (days)", input("tracking_days", { type: "number", min: 1, max: 365, step: 1 })),
          el("label", { class: "field narrow" }, "Status", status),
        ),
        this.expiresNote,
        el("p", { class: "muted small" }, "1 adult, economy. No filters on stops, bags, duration or self-transfer."),
      ),
      el(
        "section",
        { class: "panel" },
        el("h3", {}, "Query budget"),
        this.budgetBox,
        this.errorsBox,
        el(
          "div",
          { class: "actions" },
          this.saveBtn,
          el("button", { type: "button", class: "btn", onclick: () => this.exportJson() }, "Export JSON"),
          el("a", { class: "btn ghost", href: "#/searches" }, "Cancel"),
        ),
        this.saveHint,
      ),
    );
  }

  sidePanel(sideName) {
    const color = SIDE_COLORS[sideName];
    const p = {};
    p.search = el("input", { type: "search", placeholder: "Search by code or city", autocomplete: "off", "aria-label": `${SIDE_TITLES[sideName]} airport search` });
    p.suggest = el("ul", { class: "suggest", role: "listbox" });
    p.search.addEventListener("input", () => this.renderSuggest(sideName));
    p.search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const first = searchAirports(p.search.value, this.includeMedium, 1)[0];
        if (first) this.pickCenter(sideName, first);
      } else if (e.key === "Escape") clear(p.suggest);
    });
    p.search.addEventListener("blur", () => setTimeout(() => clear(p.suggest), 200));
    p.center = el("div", { class: "center-line" });
    p.range = el("input", { type: "range", min: 0, max: MAX_RADIUS, step: 10, "aria-label": "Radius in km" });
    p.num = el("input", { type: "number", min: 0, max: MAX_RADIUS * 2, step: 10, class: "km", "aria-label": "Radius in km" });
    const setRadius = (v) => {
      const s = this.state.sides[sideName];
      s.radius = Math.max(0, Number.isFinite(v) ? v : 0);
      this.update();
    };
    p.range.addEventListener("input", () => setRadius(p.range.valueAsNumber));
    p.num.addEventListener("input", () => setRadius(p.num.valueAsNumber));
    p.count = el("span", { class: "muted" });
    const all = (on) => () => {
      const s = this.state.sides[sideName];
      for (const { airport } of this.hitsFor(s)) on ? s.unchecked.delete(airport.iata) : s.unchecked.add(airport.iata);
      this.update();
    };
    p.list = el("ul", { class: "ap-list" });
    this.sidePanels[sideName] = p;
    return el(
      "section",
      { class: `panel side ${sideName}`, style: `--side:${color}` },
      el("h3", {}, el("span", { class: "swatch" }), SIDE_TITLES[sideName]),
      el("div", { class: "search-box" }, p.search, p.suggest),
      p.center,
      el("label", { class: "radius" }, "Radius", p.range, p.num, "km"),
      el(
        "div",
        { class: "list-head" },
        p.count,
        el("span", {}, el("button", { type: "button", class: "link", onclick: all(true) }, "All"), " / ", el("button", { type: "button", class: "link", onclick: all(false) }, "None")),
      ),
      p.list,
    );
  }

  renderSuggest(sideName) {
    const p = this.sidePanels[sideName];
    clear(p.suggest);
    for (const a of searchAirports(p.search.value, this.includeMedium)) {
      p.suggest.append(
        el(
          "li",
          { role: "option" },
          el(
            "button",
            { type: "button", onmousedown: (e) => e.preventDefault(), onclick: () => this.pickCenter(sideName, a) },
            el("strong", {}, a.iata),
            ` ${a.city || ""} `,
            el("span", { class: "muted" }, `${a.name}, ${a.country}${a.type === "large_airport" ? "" : " (medium)"}`),
          ),
        ),
      );
    }
  }

  pickCenter(sideName, airport) {
    const p = this.sidePanels[sideName];
    p.search.value = "";
    clear(p.suggest);
    if (airport.type !== "large_airport" && !this.includeMedium) this.setIncludeMedium(true, false);
    this.state.sides[sideName].center = airport;
    this.update();
    this.map.focus(airport, this.state.sides[sideName].radius);
  }

  syncInputs() {
    const st = this.state;
    for (const k of ["name", "earliest_out", "latest_return", "min_stay", "max_stay", "price_cap", "tracking_days"]) this.inputs[k].value = st[k];
    this.inputs.currency.value = st.currency;
    this.inputs.status.value = st.status;
    this.inputs[`trip_${st.trip_type}`].checked = true;
    this.inputs.includeMedium.checked = this.includeMedium;
    this.title.textContent = st.editing ? `Edit: ${st.editing.name}` : "New search";
  }

  update({ fit = false } = {}) {
    const st = this.state;
    const oneWay = st.trip_type === "one-way";
    this.stayRow.hidden = oneWay;
    this.outLabel.textContent = oneWay ? "Earliest date" : "Earliest outbound";
    this.retLabel.textContent = oneWay ? "Latest date" : "Latest return";

    for (const sideName of ["origins", "destinations"]) {
      const s = st.sides[sideName];
      const p = this.sidePanels[sideName];
      const hits = this.hitsFor(s);
      p.range.value = Math.min(s.radius, MAX_RADIUS);
      if (document.activeElement !== p.num) p.num.value = s.radius;
      clear(p.center);
      p.center.append(s.center ? el("span", {}, "Center: ", el("strong", {}, s.center.iata), ` ${s.center.name}`) : el("span", { class: "muted" }, "Search above or click an airport on the map."));
      const checked = new Set(hits.filter((h) => !s.unchecked.has(h.airport.iata)).map((h) => h.airport.iata));
      p.count.textContent = s.center ? `${checked.size} of ${hits.length} airports selected` : "";
      const scroll = p.list.scrollTop;
      clear(p.list);
      for (const { airport: a, km } of hits) {
        const box = el("input", { type: "checkbox", checked: checked.has(a.iata), onchange: (e) => {
          e.target.checked ? s.unchecked.delete(a.iata) : s.unchecked.add(a.iata);
          this.update();
        } });
        p.list.append(
          el("li", { class: checked.has(a.iata) ? "" : "off" }, el("label", {}, box, el("strong", {}, a.iata), el("span", { class: "ap-name" }, ` ${a.city || a.name}`), el("span", { class: "km" }, fmtKm(km)))),
        );
      }
      p.list.scrollTop = scroll;
      this.map.setSide(sideName, s.center, s.radius, hits, checked);
    }
    if (fit) this.map.fit();

    const search = this.toSearch();
    this.expiresNote.textContent = `Tracking stops on ${search.expires} (counted from the day you save).`;
    this.renderBudget(search);
  }

  renderBudget(search) {
    const today = todayUtc();
    const others = this.store.searches.filter((s) => s.id !== search.id);
    const errs = this.validate(search);
    clear(this.budgetBox);
    clear(this.errorsBox);
    for (const e of errs) this.errorsBox.append(el("li", {}, e));

    let over = false;
    const datesOk = DATE_RE.test(search.earliest_out) && DATE_RE.test(search.latest_return) && search.latest_return >= search.earliest_out;
    if (search.origins.length && search.destinations.length && datesOk) {
      const est = estimate(search, others, this.store.settings, today);
      over = est.over;
      const lines = [
        ["This search", `${est.legs} leg searches${est.reserve ? ` + up to ${est.reserve} re-pricing` : ""} (about ${est.searchMinutes} min)`],
      ];
      if (est.shared) lines.push(["Shared", `${est.shared} legs are already searched by other searches (no extra cost)`]);
      lines.push(["Per run, all active", `${est.runTotal} of ${est.cap} (about ${est.minutes} min per run)`]);
      if (search.status !== "active") lines.push(["", "Paused searches do not count toward the budget."]);
      const meter = el("div", { class: `meter ${over ? "over" : ""}` }, el("span", { style: `width:${Math.min(100, (100 * est.runTotal) / est.cap)}%` }));
      this.budgetBox.append(
        el("dl", {}, ...lines.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
        meter,
      );
      if (over) {
        const distances = {};
        for (const side of ["origins", "destinations"]) {
          distances[side] = Object.fromEntries(this.hitsFor(this.state.sides[side]).map((h) => [h.airport.iata, h.km]));
        }
        const tips = suggestions(search, others, this.store.settings, today, distances);
        this.budgetBox.append(el("div", { class: "over-box" }, el("strong", {}, "Too many searches per run. Saving is blocked."), el("ul", {}, ...tips.map((t) => el("li", {}, t)))));
      }
    } else {
      this.budgetBox.append(el("p", { class: "muted" }, "Pick origins, destinations and dates to see the estimate."));
    }

    const blocked = errs.length > 0 || over || this.saving;
    this.saveBtn.disabled = blocked || !this.store.canSave;
    this.saveHint.textContent = !this.store.canSave
      ? "To save from here, add a GitHub token in Settings. Or use Export JSON and commit config/searches.json yourself."
      : "Saving commits config/searches.json to the repo. Everything in the repo is public.";
  }

  async save() {
    const search = this.toSearch();
    if (this.validate(search).length) return;
    this.saving = true;
    this.saveBtn.textContent = "Saving...";
    this.update();
    try {
      await this.store.saveSearch(search, this.state.editing ? "Update" : "Add");
      toast(`Saved "${search.name}". It will be searched on the next run.`, "ok");
      this.onSaved(search);
    } catch (e) {
      toast(`Could not save: ${e.message}`, "error");
    } finally {
      this.saving = false;
      this.saveBtn.textContent = "Save search";
      this.update();
    }
  }

  exportJson() {
    const search = this.toSearch();
    downloadJson("searches.json", this.store.configWith(search));
  }
}

