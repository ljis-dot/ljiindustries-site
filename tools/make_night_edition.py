#!/usr/bin/env python3
"""Convert a Briefed night-update folder into editions/YYYY-MM-DD-night.json.

Inputs under $BRIEFED_AUDIO_DIR/<day>-night/ (default /workspace/briefed-audio):
  Briefed-<day>-night-full-twohost.mp3
  Briefed-<day>-night-full-twohost-chapters.json
  vN/stories.json, vN/video-chapters.json, vN/*-web.mp4, vN poster/thumbnail
  web-summary-night.md (or web-summary.md)
  vN/PHOTO-SOURCES.md (or PHOTO-SOURCES.md)

Usage: make_night_edition.py DAY OUT.json [--audio-url URL] [--release-base /briefed/media/DAY-night]
Does not read or write the morning edition (editions/DAY.json or briefed/media/DAY/).
"""
import json, os, re, sys
from urllib.parse import urlparse

OUTLETS = {"apnews.com": "Associated Press", "reuters.com": "Reuters", "bbc.com": "BBC", "bbc.co.uk": "BBC", "nbcnews.com": "NBC News",
  "abcnews.go.com": "ABC News", "cbsnews.com": "CBS News", "npr.org": "NPR", "nytimes.com": "New York Times", "washingtonpost.com": "Washington Post",
  "wsj.com": "Wall Street Journal", "foxnews.com": "Fox News", "cnn.com": "CNN", "politico.com": "Politico", "thehill.com": "The Hill",
  "axios.com": "Axios", "theguardian.com": "The Guardian", "bloomberg.com": "Bloomberg", "cnbc.com": "CNBC", "usatoday.com": "USA Today",
  "newsmax.com": "Newsmax", "washingtontimes.com": "Washington Times", "nypost.com": "New York Post", "dw.com": "DW", "france24.com": "France 24",
  "aljazeera.com": "Al Jazeera", "abqjournal.com": "Albuquerque Journal", "politifact.com": "PolitiFact"}
NAMES = {"AP": "Associated Press", "NBC": "NBC News", "ABC": "ABC News", "CBS": "CBS News", "DOJ": "Justice Department"}
OFFICIAL = re.compile(r"(\.gov|\.mil|whitehouse\.gov|kremlin\.ru|\.gov\.[a-z]{2}|europa\.eu|un\.org|who\.int)$")
LABELS = {"sourced": "sourced", "cleared": "cleared", "as_reported": "reported-only", "reported": "reported-only", "reported_only": "reported-only"}


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

def find_version_dir(base):
    versions = []
    for n in os.listdir(base):
        p = os.path.join(base, n)
        if re.fullmatch(r"v\d+", n) and os.path.isdir(p) and os.path.exists(os.path.join(p, "stories.json")):
            versions.append((int(n[1:]), p))
    if not versions:
        raise SystemExit(f"no vN/stories.json under {base}")
    versions.sort()
    return versions[-1][1]

def first_existing(*paths):
    for p in paths:
        if p and os.path.exists(p) and (not os.path.isfile(p) or os.path.getsize(p) > 0):
            return p
    return None

def parse_list_items(block):
    items = []
    for raw in (block or "").splitlines():
        m = re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)$", raw)
        if m:
            items.append(m.group(1).strip())
        elif items and raw.strip() and raw.startswith(" "):
            items[-1] = items[-1] + " " + raw.strip()
    return items

def parse_briefing(md):
    """Pull Quick facts / Not yet confirmed / related / What happens next / Sources from the night summary."""
    if not md: return {}
    text = md.replace("\r\n", "\n")
    parts = re.split(r"\n(?=### )", "\n" + text)
    sections = {}
    for part in parts:
        part = part.lstrip("\n")
        if not part.startswith("### "):
            continue
        title, _, body = part.partition("\n")
        key = title[4:].strip()
        sections[key] = body.strip()
    def grab(*names):
        for n in names:
            if n in sections: return parse_list_items(sections[n])
            for k in sections:
                if k.lower() == n.lower(): return parse_list_items(sections[k])
        # prefix match (e.g. "Related same-day development (not in the clip)")
        for n in names:
            for k in sections:
                if k.lower().startswith(n.lower()): return parse_list_items(sections[k])
        return []
    sources = []
    for item in grab("Sources"):
        m = re.search(r"https?://\S+", item)
        if m:
            u = m.group(0).rstrip(").,;")
            sources.append({"name": outlet_name(host(u)), "url": u})
    out = {}
    qf = grab("Quick facts")
    nyc = grab("Not yet confirmed")
    rel = grab("Related same-day development", "Related")
    nxt = grab("What happens next")
    if qf: out["quickFacts"] = qf
    if nyc: out["notYetConfirmed"] = nyc
    if rel: out["related"] = rel
    if nxt: out["whatHappensNext"] = nxt
    if sources: out["sources"] = sources
    return out

