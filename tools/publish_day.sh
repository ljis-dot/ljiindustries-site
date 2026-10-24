#!/usr/bin/env bash
# Publish one Briefed day to ljiindustries.com/briefed.
# Usage: tools/publish_day.sh YYYY-MM-DD [--dry-run]
# Needs: $LJI_SITE_GITHUB_TOKEN (fine-grained, Contents R/W on ljiindustries-site). Never printed.
# Dry run: converts + builds into a temp copy of the repo; no release, commit, push or live check.
set -euo pipefail
DAY="${1:?usage: publish_day.sh YYYY-MM-DD [--dry-run]}"; DRY=0; [ "${2:-}" = "--dry-run" ] && DRY=1
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad date: $DAY" >&2; exit 2; }
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OWNER_REPO="ljis-dot/ljiindustries-site"
SRC="${BRIEFED_AUDIO_DIR:-/workspace/briefed-audio}/$DAY"
MP3="$SRC/Briefed-$DAY-full-twohost.mp3"; CH="$SRC/Briefed-$DAY-full-twohost-chapters.json"
TAG="briefed-$DAY"; API="https://api.github.com/repos/$OWNER_REPO"
for f in "$MP3" "$CH" "$SRC/v2/stories.json"; do [ -s "$f" ] || { echo "missing input: $f" >&2; exit 3; }; done
log(){ echo "[publish $DAY] $*"; }
gh_api(){ curl -sS -H "Authorization: Bearer $LJI_SITE_GITHUB_TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }
if [ $DRY = 0 ] && [[ "$DAY" < "2026-10-24" ]]; then echo "refusing: $DAY is before launch (2026-10-24)" >&2; exit 2; fi
AUDIO_URL="https://github.com/$OWNER_REPO/releases/download/$TAG/Briefed-$DAY-full-twohost.mp3"

if [ $DRY = 1 ]; then
  WORK="$(mktemp -d)"; (cd "$REPO_DIR" && git archive HEAD) | tar -x -C "$WORK"
  cp "$REPO_DIR/tools/"*.py "$WORK/tools/"   # test uncommitted tool changes too
  log "DRY RUN in $WORK (would create release $TAG and upload 2 assets)"
else
  : "${LJI_SITE_GITHUB_TOKEN:?LJI_SITE_GITHUB_TOKEN not set}"
  WORK="$REPO_DIR"
  AUTH=(-c credential.helper= -c http.extraheader="Authorization: Basic $(printf 'x-access-token:%s' "$LJI_SITE_GITHUB_TOKEN" | base64 -w0)")
  cd "$WORK"; git checkout -q main; git "${AUTH[@]}" pull -q --ff-only origin main
  # --- release (idempotent) ---
  REL=$(gh_api "$API/releases/tags/$TAG")
  RID=$(printf '%s' "$REL" | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))")
  if [ -z "$RID" ]; then
    RID=$(gh_api -X POST "$API/releases" -d "{\"tag_name\":\"$TAG\",\"target_commitish\":\"main\",\"name\":\"Briefed $DAY\",\"body\":\"Briefed audio edition for $DAY (AI-voiced). MP3 + chapters.\",\"prerelease\":true}" \
      | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('id') or '')")
    [ -n "$RID" ] || { echo "release create failed" >&2; exit 4; }; log "created release $TAG ($RID)"
  else log "release $TAG exists ($RID)"; fi
  for f in "$MP3" "$CH"; do
    n=$(basename "$f")
    old=$(gh_api "$API/releases/$RID/assets?per_page=100" | python3 -c "import json,sys;print(next((str(a['id']) for a in json.load(sys.stdin) if a['name']=='$n'),''))")
    [ -n "$old" ] && gh_api -X DELETE "$API/releases/assets/$old" >/dev/null && log "replaced old asset $n"
    ct=$([[ $n == *.mp3 ]] && echo audio/mpeg || echo application/json)
    code=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $LJI_SITE_GITHUB_TOKEN" -H "Content-Type: $ct" --data-binary @"$f" \
      "https://uploads.github.com/repos/$OWNER_REPO/releases/$RID/assets?name=$n")
    [ "$code" = 201 ] || { echo "upload $n failed: HTTP $code" >&2; exit 5; }; log "uploaded $n"
  done
  curl -sfIL -o /dev/null "$AUDIO_URL" || { echo "audio URL not reachable: $AUDIO_URL" >&2; exit 6; }
fi

# --- convert + build ---
python3 "$WORK/tools/make_edition.py" "$DAY" "$WORK/editions/$DAY.json" --audio-url "$AUDIO_URL"
(cd "$WORK" && python3 tools/build_briefed.py)

if [ $DRY = 1 ]; then
  if [[ "$DAY" < "2026-10-24" ]]; then
    log "note: $DAY is before launch (2026-10-24), so the real build skips it; rendering preview copy too"
    (cd "$WORK" && python3 tools/build_briefed.py --preview "editions/$DAY.json" >/dev/null)
  fi
  log "DRY RUN done. Output: $WORK/briefed/ ; would commit editions/$DAY.json + briefed/ + sitemap.xml and push to main"
  echo "$WORK"; exit 0
fi

# --- commit + push ---
git add "editions/$DAY.json" briefed sitemap.xml
if git diff --cached --quiet; then log "nothing changed"; else
  git -c user.name="Briefed Bot" -c user.email="info@ljiindustries.com" commit -qm "Briefed: publish $DAY"
  git "${AUTH[@]}" push -q origin main 2>&1 | sed -E 's/(gh[pousr]_|github_pat_)[A-Za-z0-9_]+/[REDACTED]/g'
  log "pushed $(git rev-parse --short HEAD)"
fi

# --- verify live (up to 10 min) ---
LONG=$(python3 -c "from datetime import date;print(date.fromisoformat('$DAY').strftime('%A, %B %-d, %Y'))")
for i in $(seq 1 20); do
  if curl -sf "https://ljiindustries.com/briefed/?v=$(date +%s)" -H 'Cache-Control: no-cache' | grep -qF "$LONG"; then log "LIVE: ljiindustries.com/briefed shows $LONG"; exit 0; fi
  sleep 30
done
echo "[publish $DAY] FAILED: /briefed/ did not show '$LONG' within 10 minutes" >&2; exit 7
