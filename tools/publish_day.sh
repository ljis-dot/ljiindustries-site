#!/usr/bin/env bash
# Publish one Briefed day to ljiindustries.com/briefed.
# Usage: tools/publish_day.sh YYYY-MM-DD [--night] [--dry-run]
# Needs: $LJI_SITE_GITHUB_TOKEN (fine-grained, Contents R/W on ljiindustries-site). Never printed.
# Dry run: converts + builds into a temp copy of the repo; no release, commit, push or live check.
# --night publishes a night addendum at /briefed/YYYY-MM-DD-night/ from $BRIEFED_AUDIO_DIR/YYYY-MM-DD-night/.
# It does not modify editions/YYYY-MM-DD.json or briefed/media/YYYY-MM-DD/.
set -euo pipefail
DAY=""; NIGHT=0; DRY=0
for arg in "$@"; do
  case "$arg" in
    --night) NIGHT=1 ;;
    --dry-run) DRY=1 ;;
    -*) echo "usage: publish_day.sh YYYY-MM-DD [--night] [--dry-run]" >&2; exit 2 ;;
    *)
      if [ -z "$DAY" ]; then DAY="$arg"
      else echo "usage: publish_day.sh YYYY-MM-DD [--night] [--dry-run]" >&2; exit 2
      fi
      ;;
  esac
done
[ -n "$DAY" ] || { echo "usage: publish_day.sh YYYY-MM-DD [--night] [--dry-run]" >&2; exit 2; }
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad date: $DAY" >&2; exit 2; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OWNER_REPO="ljis-dot/ljiindustries-site"
SLUG="$DAY"
SRC="${BRIEFED_AUDIO_DIR:-/workspace/briefed-audio}/$DAY"
if [ $NIGHT = 1 ]; then
  SLUG="$DAY-night"
  SRC="${BRIEFED_AUDIO_DIR:-/workspace/briefed-audio}/$SLUG"
fi
MP3="$SRC/Briefed-$SLUG-full-twohost.mp3"; CH="$SRC/Briefed-$SLUG-full-twohost-chapters.json"
TAG="briefed-$SLUG"; API="https://api.github.com/repos/$OWNER_REPO"
if [ $NIGHT = 1 ]; then
  [ -s "$MP3" ] || { echo "missing input: $MP3" >&2; exit 3; }
  [ -s "$CH" ] || { echo "missing input: $CH" >&2; exit 3; }
  found_stories=0
  for d in "$SRC"/v[0-9]*; do
    [ -s "$d/stories.json" ] && found_stories=1 && break
  done
  [ $found_stories = 1 ] || { echo "missing input: $SRC/vN/stories.json" >&2; exit 3; }
else
  for f in "$MP3" "$CH" "$SRC/v2/stories.json"; do [ -s "$f" ] || { echo "missing input: $f" >&2; exit 3; }; done
