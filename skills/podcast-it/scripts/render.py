#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "click", "openai>=1.60", "kokoro==0.9.4", "soundfile", "numpy", "faster-whisper",
#   # Kokoro's phonemizer loads this spaCy model and pip-installs it at run time when it is missing.
#   "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
"""Check a spoken script and render it to one Ogg Opus file, with OpenAI TTS or locally with Kokoro-82M.

Engines:
  openai   the newest priced OpenAI TTS model; paid, takes style instructions
  kokoro   local Kokoro-82M on the CPU; free, no key, no network after the first download.
           Good on short samples, but it mispronounces more words over a long episode.

The engine and the voices come from the config file that setup writes (see CONFIG below and
SKILL.md); --engine, --voice and --ask-voice override it for one run.

Without --yes this is a dry run: it checks the script and prints the engine, the voices, the
length, and the cost. It makes no paid call (listing OpenAI models is free). With --yes it renders.

Python is pinned to 3.12 because Kokoro 0.9.4 does not install on 3.13 or later. The first run
downloads the Kokoro and faster-whisper packages even when you use OpenAI; that is a one-time cost.

Script format (plain text, markdown headings allowed):
  ## Heading        starts a new segment and an ID3 chapter with that title; 2.5 s of silence before it
  Q: text           a paragraph for the second voice (the asker): a question, a recall prompt, or a
                    "so what"; every other paragraph is the narrator
  [pause]           on its own line: 2 s of silence, for a point the listener must think about
  [pause 3]         on its own line: 3 s of silence
  === NOTES ===     companion text for the feed description (publish.py --notes); not spoken
  === SOURCES ===   source notes for the editor; not spoken

After rendering, each spoken chunk is transcribed back (locally with faster-whisper by default)
and compared with the script. With --engine openai a chunk that does not match (TTS repeats,
skips, or long silences) is rendered again once. Kokoro is deterministic, so a mismatch is only
reported.

Key (for --engine openai or --transcriber openai): OPENAI_API_KEY from the environment.

Examples:
  render.py script.md -o episode.ogg                  # dry run: checks, engine, minutes, cost
  render.py script.md -o episode.ogg --yes            # render with OpenAI TTS (paid)
  render.py script.md --ask-voice none --yes          # one narrator; Q: lines in the narrator voice
  render.py script.md --engine kokoro --yes           # render locally with Kokoro (free)
  render.py sample.md --engine openai --voice coral --no-verify --yes -o 3.ogg   # one blind-test sample
"""

import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import click

API = "https://api.openai.com/v1"
MAX_CHARS = 3000  # the speech endpoint takes at most 2000 input tokens; 3000 chars stays under
WORDS_PER_MIN = 160  # measured: 159 to 165 wpm on three real episodes
SECTION_GAP_S = 2.5
PAUSE_DEFAULT_S = 2.0
OPUS_BITRATE = "16k"  # mono speech; in a blind test the author heard no difference from 64k MP3
MIN_MINUTES, WARN_MINUTES, MAX_MINUTES = 10, 20, 25
MAX_ASK_LINES = 4  # per section; more turns the asker into a co-host

KOKORO_MODEL = "Kokoro-82M 0.9.4"  # part of the chunk hash; change it when the weights or the package change
KOKORO_REPO = "hexgrad/Kokoro-82M"
KOKORO_RATE = 24000
KOKORO_TURN_GAP_S = 0.6  # Kokoro audio has tight edges; OpenAI chunks carry about 0.5 s of natural silence

# USD per minute of output audio, matched on the longest id prefix. A model without an entry
# here is never picked automatically: we cannot state its cost before spending.
PRICE_PER_MIN = {
    "gpt-4o-mini-tts": 0.015,
}
VERIFY_MODEL = "gpt-4o-mini-transcribe"
VERIFY_USD_PER_MIN = 0.003
LOCAL_VERIFY_MODEL = "base.en"  # faster-whisper int8 on CPU: about 50x real time, measured 2026-10-09
VERIFY_MIN_RATIO = 0.85  # word-sequence similarity between script chunk and its transcript

