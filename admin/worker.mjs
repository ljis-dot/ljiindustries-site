/**
 * Private admin for admin.ljiindustries.com.
 * GitHub Pages cannot authenticate this. The worker fails closed unless
 * Cloudflare Access proves the configured owner email, and it refuses every
 * host other than ADMIN_HOST (including workers.dev and preview URLs).
 * Metrics come only from authenticated snapshot uploads. Nothing here is a
 * live count, and missing sources stay null.
 */

const SITE_TAG = "57c329fc4bd24936a4ec6bdb8a771be4";
const RANGES = new Set(["7d", "30d", "90d"]);
const STALE_MS = 48 * 60 * 60 * 1000;
const MAX_BODY = 100_000;
const USER_METRICS = ["followers_count", "following_count", "tweet_count", "listed_count"];
const POST_METRICS = ["impression_count", "like_count", "reply_count", "retweet_count", "quote_count", "bookmark_count"];

export { SITE_TAG, RANGES, STALE_MS };

function text(status, message, extra) {
  return new Response(message + "\n", {
    status,
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-robots-tag": "noindex, nofollow",
      "referrer-policy": "no-referrer",
      ...extra,
    },
  });
}

function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-robots-tag": "noindex, nofollow",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
    },
  });
}

function configured(env) {
  if (!env) return false;
  const email = String(env.ADMIN_EMAIL || "");
  const team = String(env.TEAM_DOMAIN || "");
  return hostAllowed(String(env.ADMIN_HOST || "").toLowerCase(), env.ADMIN_HOST || "")
    && /^[^\s@]+@[^\s@]+$/.test(email)
    && /^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/.test(team)
    && typeof env.ACCESS_AUD === "string"
    && env.ACCESS_AUD.length >= 16;
}

function hostAllowed(host, expected) {
  expected = String(expected || "").toLowerCase();
  host = String(host || "").toLowerCase();
  if (!expected || expected === "workers.dev" || expected.endsWith(".workers.dev")) return false;
  if (!host || host === "workers.dev" || host.endsWith(".workers.dev")) return false;
  return host === expected;
}

function b64urlToBytes(s) {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + pad;
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function verifyAccessJwt(token, env, fetchImpl, now) {
  const parts = typeof token === "string" ? token.split(".") : [];
  if (parts.length !== 3) return null;
  let header, payload;
  try {
    header = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[0])));
    payload = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[1])));
  } catch {
    return null;
  }
  const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (header.alg !== "RS256" || !header.kid) return null;
  if (payload.iss !== env.TEAM_DOMAIN) return null;
  if (!aud.includes(env.ACCESS_AUD)) return null;
  if (typeof payload.exp !== "number" || payload.exp * 1000 <= now) return null;
  if (typeof payload.email !== "string") return null;
  if (payload.email.toLowerCase() !== String(env.ADMIN_EMAIL).toLowerCase()) return null;
  const res = await fetchImpl(env.TEAM_DOMAIN + "/cdn-cgi/access/certs");
  if (!res || !res.ok) return null;
  const jwks = await res.json();
  const jwk = (jwks.keys || []).find((k) => k && k.kid === header.kid && k.kty === "RSA" && k.n && k.e);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey(
    "jwk",
    { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const ok = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlToBytes(parts[2]),
    new TextEncoder().encode(parts[0] + "." + parts[1]),
  );
  return ok ? payload : null;
}

function fail(message) {
  const err = new Error(message);
  err.expose = true;
  return err;
}

function own(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function rejectUnknown(obj, allowed) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) throw fail("expected an object");
  for (const key of Object.keys(obj)) {
    if (!allowed.includes(key)) throw fail("unknown field");
  }
}

function banPrivateKeys(value) {
  if (Array.isArray(value)) {
    value.forEach(banPrivateKeys);
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [key, child] of Object.entries(value)) {
    const name = key.toLowerCase();
    if (name.includes("non_public") || name === "organic_metrics" || name === "promoted_metrics") {
      throw fail("private metrics are not accepted");
    }
    banPrivateKeys(child);
  }
}

function integer(n) {
  if (typeof n !== "number" || !Number.isInteger(n) || n < 0 || n > 1e12) throw fail("count must be a non-negative integer");
  return n;
}

function timestamp(value, now) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value)) {
    throw fail("timestamp must be UTC ISO-8601");
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed) || parsed > now + 5 * 60 * 1000) throw fail("timestamp is in the future");
  return new Date(parsed).toISOString();
}