fi
log(){ echo "[publish $SLUG] $*"; }
gh_api(){ curl -sS -H "Authorization: Bearer $LJI_SITE_GITHUB_TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }
if [ $DRY = 0 ] && [[ "$DAY" < "2026-10-24" ]]; then echo "refusing: $DAY is before launch (2026-10-24)" >&2; exit 2; fi
AUDIO_URL="https://github.com/$OWNER_REPO/releases/download/$TAG/Briefed-$SLUG-full-twohost.mp3"

if [ $DRY = 1 ]; then
  WORK="$(mktemp -d)"; (cd "$REPO_DIR" && git archive HEAD) | tar -x -C "$WORK"
  cp "$REPO_DIR/tools/"*.py "$WORK/tools/"   # test uncommitted tool changes too
  cp "$REPO_DIR/tools/publish_day.sh" "$WORK/tools/publish_day.sh"
  log "DRY RUN in $WORK (would create/reuse release $TAG and upload MP3 + chapters; video/poster go to briefed/media/$SLUG)"
else
  : "${LJI_SITE_GITHUB_TOKEN:?LJI_SITE_GITHUB_TOKEN not set}"
  WORK="$REPO_DIR"
  AUTH=(-c credential.helper= -c http.extraheader="Authorization: Basic $(printf 'x-access-token:%s' "$LJI_SITE_GITHUB_TOKEN" | base64 -w0)")
  cd "$WORK"; git checkout -q main; git "${AUTH[@]}" pull -q --ff-only origin main
  # --- release (idempotent) ---
  REL=$(gh_api "$API/releases/tags/$TAG")
  RID=$(printf '%s' "$REL" | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))")
  if [ -z "$RID" ]; then
    BODY="Briefed audio edition for $DAY (AI-voiced). MP3 + chapters."
    NAME="Briefed $DAY"
    if [ $NIGHT = 1 ]; then
      BODY="Briefed night update for $DAY (AI-voiced). MP3 + chapters."
      NAME="Briefed $DAY night update"
    fi
    RID=$(gh_api -X POST "$API/releases" -d "{\"tag_name\":\"$TAG\",\"target_commitish\":\"main\",\"name\":\"$NAME\",\"body\":\"$BODY\",\"prerelease\":true}" \
      | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('id') or '')")
    [ -n "$RID" ] || { echo "release create failed" >&2; exit 4; }; log "created release $TAG ($RID)"
  else log "release $TAG exists ($RID)"; fi
  ASSETS=("$MP3" "$CH")   # video + poster are served from the site repo (briefed/media/$SLUG), not Releases
  for f in "${ASSETS[@]}"; do
    n=$(basename "$f")
    old=$(gh_api "$API/releases/$RID/assets?per_page=100" | python3 -c "import json,sys;print(next((str(a['id']) for a in json.load(sys.stdin) if a['name']=='$n'),''))")
    [ -n "$old" ] && gh_api -X DELETE "$API/releases/assets/$old" >/dev/null && log "replaced old asset $n"
    case "$n" in *.mp3) ct=audio/mpeg;; *.mp4) ct=video/mp4;; *.jpg) ct=image/jpeg;; *) ct=application/json;; esac
    code=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $LJI_SITE_GITHUB_TOKEN" -H "Content-Type: $ct" --data-binary @"$f" \
      "https://uploads.github.com/repos/$OWNER_REPO/releases/$RID/assets?name=$n")
    [ "$code" = 201 ] || { echo "upload $n failed: HTTP $code" >&2; exit 5; }; log "uploaded $n"
  done
  curl -sfIL -o /dev/null "$AUDIO_URL" || { echo "audio URL not reachable: $AUDIO_URL" >&2; exit 6; }
fi

# --- video + poster into the repo: briefed/media/$SLUG/ ---
MEDIA="$WORK/briefed/media/$SLUG"; VSRC=""
if [ $NIGHT = 1 ]; then
  # Prefer the highest vN folder that has a web video (v4 over v3 over v2).
  for d in $(ls -d "$SRC"/v[0-9]* 2>/dev/null | sort -V); do
    [ -d "$d" ] || continue
    for f in "$d/Briefed-$SLUG-web.mp4" "$d"/Briefed-$SLUG-v*-web.mp4; do
      [ -s "$f" ] && VSRC="$f"
    done
  done
  if [ -n "$VSRC" ]; then
    mkdir -p "$MEDIA"
    cp "$VSRC" "$MEDIA/Briefed-$SLUG-web.mp4"
    PSRC=""
    VDIR="$(dirname "$VSRC")"
    for f in "$VDIR/Briefed-$SLUG-poster.jpg" "$VDIR/poster.jpg" "$VDIR/thumbnail.jpg"; do
      [ -s "$f" ] && { PSRC="$f"; break; }
    done
    [ -n "$PSRC" ] && cp "$PSRC" "$MEDIA/Briefed-$SLUG-poster.jpg"
    log "video copied to briefed/media/$SLUG/"
  fi
  BRIEFED_AUDIO_DIR="$(cd "$SRC/.." && pwd)" python3 "$WORK/tools/make_night_edition.py" "$DAY" "$WORK/editions/$SLUG.json" --audio-url "$AUDIO_URL" --release-base "/briefed/media/$SLUG"
