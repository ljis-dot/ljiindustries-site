#!/usr/bin/env python3
"""Build static Briefed pages from editions/YYYY-MM-DD.json (public schema v1).

Usage: python3 tools/build_briefed.py [--root .] [--preview EDITION.json]
--preview builds a local-only preview from one edition (it ignores the launch date and
does not touch the sitemap). Output always goes under <root>/briefed/.
No dependencies. Shared look: the CSS is copied from index.html's <style> at build time.
"""
import argparse, html, json, os, re, shutil, sys
from datetime import date

LAUNCH = "2026-10-25"
SITE = "https://ljiindustries.com"
FORBIDDEN = [re.compile(p, re.I) for p in [r"\$\s?\d+\s?(/mo|per month|a month)", r"\bpricing\b", r"\bsubscribe now\b"]]
MAX_FOREIGN = 2
# Owner-name guard stored as sha256 of the lowercased word, so the name itself is never in the repo.
import hashlib
NAME_HASHES = {"401c866f250a30540d403f4dd498cf7ace2222bb90eb68a5bff5823fb20dc643"}

e = html.escape

def load_editions(d):
    out = []
    if not os.path.isdir(d): return out
    for n in sorted(os.listdir(d)):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", n):
            out.append(validate(json.load(open(os.path.join(d, n)))))
    return out

def validate(ed):
    assert ed.get("schemaVersion") == 1, "schemaVersion must be 1"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ed["date"])
    foreign = [s for s in ed["stories"] if s.get("region") == "foreign"]
    assert len(foreign) <= MAX_FOREIGN, f"{ed['date']}: more than {MAX_FOREIGN} foreign stories"
    for s in foreign:
        assert s.get("whyItMattersToUS"), f"{ed['date']}: foreign story {s['id']} lacks whyItMattersToUS"
    for s in ed["stories"]:
        s.pop("quotes", None); s.pop("claims", None)  # verification quotes OFF
    blob = json.dumps(ed)
    for w in set(re.findall(r"[a-z]+", blob.lower())):
        assert hashlib.sha256(w.encode()).hexdigest() not in NAME_HASHES, f"{ed['date']}: owner name found"
    for p in FORBIDDEN:
        assert not p.search(blob), f"{ed['date']}: forbidden text matched {p.pattern}"
    return ed

def site_css(root):
    src = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    m = re.search(r"<style>(.*?)</style>", src, re.S)
    return m.group(1).strip()

def header(root_rel="/"):
    return f'''<header class="nav">
  <div class="wrap">
    <a href="/" class="logo" aria-label="LJI Industries home">
      <img class="logo-lockup" src="/logo-lockup.svg" alt="LJI Industries, practical AI for small business" width="218" height="46">
    </a>
    <button class="menu-btn" aria-label="Open menu" aria-expanded="false" onclick="var n=document.getElementById('nav');n.classList.toggle('open');this.setAttribute('aria-expanded',n.classList.contains('open'))">&#9776;</button>
    <ul class="nav-links" id="nav">
      <li><a href="/#services">Services</a></li>
      <li><a href="/briefed/">Today's Briefed</a></li>
      <li><a href="/briefed/archive/">Archive</a></li>
      <li><a href="/briefed/about/">About Briefed</a></li>
    </ul>
  </div>
</header>'''

FOOTER = '''<footer>
  <div class="wrap">
    <div class="foot-grid">
      <div>
        <a href="/" class="logo"><img class="logo-icon" src="/favicon.svg" alt="" width="34" height="34"><span>LJI Industries LLC</span></a>
        <p style="margin-top:12px;max-width:320px">Practical AI consulting for small businesses. Makers of Briefed.</p>
      </div>
      <div><h4>Briefed</h4><ul><li><a href="/briefed/">Today's edition</a></li><li><a href="/briefed/archive/">Archive</a></li><li><a href="/briefed/about/">About</a></li></ul></div>
      <div><h4>Company</h4><ul><li><a href="/#services">Services</a></li><li><a href="/#faq">FAQ</a></li></ul></div>
      <div><h4>Contact</h4><ul><li><a href="mailto:info@ljiindustries.com">info@ljiindustries.com</a></li><li>ljiindustries.com</li></ul></div>
    </div>
    <div class="foot-bottom"><span>&copy; <span id="yr">2026</span> LJI Industries LLC. All rights reserved.</span></div>
  </div>
</footer>
<!-- slot:subscribe (follow/subscribe is OFF for now; render here later) -->
<script>document.getElementById('yr').textContent=new Date().getFullYear();document.querySelectorAll('#nav a').forEach(function(a){a.addEventListener('click',function(){document.getElementById('nav').classList.remove('open');});});</script>'''