function metrics(obj, names) {
  rejectUnknown(obj, names);
  const out = {};
  let any = false;
  for (const name of names) {
    if (!own(obj, name) || obj[name] == null) {
      out[name] = null;
      continue;
    }
    out[name] = integer(obj[name]);
    any = true;
  }
  if (!any) throw fail("metrics object is empty");
  return out;
}

export function parseIngest(source, range, body, now) {
  if (source === "tiktok") throw fail("TikTok has no confirmed export schema");
  if (source !== "website" && source !== "x") throw fail("unknown source");
  if (!RANGES.has(range)) throw fail("range must be 7d, 30d, or 90d");
  banPrivateKeys(body);
  if (source === "website") return parseWebsite(body, range, now);
  return parseX(body, range, now);
}

function parseWebsite(body, range, now) {
  rejectUnknown(body, ["source", "range", "fetchedAt", "siteTag", "rows"]);
  if (body.source !== "website" || body.range !== range) throw fail("snapshot does not match the request");
  if (body.siteTag !== SITE_TAG) throw fail("site tag does not match this property");
  if (!Array.isArray(body.rows) || body.rows.length > 200) throw fail("rows are invalid");
  const rows = body.rows.map((row) => {
    rejectUnknown(row, ["requestPath", "count", "visits"]);
    if (typeof row.requestPath !== "string" || !/^\/[A-Za-z0-9._~/-]{0,180}$/.test(row.requestPath)) {
      throw fail("requestPath is invalid");
    }
    return { requestPath: row.requestPath, count: integer(row.count), visits: integer(row.visits) };
  });
  rows.sort((a, b) => a.requestPath.localeCompare(b.requestPath));
  return { source: "website", range, fetchedAt: timestamp(body.fetchedAt, now), siteTag: SITE_TAG, rows };
}

function parseX(body, range, now) {
  rejectUnknown(body, ["source", "range", "fetchedAt", "accounts", "posts"]);
  if (body.source !== "x" || body.range !== range) throw fail("snapshot does not match the request");
  if (!Array.isArray(body.accounts) || body.accounts.length > 20) throw fail("accounts are invalid");
  if (!Array.isArray(body.posts) || body.posts.length > 100) throw fail("posts are invalid");
  const accounts = body.accounts.map((account) => {
    rejectUnknown(account, ["id", "username", "publicMetrics"]);
    if (typeof account.id !== "string" || !/^[0-9]{1,30}$/.test(account.id)) throw fail("account id is invalid");
    if (typeof account.username !== "string" || !/^[A-Za-z0-9_]{1,15}$/.test(account.username)) throw fail("username is invalid");
    return { id: account.id, username: account.username, publicMetrics: metrics(account.publicMetrics, USER_METRICS) };
  });
  const posts = body.posts.map((post) => {
    rejectUnknown(post, ["id", "createdAt", "publicMetrics"]);
    if (typeof post.id !== "string" || !/^[0-9]{1,30}$/.test(post.id)) throw fail("post id is invalid");
    return {
      id: post.id,
      createdAt: post.createdAt == null ? null : timestamp(post.createdAt, now),
      publicMetrics: metrics(post.publicMetrics, POST_METRICS),
    };
  });
  return { source: "x", range, fetchedAt: timestamp(body.fetchedAt, now), accounts, posts };
}

function freshness(fetchedAt, now) {
  const stale = now - Date.parse(fetchedAt) > STALE_MS;
  return { fetchedAt, stale, maxAgeHours: STALE_MS / 3600000 };
}

function disconnected(reason) {
  return { status: "not_connected", reason, freshness: null, metrics: null };
}

export function presentSummary(stored, range, now) {
  return {
    range,
    generatedAt: new Date(now).toISOString(),
    sources: {
      website: presentWebsite(stored.website, now),
      x: presentX(stored.x, now),
      tiktok: disconnected("TikTok is not connected. No official export schema is configured, so imports are refused."),
    },
  };
}

