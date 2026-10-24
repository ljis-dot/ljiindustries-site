#!/usr/bin/env python3
"""Build static Briefed pages from editions/YYYY-MM-DD.json (public schema v1).

Usage: python3 tools/build_briefed.py [--root .] [--preview EDITION.json]
--preview builds a local-only preview from one edition (it ignores the launch date and
does not touch the sitemap). Output always goes under <root>/briefed/.
No dependencies. Shared look: the CSS is copied from index.html's <style> at build time.
"""
import argparse, html, json, os, re, shutil, sys
from datetime import date

LAUNCH = "2026-10-24"  # first published day (Levi, 2026-10-24 review edition)
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

def short_date(d):
    y, m, dd = map(int, d.split("-"))
    return date(y, m, dd).strftime("%a, %b %-d, %Y")

def media_chapters(ed):
    v = ed.get("video") or {}
    if v.get("url") and v.get("chapters"): return v["chapters"]
    return (ed.get("audio") or {}).get("chapters", [])

AI_TITLE = "Narrated by AI-generated voices from Briefed's written edition."

def player(ed):
    """Compact media block. Video (if present) on top with a synced story panel; else a one-line audio player."""
    v, a = ed.get("video") or {}, ed.get("audio") or {}
    has_video = bool(v.get("url"))
    if not has_video and not a.get("url"): return "", ""
    chaps = media_chapters(ed)
    items = "".join('<li><button type="button" data-start="%.3f" data-end="%.3f" data-story="%s"><span class="t">%s</span> %s</button></li>'
                    % (c["start"], c.get("end") or 0, e(c.get("storyId") or ""), fmt_t(c["start"]), e(c["title"])) for c in chaps)
    dur = (v if has_video else a).get("durationSeconds") or 0
    toggle = ('<details class="b-chap"><summary>Chapters (%d)</summary><ol class="b-chapters">%s</ol></details>' % (len(chaps), items)) if chaps else ""
    ai = '<span class="b-ai" title="%s">AI-voiced</span>' % e(AI_TITLE)
    if has_video:
        poster = ' poster="%s"' % e(v["poster"]) if v.get("poster") else ""
        media = ('<div class="b-grid"><div class="b-video-wrap"><video id="b-media" class="b-video" controls playsinline preload="metadata"%s src="%s"></video></div>\n'
                 '<div id="b-panel" class="b-panel" aria-live="polite"><p class="b-panel-empty">Press play: the story being read shows here.</p></div></div>\n'
                 '<div class="b-mbar">%s<span class="b-mlabel">Video edition &middot; %s</span>%s</div>') % (poster, e(v["url"]), ai, fmt_t(dur), toggle)
    else:
        media = ('<audio id="b-media" preload="metadata" src="%s"></audio>\n'
                 '<noscript><audio controls preload="none" src="%s"></audio></noscript>\n'
                 '<div class="b-mbar"><button type="button" class="b-play" id="b-play" aria-label="Play">&#9654;</button>'
                 '<input type="range" id="b-seek" class="b-seek" min="0" max="%.1f" step="0.1" value="0" aria-label="Seek">'
                 '<span class="b-time" id="b-time">0:00 / %s</span>%s%s</div>') % (e(a["url"]), e(a["url"]), dur, fmt_t(dur), ai, toggle)
    html_ = '<section class="b-player card%s" aria-label="Listen to or watch the edition">\n%s\n</section>' % (" b-has-video" if has_video else "", media)
    return html_, "<script>" + open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefed_player.js")).read() + "</script>"

BADGES = {"cleared": ("Cleared", "ok"), "sourced": ("Sourced", "ok"), "reported-only": ("Reported only", "warn")}

def panel_data(ed):
    out = {}
    for i, s in enumerate(ed["stories"]):
        bd = BADGES.get(s.get("status"), (s.get("status", "").title(), "warn"))
        kick = ("Lead story · " if i == 0 else "") + ("World" if s.get("region") == "foreign" else "U.S.") + ((" · " + s["location"]) if s.get("location") else "")
        out[s["id"]] = {"headline": s["headline"], "summary": s.get("summary"), "why": s.get("whyItMattersToUS"), "statusNote": s.get("statusNote"),
                        "badge": bd[0], "badgeClass": bd[1], "kicker": kick, "outlets": s.get("outlets", []), "officialSources": s.get("officialSources", [])}
    return json.dumps({"stories": out}).replace("</", "<\\/")

def daynav(prev_day, next_day):
    if not prev_day and not next_day: return ""  # only one edition: hide the row
    pv = ('<a class="b-pn" href="/briefed/%s/" rel="prev">&larr; Previous day</a>' % prev_day) if prev_day else '<span class="b-pn off" aria-disabled="true">&larr; Previous day</span>'
    nx = ('<a class="b-pn" href="/briefed/%s/" rel="next">Next day &rarr;</a>' % next_day) if next_day else '<span class="b-pn off" aria-disabled="true">Next day &rarr;</span>'
    return '<nav class="b-daynav" aria-label="Edition by day">%s%s</nav>' % (pv, nx)