def parse_credits(md):
    credits = []
    if not md: return credits
    chunks = re.split(r"\n## ", "\n" + md.replace("\r\n", "\n"))
    for chunk in chunks[1:]:
        title, _, body = chunk.partition("\n")
        title = title.strip()
        if "used in the thumbnail" not in title.lower():
            continue
        subject = re.sub(r"\s*\(used in the thumbnail\)\s*", "", title, flags=re.I).strip()
        fields = {}
        for line in body.splitlines():
            m = re.match(r"-\s+\*\*(.+?)\*\*\s*(.*)$", line.strip())
            if m and m.group(2).strip():
                fields[m.group(1).strip().rstrip(":").strip().lower()] = m.group(2).strip()
        url = fields.get("wikimedia commons page", "")
        author = fields.get("author", "")
        date = fields.get("date", "")
        licence = fields.get("licence") or fields.get("license") or ""
        short_lic = licence
        m = re.match(r"(Public domain\s*\([^)]+\))", licence, re.I)
        if m:
            short_lic = m.group(1)
        credit = ", ".join(x for x in (author, date) if x)
        rec = {"subject": subject, "credit": credit, "license": short_lic}
        if url:
            rec["url"] = url
            rec["source"] = "Wikimedia Commons"
        if author: rec["author"] = author
        credits.append(rec)
    return credits

def outlets_from(sources, official_extra=None):
    outlets, official = [], []
    for src in sources or []:
        if re.match(r"https?://", src):
            h = host(src)
            (official.append(src) if OFFICIAL.search(h) else outlets.append({"name": outlet_name(h), "url": src}))
        else:
            outlets.append({"name": clean_name(src)})
    for u in official_extra or []:
        official.append(u)
    seen = set()
    outlets = [o for o in outlets if not (o.get("url") or o["name"]) in seen and not seen.add(o.get("url") or o["name"])]
    return outlets, official

