// Results for one search: deals table, cheapest per run, price chart, run log.

import { expiresOf } from "./budget.js";
import { statusOf } from "./searchList.js";
import { clear, el, fmtPrice, toast } from "./util.js";

const CHART_JS = {
  src: "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js",
  integrity: "sha384-bs/nf9FbdNouRbMiFcrcZfLXYPKiPaGVGplVbv7dLGECccEXDW+S3zjqSKR5ZEaD",
};
const SEPARATE_WARNING =
  "2 separate tickets: the airline of the second ticket has no duty to help if the first flight is delayed or cancelled and you miss it. Allow plenty of time between them.";
const RUN_HOURS_UTC = [5, 12, 19];

let chart = null;
let chartLoader = null;

function loadChartJs() {
  if (window.Chart) return Promise.resolve(window.Chart);
  chartLoader ??= new Promise((resolve, reject) => {
    const s = el("script", { src: CHART_JS.src, integrity: CHART_JS.integrity, crossorigin: "anonymous" });
    s.onload = () => resolve(window.Chart);
    s.onerror = () => reject(new Error("Could not load the chart library"));
    document.head.append(s);
  });
  return chartLoader;
}

const when = (iso) =>
  iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
const day = (iso) => (iso ? new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" }) : "");

function nextRun(now = new Date()) {
  for (let add = 0; add < 2; add++) {
    for (const h of RUN_HOURS_UTC) {
      const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + add, h));
      if (t > now) return t;
    }
  }
}

function ticketBadge(type) {
  if (type === "single") return el("span", { class: "ticket single" }, "Single ticket");
  return el(
    "button",
    { type: "button", class: "ticket separate", title: SEPARATE_WARNING, "aria-label": `2 separate tickets. ${SEPARATE_WARNING}`, onclick: () => toast(SEPARATE_WARNING) },
    "2 separate tickets ⚠",
  );
}

function links(d) {
  const labels = d.links.length > 1 ? ["Out", "Back"] : ["Google Flights"];
  return el("span", { class: "links" }, ...d.links.map((href, i) => el("a", { href, target: "_blank", rel: "noopener noreferrer" }, labels[i] || `Link ${i + 1}`)));
}

function dealsSection(result, search) {
  const currency = result.currency || search?.currency || "DKK";
  const isReturn = result.deals.some((d) => d.ret_date) || search?.trip_type !== "one-way";
  const state = { onlyAvailable: true, sort: "price" };
  const body = el("div");
  const onlyBox = el("input", { type: "checkbox", checked: true, onchange: (e) => {
    state.onlyAvailable = e.target.checked;
    render();
  } });
  const sortSel = el(
    "select",
    { "aria-label": "Sort deals", onchange: (e) => {
      state.sort = e.target.value;
      render();
    } },
    el("option", { value: "price" }, "Cheapest first"),
    el("option", { value: "out" }, "Earliest departure"),
    el("option", { value: "new" }, "Newest found"),
  );

  const columns = [
    ["Out", (d) => day(d.out_date)],
    ...(isReturn ? [["Back", (d) => day(d.ret_date)]] : []),
    ["Route out", (d) => `${d.out_from} to ${d.out_to}`],
    ...(isReturn ? [["Route back", (d) => (d.ret_from ? `${d.ret_from} to ${d.ret_to}` : "")]] : []),
    ["Airlines", (d) => (d.airlines || []).join(", ")],
    ["Total", (d) => el("strong", {}, fmtPrice(d.price, currency))],
    ["Ticket", (d) => ticketBadge(d.ticket_type)],
    ["Book", (d) => links(d)],
    ["First seen", (d) => when(d.first_seen)],
    ["Last seen", (d) => when(d.last_seen)],
    ["Available", (d) => el("span", { class: d.available ? "yes" : "no" }, d.available ? "Yes" : "No")],
  ];

  function render() {
    clear(body);
    let deals = result.deals.filter((d) => !state.onlyAvailable || d.available);
    const cmp = {
      price: (a, b) => a.price - b.price || a.out_date.localeCompare(b.out_date),
      out: (a, b) => a.out_date.localeCompare(b.out_date) || a.price - b.price,
      new: (a, b) => b.first_seen.localeCompare(a.first_seen) || a.price - b.price,
    }[state.sort];
    deals = [...deals].sort(cmp);
    if (!deals.length) {
      body.append(el("p", { class: "muted" }, result.deals.length ? "No deals are available in the latest run. Untick the box to see earlier ones." : `Nothing at or under ${fmtPrice(search?.price_cap ?? 0, currency)} yet. See the cheapest found per run below.`));
      return;
    }
    const table = el(
      "table",
      { class: "deals" },
      el("thead", {}, el("tr", {}, ...columns.map(([h]) => el("th", { scope: "col" }, h)))),
      el("tbody", {}, ...deals.map((d) => el("tr", { class: d.available ? "" : "gone" }, ...columns.map(([h, f]) => el("td", { "data-label": h }, f(d)))))),
    );
    body.append(el("div", { class: "table-wrap" }, table));
  }
  render();

  const available = result.deals.filter((d) => d.available).length;
  return el(
    "section",
    { class: "panel" },
    el("div", { class: "section-head" }, el("h3", {}, `Deals at or under ${fmtPrice(search?.price_cap ?? 0, currency)}`), el("span", { class: "muted small" }, `${available} available, ${result.deals.length} seen in total`)),
    el("div", { class: "toolbar" }, el("label", { class: "check inline" }, onlyBox, "Only available in latest run"), sortSel),
    body,
  );
}

