#!/usr/bin/env python3
"""Convert Briefed_Bot's morning outputs for one day into editions/YYYY-MM-DD.json (schema v1).

Inputs (Briefed_Bot writes these under $BRIEFED_AUDIO_DIR/<day>/, default /workspace/briefed-audio):
  v2/stories.json                         cards: headline, location, label, labelChip, sources, usLink, optional summary/region
  web-summary.md                          optional fuller summaries plus Quick facts / Not yet confirmed / What happens next
  full_segments_<MMDD>.json               spoken script; NN_body text is the summary fallback
  Briefed-<day>-full-twohost-chapters.json chapter times per storyId (card -> storyId)
  Briefed-<day>-full-twohost.mp3          audio (uploaded separately by publish_day.sh)
Usage: make_edition.py DAY OUT.json [--audio-url URL]
"""
import json, os, re, sys
from urllib.parse import urlparse

OUTLETS = {"apnews.com": "Associated Press", "reuters.com": "Reuters", "bbc.com": "BBC", "bbc.co.uk": "BBC", "nbcnews.com": "NBC News",
  "abcnews.go.com": "ABC News", "abcnews.com": "ABC News", "cbsnews.com": "CBS News", "npr.org": "NPR", "nytimes.com": "New York Times", "washingtonpost.com": "Washington Post",
  "wsj.com": "Wall Street Journal", "foxnews.com": "Fox News", "cnn.com": "CNN", "politico.com": "Politico", "thehill.com": "The Hill",
  "axios.com": "Axios", "theguardian.com": "The Guardian", "bloomberg.com": "Bloomberg", "cnbc.com": "CNBC", "usatoday.com": "USA Today",
  "newsmax.com": "Newsmax", "washingtontimes.com": "Washington Times", "nypost.com": "New York Post", "dw.com": "DW", "france24.com": "France 24",
  "aljazeera.com": "Al Jazeera", "abqjournal.com": "Albuquerque Journal", "politifact.com": "PolitiFact", "scotusblog.com": "SCOTUSblog", "courthousenews.com": "Courthouse News", "stripes.com": "Stars and Stripes", "veterannews.com": "VeteranNews", "pool.pp.tools": "White House pool report", "ballotpedia.org": "Ballotpedia", "thenextweb.com": "The Next Web", "abc7ny.com": "ABC7 New York", "ny1.com": "NY1", "tracreports.org": "TRAC"}
NAMES = {"AP": "Associated Press", "NBC": "NBC News", "ABC": "ABC News", "CBS": "CBS News", "DOJ": "Justice Department"}
OFFICIAL = re.compile(r"(\.gov|\.mil|whitehouse\.gov|kremlin\.ru|\.gov\.[a-z]{2}|europa\.eu|un\.org|who\.int)$")
LABELS = {"sourced": "sourced", "cleared": "cleared", "as_reported": "reported-only", "reported": "reported-only", "reported_only": "reported-only", "claimed": "claimed"}

def host(u):
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h

def outlet_name(h):
    for d, n in OUTLETS.items():
        if h == d or h.endswith("." + d): return n
    return h

def clean_name(s):
    s = re.sub(r"\s+(press release|release).*$", "", s, flags=re.I).strip()
    return NAMES.get(s, s)

def summary_from_script(text):
    text = re.split(r"\s*Why it matters to the U\.?S\.?:", text)[0].strip()
    text = re.sub(r"^(And|But|So|Also|Meanwhile),?\s+", "", text)
    text = re.sub(r"^On the [\w\s-]{1,30} beat:\s*", "", text)
    text = text[:1].upper() + text[1:]
    sents = re.split(r"(?<=[.!?])\s+", text)
    out = " ".join(sents[:2]).strip()
    return out[:400]


def parse_list_items(block):
    items = []
    for raw in (block or "").splitlines():
        m = re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)$", raw)
        if m:
            items.append(m.group(1).strip())
        elif items and raw.strip() and raw.startswith(" "):
            items[-1] = items[-1] + " " + raw.strip()
    if not items:
        para = re.sub(r"\s+", " ", (block or "").strip())
        if para:
            items = [para]
    return items

