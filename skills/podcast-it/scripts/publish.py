#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["click"]
# ///
"""Add an Ogg Opus episode to your private podcast feed.

Copies the audio to <feed_dir>/<slug>.ogg, writes the sidecar <slug>.json (title, description,
date, duration, source), rebuilds feed.xml (feed.py), and, when the config has a "sync" target,
copies the feed folder there with rsync. rsync never deletes anything on the target.

The feed folder works two ways: serve it from a web server (the sync target), or sync it to
your phone and add it in AntennaPod as a local folder, which needs no feed.xml at all.

Examples:
  publish.py episode.ogg anger-books "Anger: what the books say" "A walk through four books." --source research --dry-run
  publish.py episode.ogg anger-books "Anger: what the books say" "A walk through four books." --source research --notes script.md

--notes appends the script's === NOTES === block (numbers, names, links: the companion text)
to the description, which podcast apps show as the episode notes.
"""

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import click

from feed import CONFIG, load_config, write_feed


def duration(path: Path) -> str:
    seconds = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


@click.command()
@click.argument("audio", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("slug")
@click.argument("title")
@click.argument("description")
@click.option("--source", required=True, help="Kind of material, for example work or research; picks the episode picture art/<source>.jpg")
@click.option("--notes", "notes_from", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Script whose === NOTES === block is appended to the description")
@click.option("--dry-run", is_flag=True, help="Print what would happen; change nothing")
def main(audio, slug, title, description, source, notes_from, dry_run):
    config = load_config()
    if not config.get("feed_dir"):
        raise click.ClickException(f"no feed_dir in {CONFIG}; run the setup in SKILL.md first")
    feed_dir = Path(config["feed_dir"]).expanduser()
    if notes_from:
        text = notes_from.read_text()
        m = re.search(r"^=== NOTES ===\s*$", text, re.MULTILINE)
        if not m:
            raise click.ClickException(f"no === NOTES === block in {notes_from}")
        block = re.split(r"^=== SOURCES ===\s*$", text[m.end() :], maxsplit=1, flags=re.MULTILINE)[0].strip()
        description = f"{description}\n\n{block}"
    if audio.suffix != ".ogg":
        raise click.ClickException("render.py writes .ogg (Ogg Opus); publish that file")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise click.ClickException("slug must be lowercase words joined by hyphens")
    target = feed_dir / f"{slug}.ogg"
    if target.exists():
        raise click.ClickException(f"{target} already exists; pick another slug")
    meta = {
        "title": title,
        "description": description,
        "published": datetime.now().astimezone().isoformat(timespec="seconds"),
        "duration": duration(audio),
        "source": source,
    }
    sync = config.get("sync")
    if dry_run:
        click.echo(f"would copy {audio} -> {target}")
        click.echo(f"would write {target.with_suffix('.json')}:\n{json.dumps(meta, indent=2)}")
        click.echo(f"would rebuild {feed_dir / 'feed.xml'}")
        click.echo(f"would rsync {feed_dir}/ -> {sync}" if sync else "no sync target in the config; the folder stays local")
        return
    feed_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audio, target)
    target.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    click.echo(f"wrote {write_feed(feed_dir, config)}")
    if sync:
        subprocess.run(["rsync", "-a", f"{feed_dir}/", sync], check=True)
        click.echo(f"synced to {sync}")
    if config.get("base_url"):
        click.echo(f"{config['base_url'].rstrip('/')}/feed.xml")


if __name__ == "__main__":
    main()
