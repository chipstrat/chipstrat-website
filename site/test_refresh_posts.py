import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from refresh_posts import fetch_feed, parse_feed, refresh


def feed(items):
    return ("<rss><channel><title>Chipstrat</title><link>https://chipstrat.substack.com</link>"
            + "".join(items) + "</channel></rss>").encode()


def item(slug, title="New Nvidia research", extra="", day="09"):
    return (f"<item><title>{title}</title><link>https://chipstrat.substack.com/p/{slug}</link>"
            f"<pubDate>Fri, {day} Oct 2026 12:00:00 GMT</pubDate>"
            f"<description>Chips &amp; AI</description>{extra}</item>")


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "posts.json"
        self.old = dict(id=1, slug="old", title="Older research", subtitle="Original",
                        post_date="2025-01-01T12:00:00.123Z", type="video",
                        audience="only_paid", postTags=[{"name": "Foundry"}],
                        cover_image="https://example.com/image.png", wordcount=4000)
        self.path.write_text(json.dumps([self.old]))

    def test_feed_window_rollover_keeps_older_and_newly_discovered_posts(self):
        first = refresh(self.path, lambda: feed([item("first")]))
        second = refresh(self.path, lambda: feed([item("second", day="10")]))
        posts = json.loads(self.path.read_text())
        self.assertEqual([p["slug"] for p in posts], ["second", "first", "old"])
        self.assertEqual(posts[-1], self.old)
        self.assertEqual((first["added"], second["total"]), (1, 3))

    def test_rerun_is_idempotent_and_preserves_exact_file(self):
        payload = feed([item("new")])
        refresh(self.path, lambda: payload)
        before = self.path.read_bytes()
        report = refresh(self.path, lambda: payload)
        self.assertEqual((report["added"], report["updated"]), (0, 0))
        self.assertEqual(self.path.read_bytes(), before)

    def test_edits_keep_metadata_that_rss_does_not_supply(self):
        payload = feed([item("old", "Updated title &amp; subtitle")])
        refresh(self.path, lambda: payload)
        post = json.loads(self.path.read_text())[0]
        self.assertEqual(post["title"], "Updated title & subtitle")
        for key in ("id", "type", "audience", "postTags", "wordcount", "cover_image"):
            self.assertEqual(post[key], self.old[key])

    def test_bad_responses_never_replace_archive(self):
        good = feed([item("new")])
        bad = [b"<html>Access denied</html>", feed([]), feed([item("same"), item("same")]),
               good.replace(b"chipstrat.substack.com", b"other.substack.com"),
               good.replace(b"Fri, 09 Oct 2026 12:00:00 GMT", b"not-a-date"),
               good.replace(b"/p/new", b"/p/../../unexpected"),
               b'<!DOCTYPE rss [<!ENTITY x "bad">]>' + good]
        before = self.path.read_bytes()
        for payload in bad:
            with self.subTest(payload=payload[:80]):
                with self.assertRaises((ValueError, TypeError)):
                    refresh(self.path, lambda: payload)
                self.assertEqual(self.path.read_bytes(), before)

    def test_network_failure_keeps_archive(self):
        before = self.path.read_bytes()
        error = urllib.error.HTTPError("feed", 403, "Forbidden", {}, None)
        self.addCleanup(error.close)
        with self.assertRaises(urllib.error.HTTPError):
            refresh(self.path, lambda: (_ for _ in ()).throw(error))
        self.assertEqual(self.path.read_bytes(), before)

    def test_categories_and_media_are_captured_without_article_body(self):
        payload = feed([item("new", extra='<category>Foundry</category>'
                            '<enclosure type="audio/mpeg" url="https://example.com/audio.mp3"/>'
                            '<body>Private content must not enter the index</body>')])
        refresh(self.path, lambda: payload)
        post = json.loads(self.path.read_text())[0]
        self.assertEqual(post["postTags"], [{"name": "Foundry"}])
        self.assertEqual(post["type"], "podcast")
        self.assertNotIn("Private content", self.path.read_text())

    def test_retry_only_transient_server_failures(self):
        for status, attempts in [(403, 1), (429, 1), (503, 3)]:
            error = urllib.error.HTTPError("feed", status, "failure", {}, None)
            self.addCleanup(error.close)
            with patch("refresh_posts.urllib.request.urlopen", side_effect=error) as request:
                with patch("refresh_posts.time.sleep"):
                    with self.assertRaises(urllib.error.HTTPError):
                        fetch_feed()
                self.assertEqual(request.call_count, attempts)


if __name__ == "__main__":
    unittest.main()