def page(title, desc, canonical, body, jsonld=None, extra_head=""):
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}{canonical}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png" sizes="180x180">
<link rel="manifest" href="/briefed/manifest.webmanifest">
<meta name="theme-color" content="#1d4ed8">
<meta name="apple-mobile-web-app-title" content="Briefed">
<meta property="og:type" content="website"><meta property="og:site_name" content="LJI Industries">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{SITE}{canonical}"><meta property="og:image" content="{SITE}/og-image.png">
<link rel="stylesheet" href="/briefed/site.css">
<link rel="stylesheet" href="/briefed/briefed.css">
<link rel="alternate" type="application/json" href="/briefed/latest.json" title="Briefed latest edition (JSON)">
{ld}{extra_head}
</head>
<body>
{header()}
<main id="top">
{body}
</main>
{FOOTER}
</body>
</html>
'''

def long_date(d):
    y, m, dd = map(int, d.split("-"))
    return date(y, m, dd).strftime("%A, %B %-d, %Y")

def fmt_t(s):
    s = int(s); return f"{s//60}:{s%60:02d}"

def chapter_map(ed):
    a = ed.get("audio") or {}
    return {c["storyId"]: c for c in a.get("chapters", []) if c.get("storyId")}

def story_card(s, n, chap):
    badge = {"cleared": ("Cleared", "ok"), "sourced": ("Sourced", "ok"), "reported-only": ("Reported only", "warn")}.get(s.get("status"), (s.get("statusLabel") or s.get("status", "").title(), "warn"))
    region = "World" if s.get("region") == "foreign" else "U.S."
    loc = f' · {e(s["location"])}' if s.get("location") else ""
    summ = f'<p class="b-sum">{e(s["summary"])}</p>' if s.get("summary") else ""
    why = f'<p class="b-why"><strong>Why it matters to the US:</strong> {e(s["whyItMattersToUS"])}</p>' if s.get("whyItMattersToUS") else ""
    outs = "".join(
        (f'<a class="b-chip" href="{e(o["url"])}" rel="noopener nofollow" target="_blank">{e(o["name"])}</a>' if o.get("url") else f'<span class="b-chip">{e(o["name"])}</span>')
        for o in s.get("outlets", []))
    offs = "".join(f'<a href="{e(u)}" rel="noopener nofollow" target="_blank">{e(re.sub(r"^https?://(www\\.)?", "", u).split("/")[0])}</a>' for u in s.get("officialSources", []))
    offs = f'<p class="b-off">Checked against: {offs}</p>' if offs else ""
    note = f'<p class="b-note">{e(s["statusNote"])}</p>' if s.get("statusNote") else ""
    listen = (f'<button class="b-listen" type="button" data-start="{chap["start"]:.3f}" data-story="{e(s["id"])}" aria-label="Listen to this story, starts at {fmt_t(chap["start"])}">&#9654; Listen <span>{fmt_t(chap["start"])}</span></button>') if chap else ""
    lead = " b-lead" if n == 0 else ""
    return f'''<article class="b-story card{lead}" id="story-{e(s["id"])}" data-story="{e(s["id"])}">
  <div class="b-meta"><span class="eyebrow">{"Lead story · " if n == 0 else ""}{region}{loc}</span><span class="b-badge {badge[1]}">{e(badge[0])}</span></div>
  <h2 class="b-head">{e(s["headline"])}</h2>
  {summ}{why}{note}
  <div class="b-chips" aria-label="Original reporting">{outs}</div>
  {offs}
  {listen}
</article>'''

def player(ed):
    a = ed.get("audio")
    if not a or not a.get("url"): return "", ""
    items = []
    for c in a["chapters"]:
        items.append(f'<li><button type="button" data-start="{c["start"]:.3f}" data-story="{e(c.get("storyId") or "")}"><span class="t">{fmt_t(c["start"])}</span> {e(c["title"])}</button></li>')
    html_ = f'''<section class="b-player card" aria-label="Listen to today's edition">
  <div class="b-player-top"><strong>Listen to the edition</strong> <span class="b-ai" title="Audio narrated by AI-generated voices from Briefed's written edition.">AI-voiced</span> <span class="b-dur">{fmt_t(a.get("durationSeconds", 0))}</span></div>
  <audio id="b-audio" controls preload="metadata" src="{e(a["url"])}"></audio>
  <p class="b-disclose">Audio narrated by AI-generated voices from Briefed's written edition.</p>
  <ol class="b-chapters">{"".join(items)}</ol>
