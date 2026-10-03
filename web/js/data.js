// Loads and saves repo data. With a token, reads go through the GitHub API so
// they are fresh; without one, they come from the published site (may lag a
// minute or two behind the repo).

import { GitHub } from "./github.js";

export const DEFAULT_SETTINGS = {
  max_searches_per_run: 800,
  reprice_max_per_search: 60,
};

export class Store {
  constructor(local) {
    this.setLocal(local);
    this.searches = [];
    this.settings = { ...DEFAULT_SETTINGS };
  }

  setLocal(local) {
    this.local = local;
    this.gh = new GitHub(local);
  }

  get canSave() {
    return this.gh.ready;
  }

  async fetchStatic(path, fallback) {
    try {
      const res = await fetch(path, { cache: "no-store" });
      if (!res.ok) return fallback;
      return await res.json();
    } catch {
      return fallback;
    }
  }

  async load() {
    let cfg, settings;
    if (this.canSave) {
      try {
        [cfg, settings] = await Promise.all([this.gh.getJson("config/searches.json"), this.gh.getJson("config/settings.json")]);
        cfg = cfg.json;
        settings = settings.json;
      } catch (e) {
        console.warn("GitHub read failed, using published copy", e);
        this.lastError = e;
      }
    }
    cfg ??= await this.fetchStatic("config/searches.json", { version: 1, searches: [] });
    settings ??= await this.fetchStatic("config/settings.json", {});
    this.searches = Array.isArray(cfg?.searches) ? cfg.searches : [];
    this.settings = { ...DEFAULT_SETTINGS, ...(settings || {}) };
    return this;
  }

  configWith(search) {
    const searches = this.searches.filter((s) => s.id !== search.id);
    const idx = this.searches.findIndex((s) => s.id === search.id);
    if (idx >= 0) searches.splice(idx, 0, search);
    else searches.push(search);
    return { version: 1, searches };
  }

  async saveSearch(search, verb = "Save") {
    const next = await this.gh.updateJson(
      "config/searches.json",
      (cfg) => {
        cfg.searches ??= [];
        const i = cfg.searches.findIndex((s) => s.id === search.id);
        if (i >= 0) cfg.searches[i] = search;
        else cfg.searches.push(search);
        return cfg;
      },
      `${verb} search: ${search.name}`,
      { version: 1, searches: [] },
    );
    this.searches = next.searches;
  }

  async deleteSearch(id) {
    const name = this.searches.find((s) => s.id === id)?.name || id;
    const next = await this.gh.updateJson(
      "config/searches.json",
      (cfg) => ({ ...cfg, searches: (cfg.searches || []).filter((s) => s.id !== id) }),
      `Delete search: ${name}`,
      { version: 1, searches: [] },
    );
    this.searches = next.searches;
  }

  async saveSettings(patch) {
    const next = await this.gh.updateJson("config/settings.json", (s) => ({ ...s, ...patch }), "Update settings", {});
    this.settings = { ...DEFAULT_SETTINGS, ...next };
  }
}