function presentWebsite(entry, now) {
  if (!entry) return disconnected("No website snapshot is stored for this range.");
  if (entry.corrupt) return { status: "error", reason: "Stored website snapshot could not be read.", freshness: null, metrics: null };
  if (entry.missingStorage) return disconnected("Snapshot storage is not configured.");
  const pageLoads = entry.rows.reduce((sum, row) => sum + row.count, 0);
  const visits = entry.rows.reduce((sum, row) => sum + row.visits, 0);
  return {
    status: freshness(entry.fetchedAt, now).stale ? "stale" : "connected",
    reason: entry.rows.length ? null : "Stored snapshot has no page-load rows for this range.",
    freshness: freshness(entry.fetchedAt, now),
    metrics: {
      kind: "cloudflare_web_analytics",
      siteTag: entry.siteTag,
      note: "pageLoads is the Cloudflare count of page-load events. visits is sum.visits. Neither is a verified unique-visitor or organic-visitor count. Referrers are omitted until that dimension is confirmed.",
      pageLoads,
      visits,
      byPath: entry.rows.map((row) => ({ path: row.requestPath, pageLoads: row.count, visits: row.visits })),
      referrers: null,
    },
  };
}

function presentX(entry, now) {
  if (!entry) return disconnected("No X snapshot is stored for this range.");
  if (entry.corrupt) return { status: "error", reason: "Stored X snapshot could not be read.", freshness: null, metrics: null };
  if (entry.missingStorage) return disconnected("Snapshot storage is not configured.");
  return {
    status: freshness(entry.fetchedAt, now).stale ? "stale" : "connected",
    reason: null,
    freshness: freshness(entry.fetchedAt, now),
    metrics: {
      kind: "x_public_metrics",
      note: "Public profile and post metrics only. Private metric objects are rejected and are not stored.",
      accounts: entry.accounts,
      posts: entry.posts,
    },
  };
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function metricCell(value) {
  return value == null ? "<td>not in snapshot</td>" : "<td>" + esc(value) + "</td>";
}

function websiteHtml(source) {
  if (!source.metrics) return "<p>" + esc(source.reason) + "</p>";
  const rows = source.metrics.byPath.map((row) =>
    "<tr><td>" + esc(row.path) + "</td><td>" + esc(row.pageLoads) + "</td><td>" + esc(row.visits) + "</td></tr>",
  ).join("");
  const empty = source.reason ? "<p>" + esc(source.reason) + "</p>" : "";
  return empty + "<p>" + esc(source.metrics.note) + "</p>"
    + "<p>Page loads: " + esc(source.metrics.pageLoads) + ". Visits (sum.visits): " + esc(source.metrics.visits) + ".</p>"
    + "<table><thead><tr><th>Path</th><th>Page loads</th><th>Visits</th></tr></thead><tbody>"
    + (rows || "<tr><td colspan=\"3\">No rows</td></tr>") + "</tbody></table>"
    + "<p>Referrers: not in the confirmed query.</p>";
}

function xHtml(source) {
  if (!source.metrics) return "<p>" + esc(source.reason) + "</p>";
  const accounts = source.metrics.accounts.map((account) => {
    const m = account.publicMetrics;
    return "<li>@" + esc(account.username) + " followers " + (m.followers_count == null ? "not in snapshot" : esc(m.followers_count)) + "</li>";
  }).join("");
  const posts = source.metrics.posts.map((post) => {
    const m = post.publicMetrics;
    return "<tr><td>" + esc(post.id) + "</td>" + metricCell(m.impression_count) + metricCell(m.like_count)
      + metricCell(m.reply_count) + metricCell(m.retweet_count) + "</tr>";
  }).join("");
  return "<p>" + esc(source.metrics.note) + "</p><ul>" + (accounts || "<li>No accounts in this snapshot</li>") + "</ul>"
    + "<table><thead><tr><th>Post</th><th>Impressions</th><th>Likes</th><th>Replies</th><th>Reposts</th></tr></thead><tbody>"
    + (posts || "<tr><td colspan=\"5\">No posts in this snapshot</td></tr>") + "</tbody></table>";
}

export function renderDashboard(summary, options = {}) {
  const banner = options.example ? "<p class=\"banner\">EXAMPLE DATA. Not live. Not deployed. These figures are fixtures.</p>" : "";
  const nav = ["7d", "30d", "90d"].map((range) => {
    const current = range === summary.range ? " aria-current=\"true\"" : "";
    return "<a" + current + " href=\"/?range=" + range + "\">" + range + "</a>";
  }).join("");
  const card = (title, source, inner) => {
    const when = source.freshness
      ? "<p>Fetched " + esc(source.freshness.fetchedAt) + (source.freshness.stale ? " (stale)" : " (fresh)") + ".</p>"
      : "";
    return "<section><h2>" + title + "</h2><p class=\"status\" data-status=\"" + esc(source.status) + "\">"
      + esc(source.status.replace("_", " ")) + "</p>" + when + inner(source) + "</section>";
  };
  return "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    + "<meta name=\"robots\" content=\"noindex, nofollow\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    + "<title>LJI admin</title><style>"
    + "body{margin:0;font:16px/1.45 system-ui,sans-serif;background:#f6f7f9;color:#142033}"
    + "main{max-width:1100px;margin:0 auto;padding:24px}h1{font-size:1.4rem}nav{display:flex;gap:8px;margin:12px 0}"
    + "a{color:#1d4ed8}a[aria-current]{font-weight:700}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}"
    + "section{background:#fff;border:1px solid #d5dbe6;border-radius:12px;padding:16px}table{width:100%;border-collapse:collapse}"
    + "td,th{border-bottom:1px solid #e6ebf2;text-align:left;padding:6px;font-size:.92rem}.status{font-weight:700}"
    + ".banner{background:#fff4cc;border:1px solid #e2b100;padding:10px;border-radius:8px}"
    + "@media(max-width:800px){.grid{grid-template-columns:1fr}}"
    + "</style></head><body><main>" + banner + "<h1>LJI admin</h1>"
    + "<p>Website, X, and TikTok stay separate. Missing data is not shown as zero.</p><nav>" + nav + "</nav><div class=\"grid\">"
    + card("Website", summary.sources.website, websiteHtml)
    + card("X", summary.sources.x, xHtml)
    + card("TikTok", summary.sources.tiktok, (source) => "<p>" + esc(source.reason) + "</p>")
    + "</div></main></body></html>";
}

async function loadEntry(kv, source, range) {
  if (!kv) return { missingStorage: true };
  const raw = await kv.get(source + ":" + range);
  if (raw == null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return { corrupt: true };
  }
}

export async function handle(request, env, deps = {}) {
  const now = deps.now ? deps.now() : Date.now();
  const url = new URL(request.url);
  if (!configured(env) || !hostAllowed(url.hostname, env.ADMIN_HOST)) return text(403, "forbidden");
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!token) return text(401, "authentication required");
  const identity = await verifyAccessJwt(token, env, deps.fetch || fetch, now);
  if (!identity) return text(403, "forbidden");

  const range = url.searchParams.get("range") || "7d";
  if (!RANGES.has(range)) return json(400, { error: "range must be 7d, 30d, or 90d" });
  const kv = deps.kv || env.SNAPSHOTS || null;

  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/api/summary")) {
    const summary = presentSummary({
      website: await loadEntry(kv, "website", range),
      x: await loadEntry(kv, "x", range),
      tiktok: null,
    }, range, now);
    if (url.pathname === "/api/summary") return json(200, summary);
    return new Response(renderDashboard(summary), {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-store",
        "x-robots-tag": "noindex, nofollow",
        "referrer-policy": "no-referrer",
        "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        "x-content-type-options": "nosniff",
      },
    });
  }

  const ingest = url.pathname.match(/^\/api\/ingest\/(website|x|tiktok)$/);
  if (request.method === "POST" && ingest) {
    const site = request.headers.get("sec-fetch-site");
    if (site && site !== "same-origin") return text(403, "forbidden");
    if (ingest[1] === "tiktok") return json(422, { error: "TikTok has no confirmed export schema" });
    if (!kv) return json(503, { error: "snapshot storage is not configured" });
    const type = (request.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
    if (type !== "application/json") return json(415, { error: "content-type must be application/json" });
    const raw = await request.text();
    if (raw.length > MAX_BODY) return json(413, { error: "snapshot is too large" });
    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      return json(400, { error: "invalid JSON" });
    }
    try {
      const snapshot = parseIngest(ingest[1], range, body, now);
      await kv.put(ingest[1] + ":" + range, JSON.stringify(snapshot));
      return json(200, { stored: true });
    } catch (err) {
      return json(400, { error: err.expose ? err.message : "invalid snapshot" });
    }
  }

  if (request.method !== "GET" && request.method !== "POST") return text(405, "method not allowed");
  return text(404, "not found");
}

export default {
  fetch(request, env) {
    return handle(request, env);
  },
};
