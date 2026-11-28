import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { handle, parseIngest, SITE_TAG } from "./worker.mjs";

const NOW = Date.parse("2026-11-07T18:00:00.000Z");
const HOST = "admin.ljiindustries.com";
const EMAIL = "owner@example.com";
const AUD = "0123456789abcdef0123456789abcdef";
const TEAM = "https://lji.cloudflareaccess.com";

const { publicKey, privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const publicJwk = publicKey.export({ format: "jwk" });
publicJwk.kid = "test-key";
publicJwk.alg = "RS256";
publicJwk.use = "sig";

function b64url(bytes) {
  return Buffer.from(bytes).toString("base64url");
}

function jwt(payload, kid = "test-key") {
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT", kid }));
  const body = b64url(JSON.stringify(payload));
  const data = header + "." + body;
  const sig = sign("RSA-SHA256", Buffer.from(data), privateKey);
  return data + "." + b64url(sig);
}

function ownerToken(extra = {}) {
  return jwt({
    iss: TEAM,
    aud: AUD,
    exp: Math.floor(NOW / 1000) + 600,
    email: EMAIL,
    ...extra,
  });
}

function env(over = {}) {
  return {
    ADMIN_HOST: HOST,
    ADMIN_EMAIL: EMAIL,
    TEAM_DOMAIN: TEAM,
    ACCESS_AUD: AUD,
    ...over,
  };
}

function certFetch() {
  return async () => ({ ok: true, json: async () => ({ keys: [publicJwk] }) });
}

class MemoryKV {
  constructor() { this.map = new Map(); }
  async get(key) { return this.map.has(key) ? this.map.get(key) : null; }
  async put(key, value) { this.map.set(key, value); }
}

function call(path, { method = "GET", token = ownerToken(), headers = {}, body, kv, host = HOST, config = env() } = {}) {
  const head = new Headers(headers);
  if (token) head.set("cf-access-jwt-assertion", token);
  const init = { method, headers: head };
  if (body !== undefined && method !== "GET" && method !== "HEAD") init.body = body;
  return handle(new Request("https://" + host + path, init), config, {
    now: () => NOW,
    fetch: certFetch(),
    kv,
  });
}

function websiteBody(rows) {
  return {
    source: "website",
    range: "7d",
    fetchedAt: "2026-11-07T17:00:00.000Z",
    siteTag: SITE_TAG,
    rows,
  };
}

test("rejects alternate hosts and workers.dev before returning data", async () => {
  for (const host of ["lji-admin.example.workers.dev", "workers.dev", "ljiindustries.com", "preview.ljiindustries.com"]) {
    const res = await call("/api/summary", { host });
    assert.equal(res.status, 403);
    assert.equal(await res.text(), "forbidden\n");
  }
  const misconfigured = await call("/api/summary", {
    host: "lji-admin.example.workers.dev",
    config: env({ ADMIN_HOST: "lji-admin.example.workers.dev" }),
  });
  assert.equal(misconfigured.status, 403);
});

test("unauthenticated requests get 401 and no dashboard", async () => {
  for (const path of ["/", "/api/summary", "/api/ingest/website?range=7d"]) {
    const res = await call(path, { method: path.includes("ingest") ? "POST" : "GET", token: null, body: "{}" });
    assert.equal(res.status, 401, path);
    const text = await res.text();
    assert.equal(text, "authentication required\n");
    assert.equal(text.includes("pageLoads"), false);
    assert.equal(text.includes("<h1"), false);
  }
});

test("bad, expired, and foreign tokens are forbidden", async () => {
  const cases = [
    ownerToken().slice(0, -4) + "aaaa",
    ownerToken({ exp: Math.floor(NOW / 1000) - 10 }),
    ownerToken({ email: "other@example.com" }),
    ownerToken({ aud: "ffffffffffffffffffffffffffffffff" }),
    jwt({ iss: TEAM, aud: AUD, exp: Math.floor(NOW / 1000) + 60, email: EMAIL }, "other-key"),
  ];
  for (const token of cases) {
    const res = await call("/", { token });
    assert.equal(res.status, 403);
    assert.equal((await res.text()).includes("EXAMPLE"), false);
  }
});

test("missing access configuration fails closed", async () => {
  const res = await call("/", { config: env({ ADMIN_EMAIL: "" }) });
  assert.equal(res.status, 403);
});

test("authenticated summary keeps sources separate and does not invent numbers", async () => {
  const res = await call("/api/summary?range=30d", { kv: new MemoryKV() });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("x-robots-tag"), "noindex, nofollow");
  assert.equal(res.headers.get("cache-control"), "no-store");
  assert.equal(res.headers.get("access-control-allow-origin"), null);
  const body = await res.json();
  assert.equal(body.range, "30d");
  assert.equal(body.total, undefined);
  assert.equal(body.sources.website.metrics, null);
  assert.equal(body.sources.x.metrics, null);
  assert.equal(body.sources.tiktok.metrics, null);
  assert.equal(body.sources.website.status, "not_connected");
  assert.equal(body.sources.tiktok.status, "not_connected");
  assert.equal(JSON.stringify(body).includes("\"pageLoads\":0"), false);
  assert.equal(Object.hasOwn(body.sources.website, "uniqueUsers"), false);
});

test("dashboard html is served only after access and has no script", async () => {
  const res = await call("/?range=7d", { kv: new MemoryKV() });
  assert.equal(res.status, 200);
  const html = await res.text();
  assert.match(html, /noindex, nofollow/);
  assert.match(html, /Website/);
  assert.match(html, /TikTok is not connected/);
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("EXAMPLE DATA"), false);
  assert.equal(html.includes("owner@example.com"), false);
});