</section>'''
    js = '''<script>
(function(){var au=document.getElementById('b-audio');if(!au)return;
function go(t){au.currentTime=t;var p=au.play();if(p&&p.catch)p.catch(function(){});}
document.querySelectorAll('[data-start]').forEach(function(b){b.addEventListener('click',function(){go(parseFloat(b.dataset.start));});});
var marks=[].slice.call(document.querySelectorAll('.b-chapters button')).map(function(b){return{t:parseFloat(b.dataset.start),id:b.dataset.story,el:b};});
au.addEventListener('timeupdate',function(){var cur=null;marks.forEach(function(m){if(au.currentTime>=m.t-0.05)cur=m;});
marks.forEach(function(m){m.el.classList.toggle('on',m===cur);});
document.querySelectorAll('.b-story').forEach(function(s){s.classList.toggle('playing',!!cur&&cur.id===s.dataset.story);});});
})();
</script>'''
    return html_, js

def edition_body(ed, is_latest):
    chaps = chapter_map(ed)
    pl, js = player(ed)
    cards = "\n".join(story_card(s, i, chaps.get(s["id"])) for i, s in enumerate(ed["stories"]))
    label = "Today's edition" if is_latest else "Edition"
    return f'''<section class="b-hero"><div class="wrap b-narrow">
  <span class="eyebrow">Briefed · {label}</span>
  <h1>{e(long_date(ed["date"]))}</h1>
  <p class="lead">The facts on things that really happened, with links to the original reporting and the official sources.</p>
  <p class="b-sub"><a href="/briefed/archive/">Past editions</a> · <a href="/briefed/about/">About Briefed</a> · <a href="/briefed/{ed["date"]}.json">JSON</a></p>
</div></section>
<section class="b-main"><div class="wrap b-narrow">
{pl}
{cards}
<p class="b-fine">Headlines and summaries are written by Briefed. Each story links to the original reporting; we do not republish article text.</p>
</div></section>
{js}'''

def jsonld_ed(ed, url):
    return {"@context": "https://schema.org", "@type": "ItemList", "name": f"Briefed: {long_date(ed['date'])}",
            "datePublished": ed.get("generatedAt", ed["date"]), "url": SITE + url,
            "publisher": {"@type": "Organization", "name": "LJI Industries LLC", "url": SITE},
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": {"@type": "NewsArticle", "headline": s["headline"],
                "citation": [o["url"] for o in s.get("outlets", []) if o.get("url")] + s.get("officialSources", [])}} for i, s in enumerate(ed["stories"])]}

EMPTY = '''<section class="b-hero"><div class="wrap b-narrow">
  <span class="eyebrow">Briefed · Daily edition</span>
  <h1>First edition arrives tomorrow morning</h1>
  <p class="lead">Briefed's first US-focused daily edition publishes here on Sunday, October 25, 2026, around 4:45 AM ET: the facts on the day's stories, with links to the original reporting and the official sources, plus an AI-voiced audio edition.</p>
  <p class="b-sub"><a href="/briefed/about/">About Briefed</a></p>
</div></section>'''

ABOUT = '''<section class="b-hero"><div class="wrap b-narrow">
  <span class="eyebrow">About Briefed</span>
  <h1>Why Briefed exists</h1>
  <p class="lead">I got tired of partisan news: slanted headlines, endless opinion, and spin on top of every story, when all I wanted was the facts.</p>
</div></section>
<section class="b-main"><div class="wrap b-narrow"><div class="card b-about">
  <p>Briefed strips out the extra opinion and gives you the facts on things that really happened.</p>
  <p>Every story links to the original reporting and the official sources, so you can check it yourself.</p>
  <p>The audio is AI-voiced from the written edition. <span class="b-ai">AI-voiced</span></p>
  <p class="b-sub"><a href="/briefed/">Read today's edition</a> · <a href="/briefed/archive/">Past editions</a></p>
