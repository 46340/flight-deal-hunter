// Settings: GitHub token and repo (this browser only), per-run cap (committed to the repo).

import { forgetToken, saveLocal } from "./settings.js";
import { clear, el, toast } from "./util.js";

export function renderSettings(root, store, { onLocalChanged }) {
  clear(root);
  const local = { ...store.local };
  const token = el("input", { type: "password", value: local.token, autocomplete: "off", spellcheck: "false", placeholder: "github_pat_..." });
  const owner = el("input", { type: "text", value: local.owner, placeholder: "your GitHub username" });
  const repo = el("input", { type: "text", value: local.repo, placeholder: "flight-deal-hunter" });
  const branch = el("input", { type: "text", value: local.branch });
  const status = el("p", { class: "muted small" });

  const save = async () => {
    const next = { ...local, token: token.value.trim(), owner: owner.value.trim(), repo: repo.value.trim(), branch: branch.value.trim() || "main" };
    if (!saveLocal(next)) toast("This browser blocks local storage; the token will be forgotten when you leave.", "error");
    onLocalChanged(next);
    if (!next.token) {
      status.textContent = "No token: the app is read-only.";
      return;
    }
    status.textContent = "Checking...";
    try {
      status.textContent = `Connected: ${await store.gh.check()}.`;
      toast("Token saved on this device.", "ok");
    } catch (e) {
      status.textContent = e.message;
      toast(e.message, "error");
    }
  };

  const cap = el("input", { type: "number", min: 10, max: 5000, step: 10, value: store.settings.max_searches_per_run });
  const saveCap = async () => {
    const v = cap.valueAsNumber;
    if (!(v >= 10)) return toast("The cap must be at least 10.", "error");
    try {
      await store.saveSettings({ max_searches_per_run: Math.round(v) });
      toast("Per-run cap saved to the repo.", "ok");
    } catch (e) {
      toast(`Could not save: ${e.message}`, "error");
    }
  };

  root.append(
    el("h2", {}, "Settings"),
    el(
      "section",
      { class: "panel" },
      el("h3", {}, "GitHub access"),
      el("p", { class: "small" }, "A fine-grained personal access token lets this page save searches by committing config/searches.json. Give it access to this repository only, with Contents: Read and write. It is stored in this browser (localStorage) on this device only and is never written to the repo."),
      el("p", { class: "small muted" }, "Note: any other GitHub Pages site under the same username shares this browser storage. Only use pages you trust there."),
      el("label", { class: "field" }, "Token", token),
      el("div", { class: "row" }, el("label", { class: "field" }, "Owner", owner), el("label", { class: "field" }, "Repository", repo), el("label", { class: "field narrow" }, "Branch", branch)),
      el(
        "div",
        { class: "actions" },
        el("button", { type: "button", class: "btn primary", onclick: save }, "Save and test"),
        el("button", { type: "button", class: "btn", onclick: () => {
          onLocalChanged(forgetToken(local));
          token.value = "";
          status.textContent = "Token removed from this browser.";
        } }, "Forget token"),
      ),
      status,
    ),
    el(
      "section",
      { class: "panel" },
      el("h3", {}, "Scraper"),
      el("label", { class: "field" }, "Max searches per run (all active searches together)", cap),
      el("p", { class: "small muted" }, "Higher means longer runs and more chance of being blocked by Google. Each query takes about 5 seconds including the polite delay."),
      el("div", { class: "actions" }, el("button", { type: "button", class: "btn", disabled: !store.canSave, onclick: saveCap }, "Save cap")),
    ),
  );
}
