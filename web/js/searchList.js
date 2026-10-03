// Saved searches: status, summary, and actions (edit, pause/resume, delete).

import { estimate, expiresOf, isActive, todayUtc } from "./budget.js";
import { clear, downloadJson, el, fmtPrice, toast } from "./util.js";

function routeText(list, max = 4) {
  if (!list?.length) return "?";
  return list.length > max ? `${list.slice(0, max).join(", ")} +${list.length - max}` : list.join(", ");
}

export function statusOf(s, today = todayUtc()) {
  if (s.status !== "active") return "paused";
  return isActive(s, today) ? "active" : "expired";
}

export function renderSearchList(root, store, { onChanged }) {
  clear(root);
  const today = todayUtc();
  const header = el(
    "div",
    { class: "list-toolbar" },
    el("h2", {}, "Searches"),
    el(
      "div",
      { class: "actions" },
      el("a", { class: "btn primary", href: "#/new" }, "New search"),
      el("button", { type: "button", class: "btn", onclick: () => downloadJson("searches.json", { version: 1, searches: store.searches }) }, "Export JSON"),
    ),
  );
  root.append(header);

  const active = store.searches.filter((s) => isActive(s, today));
  if (store.searches.length) {
    const est = active.length ? estimate(active[0], active.slice(1), store.settings, today) : null;
    root.append(
      el("p", { class: "muted" }, est ? `Per run: about ${est.runTotal} of ${est.cap} queries, roughly ${est.minutes} min. Runs at 05:00, 12:00 and 19:00 UTC.` : "No active searches, so scheduled runs do nothing."),
    );
  }
  if (!store.canSave) {
    root.append(el("p", { class: "notice" }, "Read-only: add a GitHub token in ", el("a", { href: "#/settings" }, "Settings"), " to save, pause or delete searches from here."));
  }
  if (!store.searches.length) {
    root.append(el("div", { class: "empty" }, el("p", {}, "No searches yet."), el("a", { class: "btn primary", href: "#/new" }, "Create your first search")));
    return;
  }

  const grid = el("div", { class: "cards" });
  for (const s of store.searches) {
    const st = statusOf(s, today);
    const act = async (fn, okMsg) => {
      try {
        await fn();
        toast(okMsg, "ok");
        onChanged();
      } catch (e) {
        toast(`Failed: ${e.message}`, "error");
      }
    };
    const toggle = el(
      "button",
      { type: "button", class: "btn small", disabled: !store.canSave, onclick: () => {
        if (st === "paused") {
          const resumed = { ...s, status: "active" };
          const e = estimate(resumed, store.searches.filter((o) => o.id !== s.id), store.settings, today);
          if (e.over) return toast(`Resuming would need ${e.runTotal} queries per run, over the cap of ${e.cap}. Edit the search to shrink it.`, "error");
          act(() => store.saveSearch(resumed, "Resume"), "Resumed.");
        } else {
          act(() => store.saveSearch({ ...s, status: "paused" }, "Pause"), "Paused.");
        }
      } },
      st === "paused" ? "Resume" : "Pause",
    );
    if (st === "expired") toggle.hidden = true;

    let armed = false;
    const del = el("button", { type: "button", class: "btn small danger", disabled: !store.canSave, onclick: () => {
      if (!armed) {
        armed = true;
        del.textContent = "Tap again to delete";
        setTimeout(() => {
          armed = false;
          del.textContent = "Delete";
        }, 4000);
        return;
      }
      act(() => store.deleteSearch(s.id), "Deleted. Its results file stays in the repo.");
    } }, "Delete");

    const dates = s.trip_type === "one-way" ? `${s.earliest_out} to ${s.latest_return}, one-way` : `${s.earliest_out} to ${s.latest_return}, stay ${s.min_stay} to ${s.max_stay} days`;
    grid.append(
      el(
        "article",
        { class: `card ${st}` },
        el("div", { class: "card-head" }, el("h3", {}, s.name || s.id), el("span", { class: `badge ${st}` }, st)),
        el("p", { class: "route" }, el("span", { class: "o" }, routeText(s.origins)), " to ", el("span", { class: "d" }, routeText(s.destinations))),
        el("p", { class: "muted small" }, dates),
        el("p", { class: "muted small" }, `Cap ${fmtPrice(s.price_cap, s.currency || "DKK")}. ${st === "expired" ? "Expired" : "Tracking until"} ${expiresOf(s)}.`),
        el(
          "div",
          { class: "actions" },
          el("a", { class: "btn small primary", href: `#/results/${encodeURIComponent(s.id)}` }, "Results"),
          el("a", { class: "btn small", href: `#/edit/${encodeURIComponent(s.id)}` }, st === "expired" ? "Edit or renew" : "Edit"),
          toggle,
          del,
        ),
      ),
    );
  }
  root.append(grid);
}