</div></div></section>'''

BRIEFED_CSS = '''/* Briefed pages: built only on the site's tokens (see site.css :root). Mobile-first. */
.b-narrow{max-width:780px}
.b-hero{padding:40px 0 8px}
.b-hero h1{font-size:clamp(1.7rem,6vw,2.6rem)}
.b-hero .lead{margin-top:10px}
.b-sub{margin-top:12px;color:var(--muted);font-size:.95rem}
.b-main{padding:20px 0 64px}
.card{background:#fff;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:20px}
.b-story{margin-top:16px;transition:border-color .2s,box-shadow .2s}
.b-story.b-lead{border-top:4px solid var(--brand)}
.b-story.playing{border-color:var(--brand);box-shadow:0 0 0 3px rgba(29,78,216,.15),var(--shadow)}
.b-meta{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.b-meta .eyebrow{margin-bottom:0}
.b-head{font-size:1.22rem;margin:8px 0 6px;font-weight:800}
.b-lead .b-head{font-size:1.45rem}
.b-sum{color:var(--ink2)}
.b-why{margin-top:8px;padding:10px 12px;background:var(--soft);border-left:3px solid var(--brand2);border-radius:8px;color:var(--ink2);font-size:.96rem}
.b-note{margin-top:6px;color:var(--muted);font-size:.9rem}
.b-badge{font-size:.75rem;font-weight:700;padding:3px 10px;border-radius:999px;white-space:nowrap}
.b-badge.ok{background:rgba(29,78,216,.1);color:var(--brand2)}
.b-badge.warn{background:rgba(245,158,11,.15);color:#92400e}
.b-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.b-chip{font-size:.82rem;padding:4px 10px;border:1px solid var(--line);border-radius:999px;color:var(--ink2);background:var(--soft)}
a.b-chip:hover{border-color:var(--brand);text-decoration:none;color:var(--brand)}
.b-off{margin-top:8px;font-size:.88rem;color:var(--muted)}
.b-off a{margin-left:6px}
.b-listen{margin-top:14px;min-height:44px;padding:10px 16px;border-radius:10px;border:2px solid var(--brand);background:#fff;color:var(--brand);font-weight:700;font-size:.95rem;cursor:pointer}
.b-listen span{color:var(--muted);font-weight:600;margin-left:4px}
.b-listen:hover,.b-story.playing .b-listen{background:var(--brand);color:#fff}
.b-story.playing .b-listen span{color:#dbeafe}
.b-player{position:sticky;top:76px;z-index:20;margin-top:8px}
.b-player-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.b-ai{display:inline-block;font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;padding:2px 8px;border-radius:6px;background:var(--brand);color:#fff}
.b-dur{color:var(--muted);font-size:.9rem;margin-left:auto}
.b-player audio{width:100%;margin-top:10px}
.b-disclose{font-size:.82rem;color:var(--muted);margin-top:4px}
.b-chapters{list-style:none;margin-top:10px;display:grid;gap:4px;max-height:220px;overflow:auto}
.b-chapters button{width:100%;text-align:left;min-height:40px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--soft);color:var(--ink);font:inherit;font-size:.92rem;cursor:pointer}
.b-chapters button .t{color:var(--muted);font-variant-numeric:tabular-nums;margin-right:6px}
.b-chapters button.on{border-color:var(--brand);background:rgba(29,78,216,.08);color:var(--brand2);font-weight:700}
.b-fine{margin-top:24px;font-size:.85rem;color:var(--muted)}
.b-arch h2{font-size:1.1rem;margin:22px 0 8px;color:var(--ink2)}
.b-arch ul{list-style:none;display:grid;gap:8px}
.b-arch li a{display:block;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:#fff;color:var(--ink)}
.b-arch li a:hover{border-color:var(--brand);text-decoration:none}
.b-arch .d{display:block;font-weight:700;color:var(--brand)}
.b-about p{margin-top:10px;color:var(--ink2);font-size:1.05rem}
@media (max-width:640px){.b-player{position:static;padding:14px}.b-chapters{max-height:140px}.card{padding:16px}.b-hero{padding:28px 0 4px}}
@media (min-width:900px){.b-player{top:84px}}
'''

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)

def public_json(ed):
    keep = ["schemaVersion", "date", "generatedAt", "stories", "audio"]
    return {k: ed[k] for k in keep if k in ed}

def build(root, editions, preview=False):
    out = os.path.join(root, "briefed")
    for sub in os.listdir(out) if os.path.isdir(out) else []:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(\.json)?", sub):
            p = os.path.join(out, sub); shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    write(os.path.join(out, "site.css"), "/* generated from /index.html <style>; do not edit */\n" + site_css(root) + "\n")
    write(os.path.join(out, "briefed.css"), BRIEFED_CSS)
    write(os.path.join(out, "manifest.webmanifest"), json.dumps({
        "name": "Briefed", "short_name": "Briefed", "description": "The facts on the day's stories, with links to the original reporting.",
        "start_url": "/briefed/", "scope": "/briefed/", "display": "standalone", "theme_color": "#1d4ed8", "background_color": "#ffffff",
        "icons": [{"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
                  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}, indent=2))
    if not preview:
        editions = [x for x in editions if x["date"] >= LAUNCH]
    editions.sort(key=lambda x: x["date"], reverse=True)
    for i, ed in enumerate(editions):
        url = f"/briefed/{ed['date']}/"
        desc = f"Briefed for {long_date(ed['date'])}: " + "; ".join(s["headline"] for s in ed["stories"][:3])
        write(os.path.join(out, ed["date"], "index.html"), page(f"Briefed: {long_date(ed['date'])}", desc[:300], url, edition_body(ed, i == 0), jsonld_ed(ed, url)))
        write(os.path.join(out, f"{ed['date']}.json"), json.dumps(public_json(ed), indent=1))
    if editions:
        latest = editions[0]
        write(os.path.join(out, "index.html"), page("Briefed: today's edition | LJI Industries", f"Briefed for {long_date(latest['date'])}: the facts on the day's stories, with links to the original reporting and official sources.", f"/briefed/{latest['date']}/", edition_body(latest, True), jsonld_ed(latest, "/briefed/")))
        write(os.path.join(out, "latest.json"), json.dumps(public_json(latest), indent=1))
    else:
        write(os.path.join(out, "index.html"), page("Briefed: daily edition | LJI Industries", "Briefed's first US-focused daily edition arrives Sunday, October 25, 2026.", "/briefed/", EMPTY))
        write(os.path.join(out, "latest.json"), json.dumps({"schemaVersion": 1, "date": None, "message": "First edition arrives 2026-10-25."}))
    idx = [{"date": x["date"], "lead": x["stories"][0]["headline"] if x["stories"] else None, "url": f"/briefed/{x['date']}/", "json": f"/briefed/{x['date']}.json", "hasAudio": bool(x.get("audio"))} for x in editions]
    write(os.path.join(out, "index.json"), json.dumps({"schemaVersion": 1, "editions": idx}, indent=1))
    # archive
    if idx:
        groups, cur = [], None
        for it in idx:
            m = date.fromisoformat(it["date"]).strftime("%B %Y")
            if m != cur: groups.append((m, [])); cur = m
            groups[-1][1].append(it)
        lists = "".join(f'<h2>{m}</h2><ul>' + "".join(f'<li><a href="{it["url"]}"><span class="d">{e(long_date(it["date"]))}{" · 🎧" if it["hasAudio"] else ""}</span>{e(it["lead"] or "")}</a></li>' for it in items) + "</ul>" for m, items in groups)
    else:
        lists = '<p class="lead">No editions yet. The first edition arrives Sunday, October 25, 2026.</p>'
    body = f'<section class="b-hero"><div class="wrap b-narrow"><span class="eyebrow">Briefed · Archive</span><h1>Past editions</h1></div></section><section class="b-main"><div class="wrap b-narrow b-arch">{lists}</div></section>'
    write(os.path.join(out, "archive", "index.html"), page("Briefed archive: past editions | LJI Industries", "Every Briefed daily edition by date.", "/briefed/archive/", body))
    write(os.path.join(out, "about", "index.html"), page("About Briefed | LJI Industries", "Why Briefed exists: the facts on things that really happened, with links to the original reporting and official sources.", "/briefed/about/", ABOUT))
    if not preview:
        sitemap(root, editions)
    return editions

def sitemap(root, editions):
    p = os.path.join(root, "sitemap.xml")
    s = open(p).read()
    s = re.sub(r"\s*<url><loc>https://ljiindustries.com/briefed/[^<]*</loc>.*?</url>", "", s)
    today = editions[0]["date"] if editions else "2026-10-24"
    urls = [("/briefed/", today), ("/briefed/archive/", today), ("/briefed/about/", "2026-10-24")] + [(f"/briefed/{x['date']}/", x["date"]) for x in editions]
    add = "".join(f"\n  <url><loc>{SITE}{u}</loc><lastmod>{d}</lastmod></url>" for u, d in urls)
    s = s.replace("\n</urlset>", add + "\n</urlset>")
    open(p, "w").write(s)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--preview", help="local-only: build from this one edition file, ignore launch date, skip sitemap")
    a = ap.parse_args()
    eds = [validate(json.load(open(a.preview)))] if a.preview else load_editions(os.path.join(a.root, "editions"))
    got = build(a.root, eds, preview=bool(a.preview))
    print(f"built {len(got)} edition(s): {[x['date'] for x in got]}")