# Fallback voices when the config names none. These were the author's blind-test picks; yours may differ.
KOKORO_VOICE = "af_heart"  # female narrator
KOKORO_ASK_VOICE = "am_puck"  # male asker
OPENAI_VOICE = "marin"  # female narrator; OpenAI names marin and cedar as its best-quality voices
OPENAI_ASK_VOICE = "cedar"  # male asker

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "podcast-it" / "config.json"
DEFAULT_INSTRUCTIONS = (
    "You are a calm, warm, clear narrator of a personal podcast. "
    "The listener knows the field and is running, cleaning, or driving. Speak at a normal conversational pace, "
    "and finish each sentence cleanly before the next one. "
    "Leave a short natural pause at the end of each paragraph. "
    "Give a little weight to the one key idea in each paragraph. "
    "Sound like a knowledgeable friend explaining something over coffee, not like a newsreader. No dramatics."
)
DEFAULT_ASK_INSTRUCTIONS = (
    "You are the second voice of a personal podcast: a curious, thoughtful colleague. "
    "You only ask one short, direct question or say one short line. Speak a little slower than the narrator, "
    "evenly, with restrained curiosity. Lift the voice naturally on a question. "
    "Do not perform surprise, humour, or agreement."
)

PAUSE_RE = re.compile(r"^\[pause(?:\s+(\d+(?:\.\d+)?))?\]$")
ASK_RE = re.compile(r"^Q:\s*")
TAIL_RE = re.compile(r"^=== (NOTES|SOURCES) ===\s*$", re.MULTILINE)


@dataclass
class Item:
    kind: str  # "say" or "gap"
    text: str = ""
    role: str = "narrator"  # "narrator" or "ask"
    seconds: float = 0.0
    section: int = 0


def load_key() -> str:
    if key := os.environ.get("OPENAI_API_KEY"):
        return key
    raise click.ClickException("OPENAI_API_KEY is not set")


def load_config() -> dict:
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def price_of(model: str) -> float | None:
    matches = [p for p in PRICE_PER_MIN if model.startswith(p)]
    return PRICE_PER_MIN[max(matches, key=len)] if matches else None


