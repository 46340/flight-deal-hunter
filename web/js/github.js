// Minimal GitHub REST client for reading and committing JSON files in this repo.

const API = "https://api.github.com";

export class ConflictError extends Error {}

function b64encodeUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

function b64decodeUtf8(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

export class GitHub {
  constructor({ token, owner, repo, branch = "main" }) {
    Object.assign(this, { token, owner, repo, branch });
  }

  get ready() {
    return Boolean(this.token && this.owner && this.repo);
  }

  async request(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      ...options,
      cache: "no-store",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${this.token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
    });
    if (!res.ok) {
      let detail = "";
      try {
        detail = (await res.json()).message || "";
      } catch {}
      if (res.status === 409 || (res.status === 422 && /sha/i.test(detail))) {
        throw new ConflictError("The file changed on GitHub in the meantime.");
      }
      const hint = res.status === 401 ? " (token invalid or expired)" : res.status === 403 || res.status === 404 ? " (check token permissions and repo name)" : "";
      const err = new Error(`GitHub ${res.status}: ${detail}${hint}`);
      err.status = res.status;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  /** Check the token can write to the repo. Returns a short description. */
  async check() {
    const repo = await this.request(`/repos/${this.owner}/${this.repo}`);
    if (!repo.permissions?.push) throw new Error("Token can read the repo but cannot write to it (Contents: Read and write needed).");
    return `${repo.full_name}, default branch ${repo.default_branch}`;
  }

  /** Returns {json, sha}, or {json: null, sha: null} if the file does not exist. */
  async getJson(path) {
    try {
      const f = await this.request(`/repos/${this.owner}/${this.repo}/contents/${path}?ref=${encodeURIComponent(this.branch)}`);
      return { json: JSON.parse(b64decodeUtf8(f.content)), sha: f.sha };
    } catch (e) {
      if (e.status === 404) return { json: null, sha: null };
      throw e;
    }
  }

  async putJson(path, json, sha, message) {
    const body = {
      message,
      content: b64encodeUtf8(JSON.stringify(json, null, 2) + "\n"),
      branch: this.branch,
      ...(sha ? { sha } : {}),
    };
    const res = await this.request(`/repos/${this.owner}/${this.repo}/contents/${path}`, { method: "PUT", body: JSON.stringify(body) });
    return res.content.sha;
  }

  /** Read, apply mutate(json) -> json, commit. Retries on concurrent edits. */
  async updateJson(path, mutate, message, fallback = {}) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const { json, sha } = await this.getJson(path);
      const next = mutate(structuredClone(json ?? fallback));
      try {
        await this.putJson(path, next, sha, message);
        return next;
      } catch (e) {
        if (!(e instanceof ConflictError) || attempt === 2) throw e;
      }
    }
  }
}
