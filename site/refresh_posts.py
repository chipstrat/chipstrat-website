"""Merge Chipstrat's public RSS feed into the durable post index (no login needed)."""
import datetime as dt
import email.utils
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = "https://chipstrat.substack.com/feed"
POST_HOSTS = {"chipstrat.substack.com", "newsletter.chipstrat.com", "www.chipstrat.com"}
MAX_BYTES = 8 * 1024 * 1024


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = Text()
    parser.feed(value or "")
    return html.unescape(" ".join("".join(parser.parts).split()))


def date(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Post date must include a timezone")
    return parsed


def fetch_feed():
    request = urllib.request.Request(FEED_URL, headers={
        "User-Agent": "Chipstrat-Website-Refresh/1.0 (+https://www.chipstrat.com)",
        "Accept": "application/rss+xml, application/xml;q=0.9",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError("RSS response exceeds the size limit")
            return payload
        except urllib.error.HTTPError as error:
            error.close()
            # Do not retry authentication, access-control or rate-limit refusals.
            if error.code not in {500, 502, 503, 504} or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def parse_feed(payload):
    if len(payload) > MAX_BYTES or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("Unexpected or oversized RSS document")
    root = ET.fromstring(payload)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise ValueError("Response is not an RSS feed")
    if urllib.parse.urlsplit(channel.findtext("link", "")).hostname not in POST_HOSTS:
        raise ValueError("RSS channel does not belong to Chipstrat")
    items = channel.findall("item")
    if not items:
        raise ValueError("RSS feed contains no posts")
    posts, seen = [], set()
    for item in items:
        url = urllib.parse.urlsplit(item.findtext("link", ""))
        match = re.fullmatch(r"/p/([a-zA-Z0-9_-]+)/?", url.path)
        if url.scheme != "https" or url.hostname not in POST_HOSTS or not match:
            raise ValueError("RSS contains an invalid article URL")
        slug = match[1]
        if slug in seen:
            raise ValueError(f"Duplicate RSS post: {slug}")
        seen.add(slug)
        title = plain(item.findtext("title"))
        published = email.utils.parsedate_to_datetime(item.findtext("pubDate", ""))
        if not title or published.tzinfo is None:
            raise ValueError(f"RSS post is missing a title or dated publication: {slug}")
        description = plain(item.findtext("description"))
        post = {
            "slug": slug, "title": title,
            "subtitle": re.sub(r"^(?:Watch|Listen) now(?: \([^)]*\))?\s*\|\s*", "", description),
            "post_date": published.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        categories = [plain(c.text) for c in item.findall("category") if plain(c.text)]
        if categories:
            post["postTags"] = [{"name": name} for name in dict.fromkeys(categories)]
        enclosure = item.find("enclosure")
        if enclosure is not None:
            media_type = enclosure.get("type", "")
            media_url = enclosure.get("url", "")
            if media_type.startswith("image/") and urllib.parse.urlsplit(media_url).scheme == "https":
                post["cover_image"] = media_url
            elif media_type.startswith("audio/"):
                post["type"] = "podcast"
            elif media_type.startswith("video/"):
                post["type"] = "video"
        if description.startswith("Watch now"):
            post["type"] = "video"
        elif description.startswith("Listen now"):
            post["type"] = "podcast"
        posts.append(post)
    return posts


def merge_posts(existing, incoming):
    """RSS is a recent window: absence never means deletion or removal of metadata."""
    by_slug = {}
    for post in existing:
        if not post.get("slug") or post["slug"] in by_slug:
            raise ValueError("Post index contains a missing or duplicate slug")
        date(post["post_date"])
        by_slug[post["slug"]] = dict(post)
    added = updated = 0
    for post in incoming:
        old = by_slug.get(post["slug"])
        if old is None:
            combined = dict(id="rss:" + post["slug"], audience=None, type="newsletter",
                            postTags=[], cover_image=None, wordcount=None)
            combined.update(post)
            added += 1
        else:
            combined = {**old, **post}
            # RSS dates omit milliseconds. Avoid changing the original timestamp.
            if date(old["post_date"]).replace(microsecond=0) == date(post["post_date"]):
                combined["post_date"] = old["post_date"]
            if combined != old:
                updated += 1
        by_slug[post["slug"]] = combined
    result = sorted(by_slug.values(), key=lambda p: (date(p["post_date"]), p["slug"]), reverse=True)
    return result, added, updated


def refresh(path, fetch=fetch_feed):
    path = Path(path)
    before = path.read_bytes()
    existing = json.loads(before)
    incoming = parse_feed(fetch())
    merged, added, updated = merge_posts(existing, incoming)
    # Validate the complete response before writing; failed requests leave the archive intact.
    if added or updated:
        payload = json.dumps(merged, ensure_ascii=False).encode()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
                temp_path = temp.name
                temp.write(payload)
            os.replace(temp_path, path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    report = dict(source=FEED_URL, feed_posts=len(incoming), added=added, updated=updated,
                  total=len(merged), newest=max(date(p["post_date"]) for p in merged).isoformat())
    print(f"::notice::RSS refresh: {len(incoming)} recent posts, {added} added, "
          f"{updated} updated; {len(merged)} total")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### Post refresh\n\nPublic RSS fetch succeeded. {added} new posts, "
                    f"{updated} updated; {len(merged)} posts retained.\n\n"
                    "Older posts and metadata absent from RSS are preserved.\n")
    return report