def parse_web_summary(md):
    """Parse morning web-summary.md into per-card fuller text and brief lists.

    Morning summaries use numbered '## N. Headline [Label]' sections and
    '**Quick facts**' / '**Not yet confirmed**' / '**What happens next**' headings.
    Night summaries use '### ' headings and are handled in make_night_edition.py.
    """
    out = {}
    if not md:
        return out
    text = md.replace("\r\n", "\n")
    parts = re.split(r"\n(?=##\s+\d+\.\s+)", "\n" + text)
    for part in parts:
        part = part.lstrip("\n")
        m = re.match(r"##\s+(\d+)\.\s+(.+?)(?:\s+\[[^\]]+\])?\s*\n", part)
        if not m:
            continue
        rec = {"headline": m.group(2).strip()}
        body = part[m.end():]
        chunks = re.split(r"\n(?=\*\*(?:Quick facts|Not yet confirmed|What happens next|Sources)\*\*\s*$)", body, flags=re.M)
        rec["summary"] = chunks[0].strip() if chunks else ""
        for chunk in chunks[1:]:
            title, _, sbody = chunk.strip().partition("\n")
            key = title.strip().strip("*").strip()
            items = parse_list_items(sbody)
            if key == "Quick facts":
                rec["quickFacts"] = items
            elif key == "Not yet confirmed":
                rec["notYetConfirmed"] = items
            elif key == "What happens next":
                rec["whatHappensNext"] = items
            elif key == "Sources":
                urls = []
                for item in items:
                    um = re.search(r"https?://\S+", item)
                    if um:
                        urls.append(um.group(0).rstrip(").,;"))
                rec["sources"] = urls
        out[int(m.group(1))] = rec
    return out

