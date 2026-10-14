#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["click"]
# ///
"""Build feed.xml for a private podcast from one folder of episodes.

The folder holds, per episode, the audio (<slug>.ogg, or .mp3) and a sidecar <slug>.json:

  {"title": "...", "description": "...", "published": "2026-10-14T09:30:00+02:00",
   "duration": "0:14:05", "source": "research"}

and the pictures in art/: channel.jpg for the feed, and <source>.jpg for each source. An episode
whose source has no picture gets channel.jpg. Serve art/ without a login: some podcast apps do
not send the login when they fetch images.

The feed settings come from the config file (see SKILL.md): base_url, title, description, author.
The feed is built from the files on disk, so it always lists what can be downloaded.

Examples:
  feed.py                                   # build <feed_dir>/feed.xml from the config
  feed.py --dir ./podcast --base-url https://podcast.example.com
"""

from __future__ import annotations

import datetime as dt
import json
import os
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import click

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
AUDIO_TYPES = {".ogg": "audio/ogg", ".mp3": "audio/mpeg"}
CHANNEL_ART = "channel.jpg"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "podcast-it" / "config.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def episodes(directory: Path) -> list[tuple[Path, dict]]:
    """Audio files with a readable sidecar, newest first. A file without one is skipped."""
    found = []
    for path in directory.iterdir():
        if path.suffix not in AUDIO_TYPES:
            continue
        try:
            meta = json.loads(path.with_suffix(".json").read_text())
            dt.datetime.fromisoformat(meta["published"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        found.append((path, meta))
    return sorted(found, key=lambda e: dt.datetime.fromisoformat(e[1]["published"]), reverse=True)


def art_for(directory: Path, meta: dict) -> str:
    source = meta.get("source")
    if source and (directory / "art" / f"{source}.jpg").is_file():
        return f"{source}.jpg"
    return CHANNEL_ART


def build_feed(directory: Path, base_url: str, title: str, description: str, author: str) -> str:
    base = base_url.rstrip("/")
    ET.register_namespace("itunes", ITUNES)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = f"{base}/feed.xml"
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, f"{{{ITUNES}}}author").text = author
    ET.SubElement(channel, f"{{{ITUNES}}}explicit").text = "false"
    ET.SubElement(channel, f"{{{ITUNES}}}summary").text = description
    if (directory / "art" / CHANNEL_ART).is_file():
        ET.SubElement(channel, f"{{{ITUNES}}}image", {"href": f"{base}/art/{CHANNEL_ART}"})
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = f"{base}/art/{CHANNEL_ART}"
        ET.SubElement(image, "title").text = title
        ET.SubElement(image, "link").text = f"{base}/feed.xml"

    for path, meta in episodes(directory):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = meta.get("title") or path.stem
        ET.SubElement(item, "description").text = meta.get("description") or ""
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = path.stem
        ET.SubElement(item, "pubDate").text = format_datetime(dt.datetime.fromisoformat(meta["published"]))
        ET.SubElement(
            item,
            "enclosure",
            {"url": f"{base}/{path.name}", "length": str(path.stat().st_size), "type": AUDIO_TYPES[path.suffix]},
        )
        if (directory / "art" / art_for(directory, meta)).is_file():
            ET.SubElement(item, f"{{{ITUNES}}}image", {"href": f"{base}/art/{art_for(directory, meta)}"})
        if meta.get("duration"):
            ET.SubElement(item, f"{{{ITUNES}}}duration").text = meta["duration"]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")


def write_feed(directory: Path, config: dict, base_url: str | None = None) -> Path:
    base_url = base_url or config.get("base_url")
    if not base_url:
        raise click.ClickException(f"no base_url: set it in {CONFIG} or pass --base-url")
    out = directory / "feed.xml"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(
        build_feed(
            directory,
            base_url,
            config.get("title", "My private podcast"),
            config.get("description", "Episodes made with the podcast-it skill."),
            config.get("author", "podcast-it"),
        )
    )
    tmp.rename(out)  # a podcast app never reads a half-written feed
    return out


@click.command()
@click.option("--dir", "directory", type=click.Path(file_okay=False, path_type=Path), help="Feed folder (default: feed_dir in the config)")
@click.option("--base-url", help="URL where the feed folder is served (default: base_url in the config)")
def main(directory: Path | None, base_url: str | None) -> None:
    config = load_config()
    directory = directory or (Path(config["feed_dir"]).expanduser() if config.get("feed_dir") else None)
    if not directory:
        raise click.ClickException(f"no feed folder: set feed_dir in {CONFIG} or pass --dir")
    out = write_feed(directory, config, base_url)
    click.echo(f"wrote {out}: {len(episodes(directory))} episodes")


if __name__ == "__main__":
    main()
