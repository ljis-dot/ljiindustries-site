# Briefed editions (input)
One file per day, `YYYY-MM-DD.json`, public schema v1, written by the morning job. Days before 2026-10-25 are ignored by the build.
Fields: schemaVersion, date, generatedAt, stories[{id, region us|foreign, location?, headline, summary?, status, statusNote?, whyItMattersToUS (required for foreign, max 2), outlets[{name, url?}], officialSources[url], firstHand?[{who, handle, role, date, url (http(s)), quote}]}], audio?{url (GitHub Release asset), durationSeconds, aiVoices:true, chapters[{storyId|null, title, start, end}]}.
No article text, no verification quotes, no owner name, no pricing. Build: `python3 tools/build_briefed.py`.
Night addenda are optional `YYYY-MM-DD-night.json` files (`kind: night`, `slug: YYYY-MM-DD-night`). They publish at `/briefed/YYYY-MM-DD-night/`, are linked from that morning's edition and the archive, and never replace today's edition on the homepage.