def daynav_inline(prev_day, next_day):
    pv = ('<a class="b-pi" href="/briefed/%s/" rel="prev" title="Previous day">&larr; Prev</a>' % prev_day) if prev_day else '<span class="b-pi off" aria-disabled="true" title="No earlier edition">&larr; Prev</span>'
    nx = ('<a class="b-pi" href="/briefed/%s/" rel="next" title="Next day">Next &rarr;</a>' % next_day) if next_day else '<span class="b-pi off" aria-disabled="true" title="This is the latest edition">Next &rarr;</span>'
    return pv + nx

def edition_body(ed, is_latest, prev_day=None, next_day=None):
    chaps = {c["storyId"]: c for c in media_chapters(ed) if c.get("storyId")}
    pl, js = player(ed)
    cards = "\n".join(story_card(s, i, chaps.get(s["id"])) for i, s in enumerate(ed["stories"]))
    d = ed["date"]
    nav = daynav(prev_day, next_day)
    return ('<div class="b-stick" id="b-stick"><div class="wrap b-narrow">\n'
      '<div class="b-topline"><h1 class="b-h1"><span class="eyebrow">Briefed &middot; %s</span> <time datetime="%s">%s</time></h1>'
      '<span class="b-links">%s<a href="/briefed/archive/">Archive</a><a href="/briefed/about/">About</a></span></div>\n'
      '%s\n</div></div>\n'
      '<section class="b-main"><div class="wrap b-narrow">\n<p class="b-tag">Just the facts, with sources. <a href="/briefed/%s.json">JSON</a></p>\n%s\n%s\n'
      '<p class="b-fine">Headlines and summaries are written by Briefed. Each story links to the original reporting; we do not republish article text.</p>\n'
      '</div></section>\n<script type="application/json" id="b-data">%s</script>\n%s') % (
      "Today" if is_latest else "Edition", d, e(short_date(d)), daynav_inline(prev_day, next_day), pl, d, cards, nav, panel_data(ed), js)


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
.b-player{position:sticky;top:76px;z-index:20;margin-top:4px;padding:10px 12px}
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
.b-top{padding:14px 0 4px}
.b-topline{display:flex;align-items:baseline;justify-content:space-between;gap:6px 14px;flex-wrap:wrap}
.b-h1{font-size:1.05rem;font-weight:800;letter-spacing:-.01em;margin:0;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.b-h1 .eyebrow{margin:0;font-size:.72rem}
.b-links{display:flex;gap:12px;font-size:.85rem}
.b-tag{color:var(--muted);font-size:.88rem;margin-top:2px}
.b-daynav{display:flex;justify-content:space-between;gap:8px;margin-top:8px;font-size:.88rem}
.b-main .b-daynav{margin-top:20px}
.b-pn{padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;font-weight:600;min-height:36px;display:inline-flex;align-items:center}
a.b-pn:hover{border-color:var(--brand);text-decoration:none}
.b-pn.off{color:var(--muted);opacity:.45}
.b-main{padding:8px 0 48px}
.b-mbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.b-play{width:40px;height:40px;flex:0 0 40px;border-radius:50%;border:0;background:var(--brand);color:#fff;font-size:.95rem;cursor:pointer;line-height:1}
.b-play:hover{background:var(--brand2)}
.b-seek{flex:1 1 120px;min-width:90px;accent-color:var(--brand);height:28px}
.b-time{font-size:.82rem;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.b-mlabel{font-size:.85rem;color:var(--muted)}
.b-chap{font-size:.85rem;border:0!important;padding:0!important;margin:0!important;background:none!important;box-shadow:none!important}
.b-chap summary{cursor:pointer;color:var(--brand);font-weight:700;list-style:none;padding:5px 10px;border:1px solid var(--line);border-radius:999px}
.b-chap summary::-webkit-details-marker{display:none}
.b-chap summary::after{content:" ▾";transform:none!important;position:static!important;font-size:inherit;color:inherit;margin:0!important}
.b-chap[open] summary::after{content:" ▴"}
.b-chap[open]{flex-basis:100%}
.b-player.b-has-video{position:static}
.b-video-wrap{margin-bottom:8px;border-radius:10px;overflow:hidden;background:#000}
.b-video{display:block;width:100%;max-height:60vh;aspect-ratio:16/9;background:#000}
.b-panel{margin-top:10px;padding:12px 14px;border:1px solid var(--line);border-left:4px solid var(--brand);border-radius:10px;background:var(--soft)}
.b-panel .b-head{font-size:1.1rem}
@media (max-width:640px){.b-player{top:68px;padding:8px 10px}.b-links{gap:10px;font-size:.82rem}.b-chapters{max-height:140px}.card{padding:16px}}
@media (max-width:640px){.b-hero{padding:28px 0 4px}}
/* ---- sticky top block (date line + media + current-story panel) ---- */
.b-stick{position:sticky;top:68px;z-index:40;background:rgba(255,255,255,.97);backdrop-filter:saturate(180%) blur(8px);border-bottom:1px solid var(--line);padding:8px 0 10px;box-shadow:0 6px 16px rgba(15,23,42,.05)}
.b-stick .b-topline{margin-bottom:6px}
.b-stick{max-height:calc(100vh - 80px);overflow-y:auto;overscroll-behavior:contain}
.b-stick .b-player{position:static;margin:0;padding:8px 10px;box-shadow:none}
.b-stick .b-links a.b-pi,.b-stick .b-links span.b-pi{font-weight:700}
.b-pi{font-weight:700}
.b-pi.off{color:var(--muted);opacity:.45}
.b-main .b-tag{margin:10px 0 0}
.b-has-video .b-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:12px;align-items:start}
.b-has-video .b-video-wrap{margin:0}
.b-has-video .b-video{max-height:34vh}
.b-has-video .b-panel{margin:0;max-height:34vh;overflow:auto}
.b-panel .b-sum{display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;font-size:.93rem}
.b-panel .b-why{font-size:.88rem;padding:6px 10px}
.b-panel .b-chips{margin-top:8px}
.b-panel-empty{color:var(--muted);font-size:.92rem}
.b-stick .b-mbar{margin-top:8px}
.b-stick .b-chapters{max-height:26vh}
@media (max-width:899px){
  .b-has-video .b-grid{grid-template-columns:1fr;gap:6px}
}
@media (max-width:640px){
  .b-stick{max-height:40vh;overflow-y:auto;padding:6px 0 8px}
  .b-stick .b-player{padding:6px 8px}
  .b-has-video .b-video{max-height:19vh;width:auto;margin:0 auto}
  .b-mlabel{display:none}
  .b-panel-empty{font-size:.8rem}
  .b-has-video .b-video-wrap{display:flex;justify-content:center}
  .b-panel{padding:6px 10px}
  .b-panel .b-sum,.b-panel .b-why,.b-panel .b-chips,.b-panel .b-off,.b-panel .b-note{display:none}
  .b-panel .b-head{font-size:.95rem;margin:2px 0 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .b-stick .b-mbar{margin-top:4px;gap:8px}
  .b-stick.mini .b-has-video .b-video{max-height:14vh}
  .b-stick.mini .b-topline .b-links a:not(.b-pi){display:none}
  .b-stick .b-chapters{max-height:18vh}
  .b-stick .b-topline{flex-wrap:nowrap;margin-bottom:4px}
  .b-stick .b-h1{font-size:.95rem;white-space:nowrap}
  .b-stick .b-links{gap:8px;font-size:.8rem;white-space:nowrap}
  .b-stick.mini .b-h1 .eyebrow,.b-stick.mini .b-mlabel,.b-stick.mini .b-panel .b-meta{display:none}
  .b-stick.mini .b-panel .b-head{font-size:.9rem}
}
@media (min-width:641px){
  .b-stick.mini .b-has-video .b-video,.b-stick.mini .b-has-video .b-panel{max-height:24vh}
  .b-stick.mini .b-panel .b-sum{-webkit-line-clamp:3}
}

@media (min-width:900px){.b-player{top:84px}}
'''

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)

def public_json(ed):
    keep = ["schemaVersion", "date", "generatedAt", "stories", "audio", "video"]
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
        write(os.path.join(out, ed["date"], "index.html"), page(f"Briefed: {long_date(ed['date'])}", desc[:300], url, edition_body(ed, i == 0, editions[i + 1]["date"] if i + 1 < len(editions) else None, editions[i - 1]["date"] if i > 0 else None), jsonld_ed(ed, url)))
        write(os.path.join(out, f"{ed['date']}.json"), json.dumps(public_json(ed), indent=1))
    if editions:
        latest = editions[0]
        write(os.path.join(out, "index.html"), page("Briefed: today's edition | LJI Industries", f"Briefed for {long_date(latest['date'])}: the facts on the day's stories, with links to the original reporting and official sources.", f"/briefed/{latest['date']}/", edition_body(latest, True, editions[1]["date"] if len(editions) > 1 else None, None), jsonld_ed(latest, "/briefed/")))
        write(os.path.join(out, "latest.json"), json.dumps(public_json(latest), indent=1))
    else:
        write(os.path.join(out, "index.html"), page("Briefed: daily edition | LJI Industries", "Briefed's first US-focused daily edition arrives Sunday, October 25, 2026.", "/briefed/", EMPTY))
        write(os.path.join(out, "latest.json"), json.dumps({"schemaVersion": 1, "date": None, "message": "First edition arrives soon."}))
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