test("website ingest stores page loads and visits without referrers or unique users", async () => {
  const kv = new MemoryKV();
  const saved = await call("/api/ingest/website?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(websiteBody([
      { requestPath: "/example", count: 8, visits: 6 },
      { requestPath: "/example/child", count: 3, visits: 2 },
    ])),
  });
  assert.equal(saved.status, 200);
  const summary = await (await call("/api/summary?range=7d", { kv })).json();
  assert.equal(summary.sources.website.status, "connected");
  assert.equal(summary.sources.website.metrics.pageLoads, 11);
  assert.equal(summary.sources.website.metrics.visits, 8);
  assert.equal(summary.sources.website.metrics.referrers, null);
  assert.equal(summary.sources.website.metrics.byPath[0].path, "/example");
  assert.equal(summary.sources.x.status, "not_connected");
  assert.equal(summary.sources.x.metrics, null);
  const thirty = await (await call("/api/summary?range=30d", { kv })).json();
  assert.equal(thirty.sources.website.metrics, null);
});

test("stale snapshots stay visible and are labeled stale", async () => {
  const kv = new MemoryKV();
  await call("/api/ingest/website?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...websiteBody([{ requestPath: "/example", count: 2, visits: 2 }]), fetchedAt: "2026-11-05T00:00:00.000Z" }),
  });
  const summary = await (await call("/api/summary?range=7d", { kv })).json();
  assert.equal(summary.sources.website.status, "stale");
  assert.equal(summary.sources.website.freshness.stale, true);
  assert.equal(summary.sources.website.metrics.pageLoads, 2);
});

test("invalid website snapshots and ranges are rejected", async () => {
  const kv = new MemoryKV();
  const bad = [
    websiteBody([{ requestPath: "/example", count: 1 }]),
    { ...websiteBody([{ requestPath: "/example", count: 1, visits: 1 }]), siteTag: "ffffffffffffffffffffffffffffffff" },
    { ...websiteBody([{ requestPath: "/example", count: 1, visits: 1, referrers: 3 }]) },
    { ...websiteBody([{ requestPath: "https://evil.example", count: 1, visits: 1 }]) },
    { ...websiteBody([{ requestPath: "/example", count: -1, visits: 1 }]) },
  ];
  for (const body of bad) {
    const res = await call("/api/ingest/website?range=7d", {
      method: "POST", kv, headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    });
    assert.equal(res.status, 400);
  }
  assert.equal(await kv.get("website:7d"), null);
  const range = await call("/api/summary?range=14d", { kv });
  assert.equal(range.status, 400);
  const anon = await call("/api/summary?range=14d", { token: null });
  assert.equal(anon.status, 401);
});

test("x public metrics stay separate and private metrics are refused", async () => {
  const kv = new MemoryKV();
  const saved = await call("/api/ingest/x?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source: "x",
      range: "7d",
      fetchedAt: "2026-11-07T17:30:00.000Z",
      accounts: [{ id: "1000000000000000001", username: "example", publicMetrics: { followers_count: 12 } }],
      posts: [{ id: "99", createdAt: null, publicMetrics: { impression_count: 40, like_count: null } }],
    }),
  });
  assert.equal(saved.status, 200);
  const summary = await (await call("/api/summary?range=7d", { kv })).json();
  assert.equal(summary.sources.x.status, "connected");
  assert.equal(summary.sources.x.metrics.accounts[0].publicMetrics.followers_count, 12);
  assert.equal(summary.sources.x.metrics.accounts[0].publicMetrics.following_count, null);
  assert.equal(summary.sources.x.metrics.posts[0].publicMetrics.impression_count, 40);
  assert.equal(summary.sources.x.metrics.posts[0].publicMetrics.like_count, null);
  assert.equal(summary.sources.website.metrics, null);
  assert.equal(summary.combined, undefined);
  const denied = await call("/api/ingest/x?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source: "x",
      range: "7d",
      fetchedAt: "2026-11-07T17:30:00.000Z",
      accounts: [],
      posts: [],
      non_public_metrics: { impression_count: 1 },
    }),
  });
  assert.equal(denied.status, 400);
  assert.match((await denied.json()).error, /private metrics/);
});

test("tiktok import is refused and cross-site ingest is forbidden", async () => {
  const kv = new MemoryKV();
  const tiktok = await call("/api/ingest/tiktok?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ followers: 10 }),
  });
  assert.equal(tiktok.status, 422);
  assert.equal(await kv.get("tiktok:7d"), null);
  const cross = await call("/api/ingest/website?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "application/json", "sec-fetch-site": "cross-site" },
    body: JSON.stringify(websiteBody([{ requestPath: "/example", count: 1, visits: 1 }])),
  });
  assert.equal(cross.status, 403);
  const plain = await call("/api/ingest/website?range=7d", {
    method: "POST",
    kv,
    headers: { "content-type": "text/plain" },
    body: "{}",
  });
  assert.equal(plain.status, 415);
});

test("ingest without storage reports that it saved nothing", async () => {
  const res = await call("/api/ingest/website?range=7d", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(websiteBody([{ requestPath: "/example", count: 1, visits: 1 }])),
  });
  assert.equal(res.status, 503);
});

test("parser rejects a tiktok document directly", () => {
  assert.throws(() => parseIngest("tiktok", "7d", { handle: "@example" }, NOW), /schema/);
});

test("public site and sitemap do not advertise the admin host", () => {
  const home = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const sitemap = readFileSync(new URL("../sitemap.xml", import.meta.url), "utf8");
  const builder = readFileSync(new URL("../tools/build_briefed.py", import.meta.url), "utf8");
  for (const text of [home, sitemap, builder]) {
    assert.equal(text.includes("admin.ljiindustries.com"), false);
    assert.equal(text.includes("/api/ingest"), false);
  }
});
