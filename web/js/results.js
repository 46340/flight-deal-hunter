// Results view. Implemented in phase 4.

import { clear, el } from "./util.js";

export async function renderResults(root, store, id) {
  clear(root);
  const s = store.searches.find((x) => x.id === id);
  root.append(el("h2", {}, s ? s.name : "Results"), el("p", { class: "muted" }, "Results view comes in phase 4."), el("a", { class: "btn", href: "#/searches" }, "Back"));
}
