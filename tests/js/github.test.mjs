import { test } from "node:test";
import assert from "node:assert/strict";
import { GitHub, ConflictError } from "../../web/js/github.js";

function mockApi({ conflicts = 0 } = {}) {
  const files = new Map();
  let shaN = 0;
  const calls = [];
  globalThis.fetch = async (url, opts = {}) => {
    const u = new URL(url);
    calls.push([opts.method || "GET", u.pathname, opts.headers?.Authorization]);
    const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    const m = u.pathname.match(/^\/repos\/me\/repo\/contents\/(.+)$/);
    if (!m) return json(200, { full_name: "me/repo", default_branch: "main", permissions: { push: true } });
    const path = m[1];
    if ((opts.method || "GET") === "GET") {
      const f = files.get(path);
      return f ? json(200, { content: Buffer.from(f.text).toString("base64").replace(/(.{60})/g, "$1\n"), sha: f.sha }) : json(404, { message: "Not Found" });
    }
    const body = JSON.parse(opts.body);
    const cur = files.get(path);
    if (conflicts > 0) {
      conflicts--;
      // someone else committed in between
      files.set(path, { text: JSON.stringify({ version: 1, searches: [{ id: "other", name: "Ø other" }] }), sha: `s${++shaN}` });
      return json(409, { message: "is at x but expected y" });
    }
    if ((cur?.sha || undefined) !== body.sha) return json(422, { message: "sha wasn't supplied" });
    const sha = `s${++shaN}`;
    files.set(path, { text: Buffer.from(body.content, "base64").toString("utf8"), sha });
    return json(201, { content: { sha } });
  };
  return { files, calls };
}

const gh = () => new GitHub({ token: "test-token", owner: "me", repo: "repo" });

test("create, read back with unicode, update", async () => {
  const api = mockApi();
  const g = gh();
  assert.deepEqual(await g.getJson("config/searches.json"), { json: null, sha: null });
  await g.updateJson("config/searches.json", (c) => ({ ...c, searches: [{ id: "a", name: "København" }] }), "add", { version: 1, searches: [] });
  const { json } = await g.getJson("config/searches.json");
  assert.equal(json.searches[0].name, "København");
  assert.equal(api.calls[0][2], "Bearer test-token");
});

test("retries on conflict and keeps the other edit", async () => {
  mockApi({ conflicts: 1 });
  const g = gh();
  const next = await g.updateJson("config/searches.json", (c) => ({ ...c, searches: [...(c.searches || []), { id: "mine" }] }), "add", { version: 1, searches: [] });
  assert.deepEqual(next.searches.map((s) => s.id), ["other", "mine"]);
});

test("gives up after repeated conflicts", async () => {
  mockApi({ conflicts: 5 });
  await assert.rejects(gh().updateJson("x.json", (c) => c, "m", {}), ConflictError);
});

test("check reports write access", async () => {
  mockApi();
  assert.match(await gh().check(), /me\/repo/);
});