def main():
    day, out = sys.argv[1], sys.argv[2]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise SystemExit(f"bad date: {day}")
    audio_url = sys.argv[sys.argv.index("--audio-url") + 1] if "--audio-url" in sys.argv else None
    vbase = sys.argv[sys.argv.index("--release-base") + 1].rstrip("/") if "--release-base" in sys.argv else f"/briefed/media/{day}-night"
    slug = f"{day}-night"
    base = os.path.join(os.environ.get("BRIEFED_AUDIO_DIR", "/workspace/briefed-audio"), slug)
    if not os.path.isdir(base):
        raise SystemExit(f"missing night folder: {base}")
    vdir = find_version_dir(base)
    st = json.load(open(os.path.join(vdir, "stories.json")))
    ch_path = os.path.join(base, f"Briefed-{slug}-full-twohost-chapters.json")
    if not os.path.exists(ch_path):
        raise SystemExit(f"missing chapters: {ch_path}")
    ch = json.load(open(ch_path))
    summ_path = first_existing(os.path.join(base, "web-summary-night.md"), os.path.join(base, "web-summary.md"))
    cred_path = first_existing(os.path.join(vdir, "PHOTO-SOURCES.md"), os.path.join(base, "PHOTO-SOURCES.md"))
    briefing = parse_briefing(open(summ_path, encoding="utf-8").read() if summ_path else "")
    credits = parse_credits(open(cred_path, encoding="utf-8").read() if cred_path else "")

    by_card = {c["card"]: c for c in ch.get("chapters", []) if c.get("card")}
    stories, warn = [], []
    for s in sorted(st["stories"], key=lambda x: x["card"]):
        c = by_card.get(s["card"])
        sid = s.get("storyId") or (c["storyId"] if c else f"story-{s['card']}")
        if not c: warn.append(f"card {s['card']}: no chapter (no Listen button)")
        loc = s.get("location", "")
        region = s.get("region") or ("foreign" if loc.lower().startswith("world") else "us")
        outlets, official = outlets_from(s.get("sources"), s.get("officialSources"))
        story = {"id": sid, "region": region, "location": loc.split(": ", 1)[-1] if ": " in loc else loc,
                 "headline": s["headline"], "status": LABELS.get(s.get("label", ""), "reported-only"),
                 "outlets": outlets, "officialSources": official}
        if s.get("summary"): story["summary"] = s["summary"]
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

    titles = {s["id"]: next((x.get("short") or x["headline"] for x in st["stories"]
                             if (x.get("storyId") or (by_card.get(x["card"]) or {}).get("storyId")) == s["id"]), s["headline"]) for s in stories}
    chapters = [{"storyId": c.get("storyId"), "title": "Intro" if c["kind"] == "intro" else "Close" if c["kind"] == "close" else titles.get(c["storyId"], c["storyId"]),
                 "start": round(c["startSeconds"], 3), "end": round(c["endSeconds"], 3)} for c in ch["chapters"]]
    ed = {"schemaVersion": 1, "kind": "night", "date": day, "slug": slug,
          "generatedAt": ch.get("edition", {}).get("generatedAt", day), "stories": stories}
    if briefing: ed["briefing"] = briefing
    if credits: ed["photoCredits"] = credits
    if audio_url:
        ed["audio"] = {"url": audio_url, "durationSeconds": ch.get("durationSeconds"), "aiVoices": True, "chapters": chapters}

    vmp4 = first_existing(
        os.path.join(vdir, f"Briefed-{slug}-web.mp4"),
        *([os.path.join(vdir, n) for n in sorted(os.listdir(vdir)) if n.endswith("-web.mp4")] if os.path.isdir(vdir) else []),
    )
    vch_path = first_existing(os.path.join(vdir, "video-chapters.json"))
    poster = first_existing(
        os.path.join(vdir, f"Briefed-{slug}-poster.jpg"),
        os.path.join(vdir, "poster.jpg"),
        os.path.join(vdir, "thumbnail.jpg"),
        os.path.join(vdir, f"Briefed-{slug}-thumbnail.jpg"),
    )
    if vbase and vmp4 and vch_path:
        vc = json.load(open(vch_path))["chapters"]
        if len(vc) > 1 and vc[0].get("kind") == "intro" and vc[0]["end"] - vc[0]["start"] < 4:
            vc = [dict(vc[1], start=vc[0]["start"])] + vc[2:]
        ids = {s["id"] for s in stories}
        for c in vc:
            cid = c.get("id") or c.get("storyId")
            if c.get("kind") == "story" and cid not in ids: warn.append(f"video chapter {cid} matches no story")
        vchap = [{"storyId": (c.get("id") if c.get("kind") == "story" else None),
                  "title": "Intro" if c.get("kind") == "intro" else "Close" if c.get("kind") == "close" else titles.get(c.get("id"), c.get("id")),
                  "start": round(c["start"], 3), "end": round(c["end"], 3)} for c in vc]
        video = {"url": f"{vbase}/Briefed-{slug}-web.mp4", "durationSeconds": round(vc[-1]["end"], 3), "aiVoices": True, "chapters": vchap}
        if poster:
            video["poster"] = f"{vbase}/Briefed-{slug}-poster.jpg"
        ed["video"] = video
    elif vbase and vmp4:
        warn.append("video present but no video-chapters.json")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(ed, open(out, "w"), indent=1, ensure_ascii=False)
    open(out, "a").write("\n")
    for w in warn: print("WARN:", w, file=sys.stderr)
    print(f"wrote {out}: {len(stories)} stories, {len(chapters)} chapters, audio={'yes' if audio_url else 'no'}, video={'yes' if ed.get('video') else 'no'}")

if __name__ == "__main__":
    main()