else
  for f in "$SRC/v2/Briefed-$DAY-web.mp4" "$SRC/v2/Briefed-$DAY-v2-web.mp4"; do [ -s "$f" ] && { VSRC="$f"; break; }; done
  # make_edition expects v2/Briefed-$DAY-web.mp4; give it a temp source folder of symlinks
  ESRC="$(mktemp -d)"; mkdir -p "$ESRC/$DAY/v2"
  for f in "$SRC"/* "$SRC"/v2/*; do [ -f "$f" ] && ln -s "$f" "$ESRC/$DAY/${f#$SRC/}"; done
  if [ -n "$VSRC" ]; then
    mkdir -p "$MEDIA"; cp "$VSRC" "$MEDIA/Briefed-$DAY-web.mp4"
    ln -sf "$VSRC" "$ESRC/$DAY/v2/Briefed-$DAY-web.mp4"
    [ -s "$SRC/v2/Briefed-$DAY-poster.jpg" ] && cp "$SRC/v2/Briefed-$DAY-poster.jpg" "$MEDIA/"
    log "video copied to briefed/media/$DAY/"
  fi
  BRIEFED_AUDIO_DIR="$ESRC" python3 "$WORK/tools/make_edition.py" "$DAY" "$WORK/editions/$DAY.json" --audio-url "$AUDIO_URL" --release-base "/briefed/media/$DAY"
fi
(cd "$WORK" && python3 tools/build_briefed.py)

if [ $DRY = 1 ]; then
  if [[ "$DAY" < "2026-10-24" ]]; then
    log "note: $DAY is before launch (2026-10-24), so the real build skips it; rendering preview copy too"
    (cd "$WORK" && python3 tools/build_briefed.py --preview "editions/$SLUG.json" >/dev/null)
  fi
  log "DRY RUN done. Output: $WORK/briefed/ ; would commit editions/$SLUG.json + briefed/ + sitemap.xml and push to main"
  echo "$WORK"; exit 0
fi

# Night publishes must not alter the morning edition source or media.
if [ $NIGHT = 1 ]; then
  if ! git diff --quiet -- "editions/$DAY.json" "briefed/media/$DAY"; then
    echo "refusing: morning edition files changed; restoring and aborting" >&2
    git checkout -- "editions/$DAY.json" "briefed/media/$DAY"
    exit 8
  fi
fi

# --- commit + push ---
if [ $NIGHT = 1 ]; then
  git add "editions/$SLUG.json" briefed sitemap.xml tools/publish_day.sh tools/build_briefed.py tools/make_night_edition.py tools/test_analytics.py editions/README.md
else
  git add "editions/$DAY.json" briefed sitemap.xml
fi
if git diff --cached --quiet; then log "nothing changed"; else
  MSG="Briefed: publish $DAY"
  [ $NIGHT = 1 ] && MSG="Briefed: publish $DAY night update"
  git -c user.name="Briefed Bot" -c user.email="info@ljiindustries.com" commit -qm "$MSG"
  git "${AUTH[@]}" push -q origin main 2>&1 | sed -E 's/(gh[pousr]_|github_pat_)[A-Za-z0-9_]+/[REDACTED]/g'
  log "pushed $(git rev-parse --short HEAD)"
fi

# --- verify live (up to 10 min) ---
LONG=$(python3 -c "from datetime import date;print(date.fromisoformat('$DAY').strftime('%A, %B %-d, %Y'))")
if [ $NIGHT = 1 ]; then
  NIGHT_URL="https://ljiindustries.com/briefed/$SLUG/"
  MORN_URL="https://ljiindustries.com/briefed/$DAY/"
  VID="https://ljiindustries.com/briefed/media/$SLUG/Briefed-$SLUG-web.mp4"
  POSTER="https://ljiindustries.com/briefed/media/$SLUG/Briefed-$SLUG-poster.jpg"
  for i in $(seq 1 20); do
    PAGE=$(curl -sf "$NIGHT_URL?v=$(date +%s)" -H 'Cache-Control: no-cache' || true)
    MORN=$(curl -sf "$MORN_URL?v=$(date +%s)" -H 'Cache-Control: no-cache' || true)
    ARCH=$(curl -sf "https://ljiindustries.com/briefed/archive/?v=$(date +%s)" -H 'Cache-Control: no-cache' || true)
    VC=$(curl -sSI "$VID?v=$(date +%s)" -H 'Cache-Control: no-cache' || true)
    PC=$(curl -sSI "$POSTER?v=$(date +%s)" -H 'Cache-Control: no-cache' || true)
    if grep -q "Night update" <<<"$PAGE" && grep -q "$LONG" <<<"$MORN" && grep -q "/briefed/$SLUG/" <<<"$ARCH" \
       && grep -qiE 'HTTP/.* 200' <<<"$VC" && grep -qi 'video/mp4' <<<"$VC" && grep -qiE 'HTTP/.* 200' <<<"$PC" \
       && [ "$(grep -c 'class="b-story' <<<"$MORN")" = 6 ]; then
      log "LIVE: $NIGHT_URL and morning edition intact"
      exit 0
    fi
    sleep 30
  done
  echo "[publish $SLUG] FAILED: night page or morning edition not verified within 10 minutes" >&2; exit 7
else
  for i in $(seq 1 20); do
    PAGE=$(curl -sf "https://ljiindustries.com/briefed/?v=$(date +%s)" -H 'Cache-Control: no-cache' || true)
    if grep -qF "$LONG" <<<"$PAGE"; then log "LIVE: ljiindustries.com/briefed shows $LONG"; exit 0; fi
    sleep 30
  done
  echo "[publish $DAY] FAILED: /briefed/ did not show '$LONG' within 10 minutes" >&2; exit 7
fi