def pick_model(key: str) -> tuple[str, list[str]]:
    """Newest speech model that takes style instructions and has a known price."""
    req = urllib.request.Request(f"{API}/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        models = json.load(r)["data"]
    # tts-1* takes no instructions; gpt-audio* and gpt-realtime* are not speech-endpoint models.
    tts = sorted(
        (m for m in models if "tts" in m["id"] and not m["id"].startswith("tts-1")),
        key=lambda m: m["created"],
        reverse=True,
    )
    notes = []
    for m in tts:
        if price_of(m["id"]) is not None:
            return m["id"], notes
        notes.append(f"NEWER MODEL WITHOUT PRICE: {m['id']} (add it to PRICE_PER_MIN to use it)")
    raise click.ClickException("no priced TTS model found in /v1/models")


def spoken_part(text: str) -> str:
    m = TAIL_RE.search(text)
    return text[: m.start()] if m else text


def notes_part(text: str) -> str:
    """The === NOTES === block, up to === SOURCES === or the end."""
    m = re.search(r"^=== NOTES ===\s*$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end() :]
    end = re.search(r"^=== SOURCES ===\s*$", rest, re.MULTILINE)
    return (rest[: end.start()] if end else rest).strip()


def parse(text: str) -> tuple[list[Item], list[str]]:
    """Script -> ordered items and the section titles (one per ## heading)."""
    items: list[Item] = []
    titles: list[str] = []
    for block in re.split(r"\n\s*\n", spoken_part(text)):
        block = " ".join(block.split())
        if not block:
            continue
        if block.startswith("#"):
            if items:
                items.append(Item("gap", seconds=SECTION_GAP_S, section=len(titles)))
            titles.append(block.lstrip("#").strip())
            continue
        section = max(len(titles) - 1, 0)
        if m := PAUSE_RE.match(block):
            items.append(Item("gap", seconds=float(m.group(1) or PAUSE_DEFAULT_S), section=section))
            continue
        role = "ask" if ASK_RE.match(block) else "narrator"
        clean = re.sub(r"[*_`]", "", ASK_RE.sub("", block))
        items.append(Item("say", clean, role, section=section))
    if not titles:
        titles = ["Episode"]
    return items, titles


def chunks(items: list[Item]) -> list[Item]:
    """Pack neighbouring paragraphs of one voice and one section into chunks of at most MAX_CHARS."""
    out: list[Item] = []
    for it in items:
        if it.kind == "say":
            if len(it.text) > MAX_CHARS:
                raise click.ClickException(f"paragraph longer than {MAX_CHARS} chars: {it.text[:80]}...")
            prev = out[-1] if out else None
            if (
                prev
                and prev.kind == "say"
                and prev.role == it.role
                and prev.section == it.section
                and len(prev.text) + 2 + len(it.text) <= MAX_CHARS
            ):
                prev.text = f"{prev.text}\n\n{it.text}"
                continue
        out.append(Item(it.kind, it.text, it.role, it.seconds, it.section))
    return out


def check(items: list[Item], titles: list[str], two_voices: bool) -> tuple[list[str], bool]:
    """Mechanical ear-checks. Returns report lines and whether any check FAILED."""
    spoken = " ".join(it.text for it in items if it.kind == "say")
    words = len(spoken.split())
    minutes = words / WORDS_PER_MIN + sum(it.seconds for it in items if it.kind == "gap") / 60
    sentences = [s for s in re.split(r"(?<=[.!?])[\"'”’)]*\s+", spoken) if s.strip()]
    long_ones = [s for s in sentences if len(s.split()) > 30]
    numbers = re.findall(r"\d[\d.,:/%]*", spoken)
    pauses = sum(1 for it in items if it.kind == "gap" and it.seconds != SECTION_GAP_S)
    rows: list[tuple[str, str, str]] = []

    def row(name: str, ok: bool, detail: str, warn_only: bool = False) -> None:
        rows.append(("PASS" if ok else ("WARN" if warn_only else "FAIL"), name, detail))

    row(
        "length",
        MIN_MINUTES <= minutes <= WARN_MINUTES,
        f"{minutes:.1f} min (target {MIN_MINUTES} to {WARN_MINUTES}, never above {MAX_MINUTES}; split into a series)",
        warn_only=minutes <= MAX_MINUTES,
    )
    per_min = len(numbers) / max(minutes, 1)
    row("numbers", per_min <= 1.0, f"{len(numbers)} numerals, {per_min:.1f} per min (max 1.0): {', '.join(numbers[:12])}", warn_only=per_min <= 2.0)
    avg = words / max(len(sentences), 1)
    row("sentence length", avg <= 18, f"average {avg:.1f} words (max 18)")
    row("long sentences", not long_ones, f"{len(long_ones)} over 30 words" + (f": {long_ones[0][:90]}..." if long_ones else ""), warn_only=len(long_ones) <= 3)
    row("pauses", pauses >= minutes / 3, f"{pauses} thinking pauses (at least one per 3 min)", warn_only=True)
    if two_voices:
        per_section = [sum(1 for it in items if it.kind == "say" and it.role == "ask" and it.section == s) for s in range(len(titles))]
        too_many = [titles[s] for s, n in enumerate(per_section) if n > MAX_ASK_LINES]
        none = [titles[s] for s, n in enumerate(per_section) if n == 0]
        row("asker lines", not too_many, f"max {MAX_ASK_LINES} Q: lines per section" + (f"; too many in: {', '.join(too_many)}" if too_many else ""))
        row("recall prompts", not none, "every section has a Q: line" + (f"; none in: {', '.join(none)}" if none else ""), warn_only=True)
    junk = re.findall(r"https?://\S+|www\.\S+|[\[\]{}<>|#\\]|\(|\)", spoken)
    row("unspeakable text", not junk, f"{len(junk)} URLs, brackets, or symbols" + (f": {' '.join(junk[:8])}" if junk else ""))
    caps = sorted(set(re.findall(r"\b[A-Z]{2,}s?\b", spoken)))
    row("acronyms", len(caps) <= 6, f"{len(caps)} distinct: {', '.join(caps[:15])}", warn_only=True)
    lines = [f"  {status:4}  {name:17} {detail}" for status, name, detail in rows]
    return lines, any(status == "FAIL" for status, _, _ in rows)


_kokoro: dict[str, object] = {}


def speak_kokoro(voice: str, text: str, path: Path) -> None:
    """Render with local Kokoro: each paragraph, then KOKORO_TURN_GAP_S of silence."""
    import numpy as np
    import soundfile as sf

    warnings.filterwarnings("ignore", module="torch")  # LSTM dropout and weight_norm notices from the Kokoro model
    from kokoro import KPipeline

    lang = voice[0]  # a = American English, b = British English
    if lang not in _kokoro:
        _kokoro[lang] = KPipeline(lang_code=lang, repo_id=KOKORO_REPO)
    gap = np.zeros(int(KOKORO_RATE * KOKORO_TURN_GAP_S), dtype=np.float32)
    parts = []
    for paragraph in text.split("\n\n"):
        parts += [a.numpy() if hasattr(a, "numpy") else a for _, _, a in _kokoro[lang](paragraph, voice=voice)]
        parts.append(gap)
    tmp = path.with_suffix(".tmp")
    sf.write(tmp, np.concatenate(parts), KOKORO_RATE, format="WAV", subtype="PCM_16")
    tmp.rename(path)


def speak(key: str, model: str, voice: str, instructions: str, text: str, path: Path) -> None:
    body = json.dumps({"model": model, "voice": voice, "input": text, "instructions": instructions, "response_format": "wav"}).encode()
    req = urllib.request.Request(
        f"{API}/audio/speech",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(r.read())
        tmp.rename(path)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout)


def silence(seconds: float, path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(seconds), str(path)],
        check=True,
    )


def words_of(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def similarity(expected: str, heard: str) -> float:
    return difflib.SequenceMatcher(None, words_of(expected), words_of(heard), autojunk=False).ratio()


def transcribe(client, path: Path) -> str:
    with path.open("rb") as f:
        return client.audio.transcriptions.create(model=VERIFY_MODEL, file=f, response_format="text")


def transcribe_local(model, path: Path) -> str:
    """faster-whisper on 16 kHz samples decoded by ffmpeg (its own PyAV decoder breaks on new av releases)."""
    import numpy as np

    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
        check=True,
    ).stdout
    segments, _ = model.transcribe(np.frombuffer(pcm, np.float32), language="en", beam_size=1, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments)


def chapters_metadata(titles: list[str], lengths: list[float]) -> str:
    """ffmetadata text with one chapter per section; times in milliseconds."""
    lines = [";FFMETADATA1"]
    start = 0.0
    for title, length in zip(titles, lengths, strict=True):
        clean = "".join("\\" + ch if ch in "=;#\\" else ch for ch in title)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(start * 1000)}", f"END={round((start + length) * 1000)}", f"title={clean}"]
        start += length
    return "\n".join(lines) + "\n"