def main():
    day, out = sys.argv[1], sys.argv[2]
    audio_url = sys.argv[sys.argv.index("--audio-url") + 1] if "--audio-url" in sys.argv else None
    base = os.path.join(os.environ.get("BRIEFED_AUDIO_DIR", "/workspace/briefed-audio"), day)
    st = json.load(open(os.path.join(base, "v2", "stories.json")))
    ch = json.load(open(os.path.join(base, f"Briefed-{day}-full-twohost-chapters.json")))
    segp = os.path.join(base, f"full_segments_{day[5:7]}{day[8:10]}.json")
    segs = json.load(open(segp))["segments"] if os.path.exists(segp) else []
    by_card = {c["card"]: c for c in ch["chapters"] if c.get("card")}
    body = {s.get("storyId"): s["text"] for s in segs if s["id"].endswith("_body")}
    web_path = os.path.join(base, "web-summary.md")
    webs = parse_web_summary(open(web_path, encoding="utf-8").read()) if os.path.exists(web_path) else {}
    stories, warn = [], []
    for s in sorted(st["stories"], key=lambda x: x["card"]):
        c = by_card.get(s["card"])
        sid = c["storyId"] if c else f"story-{s['card']}"
        if not c: warn.append(f"card {s['card']}: no chapter (no Listen button)")
        loc = s.get("location", "")
        region = s.get("region") or ("foreign" if loc.lower().startswith("world") else "us")
        outlets, official = [], []
        for src in s.get("sources", []):
            if re.match(r"https?://", src):
                h = host(src)
                (official.append(src) if OFFICIAL.search(h) else outlets.append({"name": outlet_name(h), "url": src}))
            else:
                outlets.append({"name": clean_name(src)})
        for u in s.get("officialSources", []): official.append(u)
        web = webs.get(s["card"]) or {}
        for src in web.get("sources") or []:
            if re.match(r"https?://", src):
                h = host(src)
                (official.append(src) if OFFICIAL.search(h) else outlets.append({"name": outlet_name(h), "url": src}))
        seen = set(); outlets = [o for o in outlets if not (o.get("url") or o["name"]) in seen and not seen.add(o.get("url") or o["name"])]
        seen_off = set(); official = [u for u in official if not (u in seen_off or seen_off.add(u))]
        story = {"id": sid, "region": region, "location": loc.split(": ", 1)[-1] if ": " in loc else loc,
                 "headline": s["headline"], "status": LABELS.get(s.get("label", ""), "reported-only"),
                 "outlets": outlets, "officialSources": official}
        summ = web.get("summary") or s.get("summary") or (summary_from_script(body[sid]) if body.get(sid) else None)
        if summ: story["summary"] = summ
        briefing = {k: web[k] for k in ("quickFacts", "notYetConfirmed", "whatHappensNext") if web.get(k)}
        if briefing:
            story["briefing"] = briefing
        elif webs and s["card"] not in webs:
            warn.append(f"card {s['card']}: no matching section in web-summary.md")
        # accept both {quote,url,role} and v2 {said,source,where} shapes
        fhn = [dict(q, quote=q.get("quote") or q.get("said"), url=q.get("url") or q.get("source"), role=q.get("role") or q.get("where"))
               for q in s.get("firstHand") or [] if isinstance(q, dict)]
        fh = [{k: q[k] for k in ("who", "handle", "role", "date", "url", "quote") if q.get(k)} for q in fhn
              if q.get("quote") and re.match(r"https?://[^\s<>\"']+$", str(q.get("url") or ""))]
        if fh: story["firstHand"] = fh
        why = s.get("whyItMattersToUS") or s.get("usLink")
        if why: story["whyItMattersToUS"] = why
        if region == "foreign" and not why: warn.append(f"{sid}: foreign story without why-it-matters line")
        if "not confirmed" in s.get("labelChip", "").lower():
            story["statusNote"] = s["labelChip"].split("·")[-1].strip().rstrip(".") + "."
        stories.append(story)
    if stories and stories[0]["region"] != "us": warn.append("lead story is not domestic")
    titles = {s["id"]: next((x.get("short") or x["headline"] for x in st["stories"] if by_card.get(x["card"], {}).get("storyId") == s["id"]), s["headline"]) for s in stories}
    chapters = [{"storyId": c.get("storyId"), "title": "Intro" if c["kind"] == "intro" else "Close" if c["kind"] == "close" else titles.get(c["storyId"], c["storyId"]),
                 "start": round(c["startSeconds"], 3), "end": round(c["endSeconds"], 3)} for c in ch["chapters"]]
    ed = {"schemaVersion": 1, "date": day, "generatedAt": ch.get("edition", {}).get("generatedAt", day), "stories": stories}
    if audio_url:
        ed["audio"] = {"url": audio_url, "durationSeconds": ch.get("durationSeconds"), "aiVoices": True, "chapters": chapters}
    # optional video: v2/Briefed-<day>-web.mp4 + v2/Briefed-<day>-poster.jpg + v2/video-chapters.json
    vbase = sys.argv[sys.argv.index("--release-base") + 1].rstrip("/") if "--release-base" in sys.argv else None
    vmp4 = os.path.join(base, "v2", f"Briefed-{day}-web.mp4")
    vch = os.path.join(base, "v2", "video-chapters.json")
    if vbase and os.path.exists(vmp4) and os.path.exists(vch):
        vc = json.load(open(vch))["chapters"]
        # no-intro editions: a short cover still (kind "intro", < 4 s) is folded into the first story so the list starts with the lead
        if len(vc) > 1 and vc[0].get("kind") == "intro" and vc[0]["end"] - vc[0]["start"] < 4:
            vc = [dict(vc[1], start=vc[0]["start"])] + vc[2:]
        ids = {s["id"] for s in stories}
        for c in vc:
            if c.get("kind") == "story" and c["id"] not in ids: warn.append(f"video chapter {c['id']} matches no story")
        vchap = [{"storyId": c["id"] if c.get("kind") == "story" else None,
                  "title": "Intro" if c.get("kind") == "intro" else "Close" if c.get("kind") == "close" else titles.get(c["id"], c["id"]),
                  "start": round(c["start"], 3), "end": round(c["end"], 3)} for c in vc]
        video = {"url": f"{vbase}/Briefed-{day}-web.mp4", "durationSeconds": round(vc[-1]["end"], 3), "aiVoices": True, "chapters": vchap}
        if os.path.exists(os.path.join(base, "v2", f"Briefed-{day}-poster.jpg")):
            video["poster"] = f"{vbase}/Briefed-{day}-poster.jpg"
        ed["video"] = video
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(ed, open(out, "w"), indent=1, ensure_ascii=False)
    for w in warn: print("WARN:", w, file=sys.stderr)
    nbrief = sum(1 for s in stories if s.get("briefing"))
    print(f"wrote {out}: {len(stories)} stories ({nbrief} with briefing lists), {len(chapters)} chapters, audio={'yes' if audio_url else 'no'}, video={'yes' if ed.get('video') else 'no'}")

if __name__ == "__main__":
    main()