function cheapestSection(result, search) {
  const currency = result.currency || search?.currency || "DKK";
  const rows = [...(result.cheapest_per_run || [])].reverse();
  const canvasWrap = el("div", { class: "chart-wrap" }, el("canvas", { "aria-label": "Cheapest total price per run" }));
  const list = el(
    "ul",
    { class: "cheapest" },
    ...rows.slice(0, 15).map((c) => {
      const over = search && c.price > search.price_cap;
      const route = c.ret_date ? `${c.out_from} to ${c.out_to} ${c.out_date}, back ${c.ret_from} to ${c.ret_to} ${c.ret_date}` : `${c.out_from} to ${c.out_to} ${c.out_date}`;
      return el(
        "li",
        {},
        el("span", { class: "muted" }, when(c.run)),
        el("strong", { class: over ? "over" : "under" }, fmtPrice(c.price, currency)),
        el("span", {}, route),
        el("span", { class: "muted small" }, `${c.ticket_type === "single" ? "single ticket" : "2 separate tickets"}, ${(c.airlines || []).join(", ")}`),
      );
    }),
  );
  const section = el(
    "section",
    { class: "panel" },
    el("div", { class: "section-head" }, el("h3", {}, "Cheapest found per run"), el("span", { class: "muted small" }, "Even above your cap, so you can see if the cap is realistic.")),
    rows.length ? canvasWrap : el("p", { class: "muted" }, "No complete runs yet."),
    rows.length ? list : null,
  );
  if (rows.length) drawChart(canvasWrap.firstChild, result, search, currency);
  return section;
}

