// Small DOM helpers. Everything user- or data-provided goes through textContent,
// never innerHTML, so names from airports.json or the repo cannot inject markup.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k in node && typeof v !== "string") node[k] = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export const $ = (sel, root = document) => root.querySelector(sel);

export function clear(node) {
  while (node.firstChild) node.firstChild.remove();
  return node;
}

export function fmtPrice(n, currency) {
  return `${Math.round(n).toLocaleString("en-US").replace(/,/g, " ")} ${currency}`;
}

export function fmtKm(km) {
  return `${Math.round(km)} km`;
}

export function slugId(name) {
  const slug = name.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "search";
  const rand = Math.random().toString(36).slice(2, 6);
  return `${slug}-${rand}`;
}

export function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" });
  const a = el("a", { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 1000);
}

let toastTimer;
export function toast(message, kind = "info") {
  let box = $("#toast");
  if (!box) {
    box = el("div", { id: "toast", role: "status", "aria-live": "polite" });
    document.body.append(box);
  }
  box.textContent = message;
  box.className = `show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (box.className = ""), kind === "error" ? 8000 : 3500);
}
