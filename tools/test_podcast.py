#!/usr/bin/env python3
"""Podcast RSS: episodes, iTunes tags, MP3 preservation, site-rule guards."""
import json, os, re, subprocess, tempfile, unittest, warnings, xml.etree.ElementTree as ET
from datetime import datetime

import build_briefed as b

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"


def _silent_mp3(path, seconds=2):
    subprocess.check_call(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", str(seconds), "-codec:a", "libmp3lame", "-q:a", "9", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


class PodcastFeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import PIL  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Pillow is required to render share cards during build")

    def test_feed_includes_only_days_with_mp3_and_keeps_the_file(self):
        with open(os.path.join(ROOT, "editions", "2026-11-16.json"), encoding="utf-8") as f:
            ed16 = json.load(f)
        with open(os.path.join(ROOT, "editions", "2026-11-15.json"), encoding="utf-8") as f:
            ed15 = json.load(f)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                f.write("<style>body{color:#111}</style>")
            day_dir = os.path.join(tmp, "briefed", "2026-11-16")
            os.makedirs(day_dir, exist_ok=True)
            mp3 = os.path.join(day_dir, "Briefed-2026-11-16.mp3")
            _silent_mp3(mp3, 2)
            size = os.path.getsize(mp3)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                b.build(tmp, [ed16, ed15], preview=True)
            self.assertTrue(os.path.isfile(mp3), "build must not delete the episode MP3")
            self.assertEqual(os.path.getsize(mp3), size)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "briefed", "2026-11-16", "index.html")))
            xml_path = os.path.join(tmp, "briefed", "podcast.xml")
            self.assertTrue(os.path.isfile(xml_path))
            with open(xml_path, encoding="utf-8") as fh:
                xml = fh.read()
            self.assertIn("Briefed-2026-11-16.mp3", xml)
            self.assertNotIn("Briefed-2026-11-15.mp3", xml)
            self.assertIn('length="%d"' % size, xml)
            self.assertIn("<itunes:duration>0:02</itunes:duration>", xml)
            self.assertIn("<guid isPermaLink=\"false\">briefed-2026-11-16</guid>", xml)
            self.assertNotRegex(xml, r"Levi|Schmieg")
            self.assertIn("info@ljiindustries.com", xml)
            self.assertEqual(len(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", xml, re.I)), 1)

    def test_required_itunes_tags_and_title_shape(self):
        with open(os.path.join(ROOT, "editions", "2026-11-16.json"), encoding="utf-8") as f:
            ed = json.load(f)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                f.write("<style>body{color:#111}</style>")
            day_dir = os.path.join(tmp, "briefed", "2026-11-16")
            os.makedirs(day_dir, exist_ok=True)
            _silent_mp3(os.path.join(day_dir, "Briefed-2026-11-16.mp3"), 2)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                b.build(tmp, [ed], preview=True)
            with open(os.path.join(tmp, "briefed", "podcast.xml"), encoding="utf-8") as fh:
                xml = fh.read()
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "rss")
        self.assertEqual(root.attrib.get("version"), "2.0")
        chan = root.find("channel")
        self.assertEqual(chan.findtext("title"), "Briefed")
        self.assertEqual(chan.findtext("link"), "https://ljiindustries.com/briefed/")
        self.assertEqual(chan.findtext("language"), "en-us")
        self.assertEqual(chan.findtext(f"{{{ITUNES}}}author"), "Briefed News")
        self.assertEqual(chan.findtext(f"{{{ITUNES}}}explicit"), "false")
        owner = chan.find(f"{{{ITUNES}}}owner")
        self.assertEqual(owner.findtext(f"{{{ITUNES}}}name"), "Briefed News")
        self.assertEqual(owner.findtext(f"{{{ITUNES}}}email"), "info@ljiindustries.com")
        cats = chan.findall(f"{{{ITUNES}}}category")
        self.assertEqual(cats[0].attrib.get("text"), "News")
        self.assertEqual(cats[0].find(f"{{{ITUNES}}}category").attrib.get("text"), "Daily News")
        image = chan.find(f"{{{ITUNES}}}image")
        self.assertEqual(image.attrib.get("href"), "https://ljiindustries.com/briefed/podcast-cover.jpg")
        self.assertEqual(chan.find("image").findtext("url"), "https://ljiindustries.com/briefed/podcast-cover.jpg")
        atom = chan.find(f"{{{ATOM}}}link")
        self.assertEqual(atom.attrib.get("rel"), "self")
        self.assertEqual(atom.attrib.get("href"), "https://ljiindustries.com/briefed/podcast.xml")
        self.assertEqual(atom.attrib.get("type"), "application/rss+xml")
        item = chan.find("item")
        self.assertIsNotNone(item)
        top = ed["stories"][0]["headline"]
        self.assertEqual(item.findtext("title"), f"Briefed · Mon, Nov 16: {top}")
        self.assertIn(top, item.findtext("description"))
        self.assertIn("https://ljiindustries.com/briefed/2026-11-16/", item.findtext("description"))
        enc = item.find("enclosure")
        self.assertEqual(enc.attrib.get("type"), "audio/mpeg")
        self.assertTrue(enc.attrib.get("length").isdigit())
        self.assertEqual(enc.attrib.get("url"), "https://ljiindustries.com/briefed/2026-11-16/Briefed-2026-11-16.mp3")
        self.assertEqual(item.find("guid").attrib.get("isPermaLink"), "false")
        self.assertEqual(item.findtext("guid"), "briefed-2026-11-16")
        self.assertEqual(item.findtext(f"{{{ITUNES}}}duration"), "0:02")
        self.assertEqual(item.findtext(f"{{{ITUNES}}}explicit"), "false")
        pub = item.findtext("pubDate")
        datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
        self.assertTrue(pub.endswith("-0500"), pub)
        self.assertIn("07:00:00", pub)

    def test_checked_in_feed_and_cover(self):
        xml_path = os.path.join(ROOT, "briefed", "podcast.xml")
        self.assertTrue(os.path.isfile(xml_path), "run tools/build_briefed.py to generate the feed")
        with open(xml_path, encoding="utf-8") as fh:
            xml = fh.read()
        self.assertIn("<title>Briefed</title>", xml)
        self.assertNotRegex(xml, r"Levi|Schmieg")
        self.assertNotRegex(xml, r"(?i)\bpricing\b")
        self.assertIn("info@ljiindustries.com", xml)
        cover = os.path.join(ROOT, "briefed", "podcast-cover.jpg")
        self.assertTrue(os.path.isfile(cover))
        from PIL import Image
        with Image.open(cover) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(img.mode, "RGB")
            self.assertEqual(img.size, (3000, 3000))
        mp3 = os.path.join(ROOT, "briefed", "2026-11-16", "Briefed-2026-11-16.mp3")
        self.assertTrue(os.path.isfile(mp3), "Nov 16 backfill MP3 is missing")
        self.assertIn('url="https://ljiindustries.com/briefed/2026-11-16/Briefed-2026-11-16.mp3"', xml)
        self.assertIn(f'length="{os.path.getsize(mp3)}"', xml)


if __name__ == "__main__":
    unittest.main()
