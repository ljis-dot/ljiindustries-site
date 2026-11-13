#!/usr/bin/env python3
"""Beacon coverage: homepage + every Briefed page the generator emits. Notes and 404 stay out."""
import json, os, re, sys, tempfile, unittest, warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_briefed as b

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOKEN = "72d001bbabb842c482d7888f61492a53"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class Analytics(unittest.TestCase):
    def test_snippet_is_one_official_beacon(self):
        snip = b.analytics_snippet()
        self.assertEqual(b.CF_BEACON_TOKEN, TOKEN)
        self.assertEqual(snip.count("beacon.min.js"), 1)
        self.assertEqual(snip.count(TOKEN), 1)
        self.assertIn('defer src="https://static.cloudflareinsights.com/beacon.min.js"', snip)
        self.assertIn("data-cf-beacon=", snip)
        self.assertEqual(json.loads(snip.split("data-cf-beacon='", 1)[1].split("'", 1)[0]), {"token": TOKEN})
        self.assertNotIn("spa", snip)

    def test_csp_adds_only_beacon_hosts(self):
        plain = b.content_security_policy(False)
        wide = b.content_security_policy(True)
        self.assertEqual(
            plain,
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://github.com https://*.githubusercontent.com; "
            "media-src 'self' https://github.com https://*.githubusercontent.com; "
            "font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests",
        )
        self.assertIn("script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com;", wide)
        self.assertIn("connect-src 'self' https://cloudflareinsights.com;", wide)
        self.assertIn("object-src 'none'", wide)
        self.assertNotIn("unsafe-eval", wide)

    def test_generator_counts_briefed_once_and_skips_notes(self):
        for canon in ("/briefed/", "/briefed/archive/", "/briefed/about/", "/briefed/2026-11-07/"):
            html = b.page("t", "d", canon, "<p>x</p>")
            self.assertEqual(html.count(b.analytics_snippet()), 1, canon)
            self.assertEqual(html.count(TOKEN), 1, canon)
            self.assertIn(b.content_security_policy(True), html, canon)
            self.assertTrue(html.rstrip().endswith("</html>"), canon)
            self.assertIn(b.analytics_snippet() + "\n</body>", html, canon)
        notes = b.page("t", "d", "/notes/", "<p>x</p>")
        self.assertNotIn("beacon.min.js", notes)
        self.assertNotIn("cloudflareinsights", notes)
        self.assertIn(b.content_security_policy(False), notes)

    def test_checked_in_pages(self):
        briefed = [
            "index.html",
            "briefed/index.html",
            "briefed/archive/index.html",
            "briefed/about/index.html",
        ]
        for name in sorted(os.listdir(os.path.join(ROOT, "briefed"))):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(-night)?", name):
                briefed.append(f"briefed/{name}/index.html")
        self.assertGreaterEqual(sum(1 for p in briefed if "/20" in p), 15)
        for rel in briefed:
            html = read(rel)
            self.assertEqual(html.count(b.analytics_snippet()), 1, rel)
            self.assertIn(b.content_security_policy(True), html, rel)
        for rel in ("notes/index.html", "404.html"):
            html = read(rel)
            self.assertNotIn("beacon.min.js", html, rel)
            self.assertNotIn("cloudflareinsights", html, rel)
            self.assertIn(b.content_security_policy(False), html, rel)

    def test_build_writes_future_editions(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is required to render share cards during build")
        with open(os.path.join(ROOT, "editions", "2026-11-07.json"), encoding="utf-8") as f:
            ed = json.load(f)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                f.write("<style>body{color:#111}</style>")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                b.build(tmp, [ed], preview=True)
            for rel in (
                "briefed/index.html",
                "briefed/archive/index.html",
                "briefed/about/index.html",
                "briefed/2026-11-07/index.html",
            ):
                with open(os.path.join(tmp, rel), encoding="utf-8") as f:
                    html = f.read()
                self.assertEqual(html.count(b.analytics_snippet()), 1, rel)
            with open(os.path.join(tmp, "notes", "index.html"), encoding="utf-8") as f:
                notes = f.read()
            self.assertNotIn("beacon.min.js", notes)
            self.assertIn(b.content_security_policy(False), notes)


    def test_night_addendum_keeps_daily_latest_and_beacon(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is required to render share cards during build")
        with open(os.path.join(ROOT, "editions", "2026-11-09.json"), encoding="utf-8") as f:
            daily = json.load(f)
        night = {
            "schemaVersion": 1,
            "kind": "night",
            "date": "2026-11-09",
            "slug": "2026-11-09-night",
            "generatedAt": "2026-11-09T20:28:00-05:00",
            "stories": [{
                "id": "massie-hegseth",
                "region": "us",
                "location": "Washington, DC",
                "headline": "Massie files 8 impeachment articles against Hegseth; House vote by Wednesday",
                "status": "reported-only",
                "outlets": [{"name": "NBC News", "url": "https://www.nbcnews.com/politics/trump-administration/thomas-massie-pete-hegseth-impeachment-house-defense-rcna597989"}],
                "officialSources": [],
                "summary": "Massie reintroduced eight articles of impeachment against Defense Secretary Pete Hegseth.",
            }],
            "briefing": {"quickFacts": ["Massie **reintroduced eight articles**."], "notYetConfirmed": ["Whether a floor vote is held."], "whatHappensNext": ["Tuesday morning: Pentagon press conference."]},
            "photoCredits": [{"subject": "Rep. Thomas Massie", "credit": "House Creative Services, circa 2025", "license": "Public domain (PD-USGov)", "url": "https://commons.wikimedia.org/wiki/File:Massie_Thomas_119th_Congress.jpg", "source": "Wikimedia Commons"}],
            "video": {"url": "/briefed/media/2026-11-09-night/Briefed-2026-11-09-night-web.mp4", "poster": "/briefed/media/2026-11-09-night/Briefed-2026-11-09-night-poster.jpg", "durationSeconds": 57.5, "aiVoices": True, "chapters": [{"storyId": "massie-hegseth", "title": "Massie Hegseth", "start": 0, "end": 49}]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                f.write("<style>body{color:#111}</style>")
            os.makedirs(os.path.join(tmp, "sitemap-src"), exist_ok=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                b.build(tmp, [daily], preview=True, addenda=[night])
            def readp(*parts):
                with open(os.path.join(tmp, *parts), encoding="utf-8") as f:
                    return f.read()
            home = readp("briefed", "index.html")
            morn = readp("briefed", "2026-11-09", "index.html")
            night_page = readp("briefed", "2026-11-09-night", "index.html")
            latest = json.loads(readp("briefed", "latest.json"))
            archive = readp("briefed", "archive", "index.html")
            self.assertEqual(latest["date"], "2026-11-09")
            self.assertNotIn("kind", latest)
            self.assertEqual(len(latest["stories"]), 6)
            self.assertIn("/briefed/2026-11-09-night/", home)
            self.assertIn("/briefed/2026-11-09-night/", morn)
            self.assertEqual(morn.count('class="b-story'), 6)
            self.assertIn("trump-deportation", morn)
            self.assertNotIn("massie-hegseth", morn)
            self.assertIn("Night update", night_page)
            self.assertIn("Quick facts", night_page)
            self.assertIn("Not yet confirmed", night_page)
            self.assertIn("What happens next", night_page)
            self.assertIn("Portrait credits", night_page)
            self.assertIn("/briefed/2026-11-09-night/", archive)
            self.assertIn("Morning edition", night_page)
            for rel, html in (("home", home), ("morn", morn), ("night", night_page), ("archive", archive)):
                self.assertEqual(html.count(b.analytics_snippet()), 1, rel)
                self.assertNotRegex(html, r"Levi|Schmieg")
            # no addenda: homepage should not grow a night banner
            with tempfile.TemporaryDirectory() as tmp2:
                with open(os.path.join(tmp2, "index.html"), "w", encoding="utf-8") as f:
                    f.write("<style>body{color:#111}</style>")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    b.build(tmp2, [daily], preview=True)
                with open(os.path.join(tmp2, "briefed", "index.html"), encoding="utf-8") as f:
                    home2 = f.read()
                self.assertNotIn("/briefed/2026-11-09-night/", home2)
                self.assertNotIn("Night update", home2)


    def test_archive_lists_headlines_and_follow_links(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is required to render share cards during build")
        with open(os.path.join(ROOT, "editions", "2026-11-09.json"), encoding="utf-8") as f:
            daily = json.load(f)
        with open(os.path.join(ROOT, "editions", "2026-11-13.json"), encoding="utf-8") as f:
            later = json.load(f)
        night = {
            "schemaVersion": 1,
            "kind": "night",
            "date": "2026-11-09",
            "slug": "2026-11-09-night",
            "stories": [{
                "id": "massie-hegseth",
                "region": "us",
                "location": "Washington, DC",
                "headline": "Massie files 8 impeachment articles against Hegseth; House vote by Wednesday",
                "status": "reported-only",
                "outlets": [],
                "officialSources": [],
                "summary": "Massie reintroduced eight articles of impeachment against Defense Secretary Pete Hegseth.",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                f.write("<style>body{color:#111}</style>")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                b.build(tmp, [later, daily], preview=True, addenda=[night])
            def readp(*parts):
                with open(os.path.join(tmp, *parts), encoding="utf-8") as f:
                    return f.read()
            arch = readp("briefed", "archive", "index.html")
            home = readp("briefed", "index.html")
            about = readp("briefed", "about", "index.html")
            today = readp("briefed", "2026-11-13", "index.html")
            older = readp("briefed", "2026-11-09", "index.html")
        def assert_follow(html, label):
            self.assertIn("Follow us on:", html, label)
            self.assertIn('href="https://www.tiktok.com/@briefedtoday3" rel="noopener" target="_blank"', html, label)
            self.assertIn('href="https://x.com/briefedtoday" rel="noopener" target="_blank"', html, label)
            self.assertEqual(html.count("Follow us on:"), 1, label)
        assert_follow(arch, "archive")
        assert_follow(home, "home")
        assert_follow(about, "about")
        assert_follow(today, "today")
        assert_follow(older, "older")
        self.assertIn('id="b-arch-filters"', arch)
        self.assertIn('id="b-arch-q"', arch)
        self.assertIn('id="b-arch-from"', arch)
        self.assertIn('id="b-arch-to"', arch)
        self.assertIn("/briefed/2026-11-13/", arch)
        self.assertIn("/briefed/2026-11-09/", arch)
        self.assertIn("/briefed/2026-11-09-night/", arch)
        self.assertIn("Night update", arch)
        # all headlines, not just the lead
        for headline in [s["headline"] for s in later["stories"]]:
            self.assertIn(headline, arch)
        self.assertIn('data-search=', arch)
        self.assertIn("ibogaine", arch.lower())
        self.assertEqual(arch.count(b.analytics_snippet()), 1)
        self.assertIn("mailto:info@ljiindustries.com", arch)
        self.assertNotRegex(arch, r"Levi|Schmieg")
        self.assertIn("The full archive is listed below", arch)  # noscript fallback
        # from/to bounds come from the edition set
        self.assertIn('min="2026-11-09"', arch)
        self.assertIn('max="2026-11-13"', arch)


if __name__ == "__main__":
    unittest.main()