@click.command()
@click.argument("script", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--out", type=click.Path(dir_okay=False, path_type=Path), help="Output .ogg, Opus at OPUS_BITRATE (default: <script>.ogg)")
@click.option("--engine", type=click.Choice(["kokoro", "openai"]), help="openai: paid API; kokoro: local and free (default: the config)")
@click.option("--voice", help=f"Narrator (default {OPENAI_VOICE} or {KOKORO_VOICE}). Kokoro female: af_heart, af_bella, bf_emma. OpenAI female: marin, coral, nova, shimmer, sage")
@click.option("--ask-voice", help=f"Voice for Q: lines (default {OPENAI_ASK_VOICE} or {KOKORO_ASK_VOICE}); 'none' reads them in the narrator voice")
@click.option("--instructions", default=DEFAULT_INSTRUCTIONS, help="Style instruction for the narrator (openai only)")
@click.option("--ask-instructions", default=DEFAULT_ASK_INSTRUCTIONS, help="Style instruction for the asker (openai only)")
@click.option("--model", help="Force an OpenAI model id (default: newest priced TTS model from /v1/models)")
@click.option("--max-usd", type=float, help="Refuse to render above this estimate (default: max_usd in the config, else 0.50)")
@click.option("--verify/--no-verify", default=True, show_default=True, help="Transcribe each chunk back and compare it with the script")
@click.option("--transcriber", type=click.Choice(["local", "openai"]), default="local", show_default=True, help=f"local: faster-whisper {LOCAL_VERIFY_MODEL} (free); openai: {VERIFY_MODEL} (paid)")
@click.option("--force", is_flag=True, help="Render even when a check FAILS")
@click.option("--yes", is_flag=True, help="Render (with --engine openai or --transcriber openai: spend). Without it this is a dry run")
def main(script, out, engine, voice, ask_voice, instructions, ask_instructions, model, max_usd, verify, transcriber, force, yes):
    out = out or script.with_suffix(".ogg")
    if out.suffix != ".ogg":
        raise click.BadParameter("the episode is Ogg Opus; name it <something>.ogg", param_hint="--out")
    config = load_config()
    engine = engine or config.get("engine")
    if engine not in ("kokoro", "openai"):
        raise click.ClickException(f"no engine chosen: run the setup in SKILL.md (it writes {CONFIG}), or pass --engine")
    max_usd = max_usd if max_usd is not None else float(config.get("max_usd", 0.5))
    kokoro = engine == "kokoro"
    # Configured voices belong to the configured engine; an --engine override falls back to that engine's defaults.
    same = engine == config.get("engine")
    voice = voice or (same and config.get("voice")) or (KOKORO_VOICE if kokoro else OPENAI_VOICE)
    ask_voice = ask_voice or (same and config.get("ask_voice")) or (KOKORO_ASK_VOICE if kokoro else OPENAI_ASK_VOICE)
    paid_verify = verify and transcriber == "openai"
    key = load_key() if not kokoro or paid_verify else ""
    notes: list[str] = []
    if kokoro:
        model, rate = KOKORO_MODEL, 0.0
        # Kokoro takes no style instructions; empty strings keep them out of the chunk hash.
        instructions = ask_instructions = ""
    else:
        if not model:
            model, notes = pick_model(key)
        rate = price_of(model)
        if rate is None:
            raise click.ClickException(f"no price known for {model}; add it to PRICE_PER_MIN first")
    two_voices = ask_voice != "none"
    voices = {"narrator": (voice, instructions), "ask": (ask_voice, ask_instructions) if two_voices else (voice, instructions)}

    items, titles = parse(script.read_text())
    report, failed = check(items, titles, two_voices)
    plan = chunks(items)
    words = sum(len(it.text.split()) for it in items if it.kind == "say")
    minutes = words / WORDS_PER_MIN + sum(it.seconds for it in items if it.kind == "gap") / 60
    cost = minutes * rate + (words / WORDS_PER_MIN * VERIFY_USD_PER_MIN if paid_verify else 0)
    verifier = (VERIFY_MODEL if paid_verify else f"faster-whisper {LOCAL_VERIFY_MODEL} (local)") if verify else ""
    click.echo(f"engine {engine}, model {model} (USD {rate}/min), narrator {voices['narrator'][0]}, asker {voices['ask'][0]}" + (f", verify with {verifier}" if verify else ""))
    for n in notes:
        click.echo(n)
    click.echo(f"{words} words, {sum(it.kind == 'say' for it in plan)} chunks, {len(titles)} chapters, about {minutes:.1f} min, cost about USD {cost:.2f}")
    click.echo("checks:")
    click.echo("\n".join(report))

    if not yes:
        for s, title in enumerate(titles):
            asks = sum(1 for it in plan if it.kind == "say" and it.section == s and it.role == "ask")
            click.echo(f"  chapter {s}: {title} ({asks} asker chunks)")
        click.echo("dry run: nothing rendered, no paid call made. Add --yes to render" + (" (paid)." if cost else " (free, local)."))
        return
    if failed and not force:
        raise click.ClickException("a check FAILED; fix the script or pass --force")
    if cost > max_usd:
        raise click.ClickException(f"estimate USD {cost:.2f} is above --max-usd {max_usd}")

    # Chunk audio stays next to the output, so a failed run resumes without rendering or paying twice.
    # The file name hashes everything that shapes the audio (engine included, so OpenAI and Kokoro
    # chunks never collide), so an edited chunk never reuses stale audio.
    parts_dir = out.with_suffix(".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)

    def path_of(i: int, it: Item) -> Path:
        if it.kind == "gap":
            return parts_dir / f"{i:03d}-gap-{it.seconds:g}.wav"
        v, ins = voices[it.role]
        gap = f"turn {KOKORO_TURN_GAP_S}" if kokoro else ""
        digest = hashlib.sha256("\0".join([engine, model, gap, v, ins, it.text]).encode()).hexdigest()[:12]
        return parts_dir / f"{i:03d}-{it.role}-{engine}-{v}-{digest}.wav"

    files = [path_of(i, it) for i, it in enumerate(plan)]
    todo: list[tuple[Item, Path]] = []
    for it, path in zip(plan, files, strict=True):
        if it.kind == "gap":
            silence(it.seconds, path)
        elif not (path.exists() and path.stat().st_size > 0):
            todo.append((it, path))
    click.echo(f"{sum(it.kind == 'say' for it in plan) - len(todo)} chunks already on disk, {len(todo)} to generate")

    def render(job: tuple[Item, Path]) -> None:
        it, path = job
        v, ins = voices[it.role]
        if kokoro:
            speak_kokoro(v, it.text, path)
        else:
            speak(key, model, v, ins, it.text, path)

    if kokoro:  # torch already uses every core, and KPipeline is not known to be thread-safe
        for job in todo:
            render(job)
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(render, todo))

    if verify:
        if paid_verify:
            from openai import OpenAI

            client = OpenAI(api_key=key)
            hear, workers = (lambda path: transcribe(client, path)), 4
        else:
            from faster_whisper import WhisperModel

            whisper = WhisperModel(LOCAL_VERIFY_MODEL, device="cpu", compute_type="int8")
            hear, workers = (lambda path: transcribe_local(whisper, path)), 1
        says = [(it, path) for it, path in zip(plan, files, strict=True) if it.kind == "say"]

        # Verdicts are cached per chunk file and transcriber, so a resumed run does not transcribe twice.
        def verdict(job: tuple[Item, Path]) -> tuple[Item, Path, float]:
            it, path = job
            cache = path.with_suffix(f".verify-{transcriber}.txt")
            heard = cache.read_text() if cache.exists() else hear(path)
            cache.write_text(heard)
            return it, path, similarity(it.text, heard)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(verdict, says))
        bad = [(it, path, r) for it, path, r in results if r < VERIFY_MIN_RATIO]
        worst = min((r for _, _, r in results), default=1.0)
        if kokoro:
            # Kokoro is deterministic: the same text gives the same audio, so a re-render cannot help.
            click.echo(f"verify: {len(says)} chunks, worst similarity {worst:.2f}, {len(bad)} below {VERIFY_MIN_RATIO} (Kokoro is deterministic, so no re-render)")
            for _, path, r in bad:
                click.echo(f"  MISMATCH {r:.2f}: {path.name}; listen to it, and reword the text if it is wrong")
        else:
            for it, path, r in bad:
                click.echo(f"  MISMATCH {r:.2f} in {path.name}: re-rendering once")
                path.with_suffix(f".verify-{transcriber}.txt").unlink(missing_ok=True)
                render((it, path))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                again = list(pool.map(verdict, [(it, path) for it, path, _ in bad]))
            still = [(path, r) for _, path, r in again if r < VERIFY_MIN_RATIO]
            click.echo(f"verify: {len(says)} chunks, worst similarity {worst:.2f}, {len(bad)} re-rendered, {len(still)} still below {VERIFY_MIN_RATIO}")
            for path, r in still:
                click.echo(f"  STILL MISMATCH {r:.2f}: {path.name}; listen to it before publishing")

    lengths = [0.0] * len(titles)
    for it, path in zip(plan, files, strict=True):
        lengths[it.section] += duration(path)
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{p.resolve()}'\n" for p in files))
        metadata = Path(tmp) / "chapters.txt"
        metadata.write_text(chapters_metadata(titles, lengths))
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(metadata),
             "-map", "0:a", "-map_chapters", "1", "-ac", "1", "-c:a", "libopus", "-b:a", OPUS_BITRATE, "-application", "voip", str(out)],
            check=True,
        )
    real = duration(out)
    speech = sum(duration(p) for it, p in zip(plan, files, strict=True) if it.kind == "say")
    click.echo(f"wrote {out}: {real / 60:.1f} min, {len(titles)} chapters, {words / max(speech / 60, 0.01):.0f} spoken words per min, about USD {real / 60 * rate:.2f} for TTS")


if __name__ == "__main__":
    main()
