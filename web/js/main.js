// App shell: loads data, routes between views by URL hash.

import { loadAirports, visibleAirports } from "./airports.js";
import { Store } from "./data.js";
import { AirportMap } from "./map.js";
import { Builder } from "./searchBuilder.js";
import { renderSearchList } from "./searchList.js";
import { loadLocal, saveLocal } from "./settings.js";
import { renderSettings } from "./settingsView.js";
import { $, clear, el, toast } from "./util.js";

const views = ["searches", "builder", "results", "settings"];
let store, builder, map;

function show(view) {
  for (const v of views) $(`#view-${v}`).hidden = v !== view;
  for (const a of document.querySelectorAll("nav a")) a.classList.toggle("current", a.dataset.view === view);
  if (view === "builder") {
    // The map has no size while hidden, so resize and fit only once it is visible.
    requestAnimationFrame(() => {
      map.refresh();
      map.fit();
    });
  }
}

async function route() {
  const [, name = "searches", arg] = location.hash.split("/");
  const id = arg ? decodeURIComponent(arg) : null;
  if (name === "new") {
    builder.open(null);
    show("builder");
  } else if (name === "edit") {
    const s = store.searches.find((x) => x.id === id);
    if (!s) {
      toast("Search not found.", "error");
      location.hash = "#/searches";
      return;
    }
    builder.open(s);
    show("builder");
  } else if (name === "results") {
    const { renderResults } = await import("./results.js");
    await renderResults($("#view-results"), store, id);
    show("results");
  } else if (name === "settings") {
    renderSettings($("#view-settings"), store, { onLocalChanged: async (local) => {
      store.setLocal(local);
      await store.load();
    } });
    show("settings");
  } else {
    renderSearchList($("#view-searches"), store, { onChanged: () => route() });
    show("searches");
  }
}

async function init() {
  const local = loadLocal();
  store = new Store(local);
  try {
    await Promise.all([loadAirports(), store.load()]);
  } catch (e) {
    clear($("main")).append(el("p", { class: "notice" }, `Could not load data: ${e.message}`));
    return;
  }
  if (store.lastError) toast(`GitHub: ${store.lastError.message}. Showing the published copy.`, "error");

  map = new AirportMap($("#map"), { onPick: (side, airport) => builder.pickCenter(side, airport) });
  map.setAirports(visibleAirports(local.includeMedium));
  builder = new Builder({
    root: $("#builder-panel"),
    map,
    store,
    local,
    onSaved: () => (location.hash = "#/searches"),
    onIncludeMedium: (on) => {
      map.setAirports(visibleAirports(on));
      store.local = { ...store.local, includeMedium: on };
      saveLocal(store.local);
    },
  });
  window.addEventListener("hashchange", route);
  route();
}

init();
