#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["click"]
# ///
"""Turn voice samples into a blind test: numbered files that do not give away which voice is which.

Every sample is converted to the same format (Ogg Opus, 16 kbps mono, the format of a real
episode) and the same loudness, so neither file type nor volume betrays the engine. The files
get shuffled numbers; the answer goes to key.json in the same folder. Do not open key.json
before you have ranked the numbers.

Name each input after what it is (for example openai-marin.wav, kokoro-af_heart.wav): that
name goes in the key.

Examples:
  blind_test.py samples/*.wav -o blind/      # writes blind/1.ogg, blind/2.ogg, ... and blind/key.json
  blind_test.py --reveal blind/              # after ranking: print which number was which
"""

import json
import random
import subprocess
from pathlib import Path

import click


@click.command()
@click.argument("samples", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--out", type=click.Path(file_okay=False, path_type=Path), help="Folder for the numbered files and key.json")
@click.option("--reveal", is_flag=True, help="Print the key of the folder given as the only argument")
def main(samples, out, reveal):
    if reveal:
        if len(samples) != 1 or not samples[0].is_dir():
            raise click.UsageError("--reveal takes one folder")
        for number, name in json.loads((samples[0] / "key.json").read_text()).items():
            click.echo(f"{number}: {name}")
        return
    if len(samples) < 2 or not out:
        raise click.UsageError("give at least two samples and -o <folder>")
    out.mkdir(parents=True, exist_ok=True)
    order = list(samples)
    random.shuffle(order)
    key = {}
    for number, path in enumerate(order, start=1):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af", "loudnorm=I=-18:TP=-1.5:LRA=11", "-ac", "1",
             "-c:a", "libopus", "-b:a", "16k", "-application", "voip", str(out / f"{number}.ogg")],
            check=True,
        )
        key[str(number)] = path.stem
    (out / "key.json").write_text(json.dumps(key, indent=2))
    click.echo(f"wrote {len(order)} numbered samples to {out}; rank them before you run --reveal")


if __name__ == "__main__":
    main()