async function drawChart(canvas, result, search, currency) {
  let Chart;
  try {
    Chart = await loadChartJs();
  } catch (e) {
    canvas.replaceWith(el("p", { class: "muted" }, e.message));
    return;
  }
  chart?.destroy();
  const pts = result.cheapest_per_run || [];
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim();
  const muted = css.getPropertyValue("--muted").trim();
  const grid = css.getPropertyValue("--border").trim();
  const datasets = [{ label: "Cheapest total", data: pts.map((p) => p.price), borderColor: accent, backgroundColor: accent, tension: 0.2, pointRadius: 3 }];
  if (search) datasets.push({ label: "Your cap", data: pts.map(() => search.price_cap), borderColor: muted, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 });
  chart = new Chart(canvas, {
    type: "line",
    data: { labels: pts.map((p) => when(p.run)), datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: muted, boxWidth: 12 } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${fmtPrice(ctx.parsed.y, currency)}` } },
      },
      scales: {
        x: { ticks: { color: muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 6 }, grid: { color: grid } },
        y: { ticks: { color: muted, callback: (v) => fmtPrice(v, "") }, grid: { color: grid } },
      },
    },
  });
}

function runLogSection(result) {
  const runs = [...(result.runs || [])].reverse();
  return el(
    "section",
    { class: "panel" },
    el("h3", {}, "Run log"),
    runs.length
      ? el(
          "div",
          { class: "table-wrap" },
          el(
            "table",
            { class: "runs" },
            el("thead", {}, el("tr", {}, ...["Time", "Searches", "Provider", "Status", "Errors"].map((h) => el("th", { scope: "col" }, h)))),
            el(
              "tbody",
              {},
              ...runs.slice(0, 60).map((r) =>
                el(
                  "tr",
                  {},
                  el("td", { "data-label": "Time" }, when(r.run)),
                  el("td", { "data-label": "Searches" }, String(r.searches ?? "")),
                  el("td", { "data-label": "Provider" }, r.provider || ""),
                  el("td", { "data-label": "Status" }, el("span", { class: `badge ${r.status}` }, r.status)),
                  el(
                    "td",
                    { "data-label": "Errors" },
                    r.errors?.length ? el("details", {}, el("summary", {}, `${r.errors.length} error${r.errors.length > 1 ? "s" : ""}`), el("ul", {}, ...r.errors.map((e) => el("li", {}, e)))) : el("span", { class: "muted" }, "None"),
                  ),
                ),
              ),
            ),
          ),
        )
      : el("p", { class: "muted" }, "No runs yet."),
  );
}

export async function renderResults(root, store, id) {
  clear(root);
  const search = store.searches.find((x) => x.id === id);
  root.append(el("p", { class: "muted" }, "Loading results..."));
  const result = await store.loadResults(id);
  clear(root);

  const st = search ? statusOf(search) : "deleted";
  const header = el(
    "div",
    { class: "results-head" },
    el("div", {}, el("h2", {}, search?.name || id), search ? el("p", { class: "route" }, el("span", { class: "o" }, search.origins.join(", ")), " to ", el("span", { class: "d" }, search.destinations.join(", "))) : null),
    el(
      "div",
      { class: "actions" },
      el("span", { class: `badge ${st}` }, st),
      search ? el("a", { class: "btn small", href: `#/edit/${encodeURIComponent(id)}` }, "Edit") : null,
      el("a", { class: "btn small", href: "#/searches" }, "All searches"),
    ),
  );
  root.append(header);

  if (!result) {
    const fmt = (t) => t.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
    const now = new Date();
    const recent = new Date(now.getTime() - 90 * 60000);
    const due = nextRun(recent);
    const timing =
      due <= now
        ? `A run was scheduled for ${fmt(due)} your time. GitHub often starts scheduled runs late, so it may still be starting or running; a run takes up to about an hour. If not, the next one is around ${fmt(nextRun(now))}.`
        : `The next scheduled run is around ${fmt(due)} your time (GitHub may start it a little late).`;
    root.append(
      el(
        "section",
        { class: "panel empty" },
        el("p", {}, "No results yet."),
        el("p", { class: "muted small" }, `Runs are scheduled at 05:00, 12:00 and 19:00 UTC. ${timing} You can also start a run by hand from the repo's Actions tab.`),
      ),
    );
    return;
  }
  result.deals ??= [];
  const currency = result.currency || search?.currency || "DKK";
  const avail = result.deals.filter((d) => d.available);
  const latest = (result.cheapest_per_run || []).at(-1);
  const lastRun = (result.runs || []).at(-1);
  root.append(
    el(
      "div",
      { class: "stats" },
      el("div", { class: "stat" }, el("span", {}, "Deals available"), el("strong", {}, String(avail.length))),
      el("div", { class: "stat" }, el("span", {}, "Cheapest deal now"), el("strong", {}, avail.length ? fmtPrice(Math.min(...avail.map((d) => d.price)), currency) : "None")),
      el("div", { class: "stat" }, el("span", {}, "Cheapest in latest run"), el("strong", {}, latest ? fmtPrice(latest.price, currency) : "None")),
      el("div", { class: "stat" }, el("span", {}, "Last run"), el("strong", {}, lastRun ? `${when(lastRun.run)}, ${lastRun.status}` : "None")),
    ),
  );
  if (search) root.append(el("p", { class: "muted small" }, `Cap ${fmtPrice(search.price_cap, currency)}. ${st === "expired" ? "Expired on" : "Tracking until"} ${expiresOf(search)}. 1 adult, economy.`));
  root.append(dealsSection(result, search), cheapestSection(result, search), runLogSection(result));
}
