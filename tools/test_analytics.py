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
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name):
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


if __name__ == "__main__":
    unittest.main()
