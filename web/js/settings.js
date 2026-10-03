// Browser-only settings (token, repo). Stored in localStorage on this device, never in the repo.

const KEY = "fdh.settings.v1";

export function detectRepo() {
  const host = location.hostname;
  if (host.endsWith(".github.io")) {
    const owner = host.split(".")[0];
    const first = location.pathname.split("/").filter(Boolean)[0];
    return { owner, repo: first || `${owner}.github.io` };
  }
  return { owner: "", repo: "" };
}

export function loadLocal() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(KEY) || "{}");
  } catch {}
  const detected = detectRepo();
  return {
    token: saved.token || "",
    owner: saved.owner || detected.owner,
    repo: saved.repo || detected.repo,
    branch: saved.branch || "main",
    includeMedium: Boolean(saved.includeMedium),
  };
}

export function saveLocal(values) {
  try {
    localStorage.setItem(KEY, JSON.stringify(values));
    return true;
  } catch {
    return false;
  }
}

export function forgetToken(values) {
  const next = { ...values, token: "" };
  saveLocal(next);
  return next;
}
