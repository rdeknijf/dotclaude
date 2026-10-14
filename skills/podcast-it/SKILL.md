---
name: podcast-it
description: Turn a report, book notes, research, meeting notes, or any other body of information into a spoken episode on the user's own private podcast feed. Writes a script for the ear, renders it with a text-to-speech engine the user picked in a blind test (OpenAI TTS or local Kokoro-82M built in), checks the audio by transcribing it back, and adds it to a feed folder that a podcast app can subscribe to. Use when the user asks to turn something into audio, make a podcast or listen version, or put something on their feed.
---

# podcast-it

This skill turns material into an episode on the user's private podcast. Most of the work is the script: a report read aloud does not work by ear. Rendering and publishing are one command each. The story behind it, and why each rule is here: [Your to-read pile as a podcast](https://deknijf.com/posts/your-to-read-pile-as-a-podcast/).

All paths below are relative to the folder that holds this file. Scripts run with [uv](https://docs.astral.sh/uv/) (`uv run --script scripts/<name>.py`) and need `ffmpeg` on the PATH.

## Setup (once)

Do this the first time, and again when the user wants to reconsider the voice or the feed. Ask the user; do not pick for them.

1. **The listener file.** Write `~/.config/podcast-it/listener.md` with what you learn about the user as a listener: when they listen (running, driving, dishes), what they already know well, what they want simplified, which voice they find clearer. Read it before every episode. It also holds their own "Rules learned from listening" (see the end of this file), so updates of this skill never overwrite them.
2. **Find the current voices.** Text-to-speech changes fast, so search the web for the current best options. Include at least: the newest OpenAI speech model, ElevenLabs, Google's Gemini TTS, the top open-weights models on the [Artificial Analysis TTS leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard), and Kokoro-82M. Ask the user what they can use: an API key, a budget, a graphics card, and whether their text may leave their machine. Keep only the options that fit.
3. **Blind test, short.** Write a sample of about one minute in the episode format below (two voices, a `Q:` line, a technical term or two that they use daily). Render it with each option. `scripts/render.py` does OpenAI and Kokoro (`--engine`, `--voice`, `--no-verify --yes -o <name>.ogg`). For any other engine, write a few lines that call its API or local model, and save each sample under a name that says what it is (`elevenlabs-rachel.wav`). Then run `scripts/blind_test.py <samples> -o blind/`. The user listens to `1.ogg`, `2.ogg`, and so on, and ranks them before anyone opens `key.json`. `--reveal` prints the key.
4. **Blind test, long.** Short samples hide mistakes. Render one real episode of ten minutes or more with the top two, and let the user listen to both in full, in their real listening situation. A voice that ties on a sample can lose on an episode: every mispronounced word pulls the listener out of the subject. This costs a few cents with a paid engine; say the estimate first.
5. **Write the config.** `~/.config/podcast-it/config.json`:

   ```json
   {
     "engine": "openai",
     "voice": "marin",
     "ask_voice": "cedar",
     "max_usd": 0.5,
     "feed_dir": "~/podcast",
     "base_url": "https://podcast.example.com",
     "sync": "user@server:/srv/podcast/",
     "title": "My private podcast",
     "description": "Reports, research and books, read to me.",
     "author": "Me"
   }
   ```

   `engine` is `openai` or `kokoro`; a third engine needs its own speak function in `render.py` (copy `speak_kokoro` or `speak`). `max_usd` is the cost above which `render.py` refuses to render. `sync` is optional; leave it out when the folder goes to the phone instead (step 6).
6. **The feed.** Pick one of two ways with the user:
   - **A web server.** Any server that the phone can reach serves the feed folder as static files. Put basic auth on it (nginx `auth_basic` with an `htpasswd` file, or Caddy `basic_auth`); do not rely on a secret URL. Leave `art/` without the login, because some podcast apps do not send the login when they fetch images. In the podcast app, add the feed by URL (`<base_url>/feed.xml`) and turn on its authentication option.
   - **No server.** Sync the feed folder to the phone (Syncthing, a cable, a cloud drive) and add it in AntennaPod with "Add local folder". It reads the audio files directly.
7. **Pictures.** Give the feed a picture, and give each kind of source its own (for example `work`, `research`, `books`). Find public-domain art through the open-access APIs of the Metropolitan Museum or the Art Institute of Chicago, or on Wikimedia Commons. Pick works that match the source. Save each as a square JPEG of at least 1400 pixels in `<feed_dir>/art/` (`channel.jpg`, `<source>.jpg`), and write the title, artist, and source URL of each in `art/SOURCES.md`.

## Procedure (each episode)

1. Read `listener.md`. Then read the source in full. Write down the three to five points that matter to the listener, and why they matter now. Everything else is a candidate to cut.
2. Pick a work folder outside any git repository, for example `~/podcast-work/<YYYY-MM-DD>-<slug>/`.
3. Write `script.md` with the structure and the rules below. After the spoken part, put the companion text (numbers, names, identifiers, links, the full question list) under `=== NOTES ===`, and source notes under `=== SOURCES ===`. Neither part is spoken.
4. Optional, for material that matters: use two writers and a fact check (see below).
5. Run the dry run. It renders nothing and makes no paid call:

   ```bash
   uv run --script scripts/render.py script.md -o episode.ogg
   ```

   It prints the engine, the two voices, the minutes, the cost, the chapters, and the ear checks. Fix every `FAIL`. Read every `WARN` and fix it unless you can say why it is right for this episode.
6. Read the script once more as the listener: on a run, half attentive, topic forgotten. Remove every sentence that the listener must hold in memory to understand a later sentence.
7. With a paid engine, follow the user's spending rule. Unless they gave a standing approval for estimates under a limit, ask once: title, a three-line outline, the minutes, and the estimated cost.
8. Render with `--yes`. The script refuses a script with a `FAIL`, and an estimate above `max_usd`. A failed run resumes from the chunk files in `episode.parts/` without rendering or paying twice. After the render, every chunk is transcribed back locally and compared with the script. With OpenAI, a mismatch is rendered again once; Kokoro gives the same audio for the same text, so a Kokoro mismatch is only reported. Listen to every chunk that the output names as `MISMATCH` or `STILL MISMATCH` before you publish. A name that the transcriber spells another way also gives a mismatch, so listen before you change the text. Each `##` heading becomes a chapter.
9. Publish. Do the dry run first, then the real run:

   ```bash
   uv run --script scripts/publish.py episode.ogg <slug> "<title>" "<description>" --source <source> --notes script.md --dry-run
   uv run --script scripts/publish.py episode.ogg <slug> "<title>" "<description>" --source <source> --notes script.md
   ```

   Then check that `feed.xml` lists the slug. When the feed is on a server, fetch `<base_url>/feed.xml` with the login and look for it there.
10. Report in one or two lines: title, minutes, real cost, and where it is.

## Two writers and a fact check (optional)

For material that matters, do not let one model write the script. Use this step only when the user has access to strong models from two different companies, for example Claude and GPT through their coding harnesses or APIs.

1. Give both models the same sources, `listener.md`, and this file, and let each write its own `script.md` with reasoning on. Run the second one from the other harness, for example `codex exec` from Claude Code or `claude -p` from Codex.
2. A third pass merges the two: keep the strongest case and the clearest order from either draft, and keep the rules below.
3. A fact check reads the merged script against the sources, claim by claim. Every claim keeps its source under `=== SOURCES ===`. Remove or fix every claim that the sources do not support.

## Script structure

- **Two voices with fixed roles.** The narrator gives every fact. The asker speaks only in paragraphs that start with `Q:`. The asker may only: ask the short why, how, or so-what question a listener would ask; give the recall question at the end of a section; or say the "so what for you" line. The asker never adds a fact, never greets, never banters, and has at most four lines per section. (R: overheard deep questions improve recall; banter does not.)
- **Cold open.** First paragraph: one concrete case or scene that ends on the question the episode answers. Then the reason it matters to the listener now. No "welcome to the show".
- **Give the map.** Next paragraph: "This episode has three parts: A, B, and C." Never more than five parts. In a series, first a 60-second "previously" in recall form: the asker asks two or three questions about earlier episodes, a `[pause]`, then the narrator answers.
- **Each section has a fixed shape, at most about 450 spoken words (3 to 4 minutes).** Start it with a `## Heading` (not spoken; it becomes the chapter title, so make it short and specific). Then:
  1. The question this section answers, often as a `Q:` line. Never a teaser such as "you won't believe".
  2. One concrete case, person, or event that shows the mechanism.
  3. The principle in one sentence ("What this tells us is ...").
  4. What it means for the listener.
  5. The recall question as a `Q:` line, then `[pause]`, then the answer in one sentence in other words.
- **Spoken signposts.** Open a section with where we are on the map ("Part two of four: ..."). Do not refer to "what I said" earlier; restate a fact in one sentence instead.
- **Close with the takeaways.** Three to five points, one sentence each. The ending adds no new claim, only restates. If there is an action for the listener, say it last.
- **Length: 10 to 20 minutes.** With more material, split into a numbered series of episodes on one theme each ("part one of two"). Never speed up the narration to fit.
- **One narrator only** when the user asks for it: render with `--ask-voice none`; the `Q:` lines are then read by the narrator.

The script format that `render.py` reads:

```text
## Heading        starts a new section and chapter; 2.5 s of silence before it
Q: text           a paragraph for the asker; every other paragraph is the narrator
[pause]           on its own line: 2 s of silence
[pause 3]         on its own line: 3 s of silence
=== NOTES ===     companion text for the episode notes (publish.py --notes); not spoken
=== SOURCES ===   source notes for the editor; not spoken
```

## Writing rules

Most of these are broadcast practice (BBC, NPR, AP style for radio). Research backs the rules on pace, pauses at clause ends, segmenting, and removing extra material (marked R). Ranked by effect:

1. One idea per sentence. Most sentences 8 to 15 words; never above 25.
2. Subject first, then the verb, active voice. Give the source before the claim: "Gottman found that ...", not "..., Gottman found."
3. No parentheses, asides, or nested clauses. Make an aside its own sentence, or delete it.
4. Numbers: at most one per paragraph, and only when it is the point. Round it and write it as speech ("about a third", "more than five hundred"). Better: a comparison ("twice as long as a marathon"). Drop identifiers completely: ticket keys, versions, dates that do not matter. (R: listeners hold about seven digits.)
5. One term for one thing. A new word sounds like a new concept to a listener. Do not vary words for style.
6. Say an acronym in full on first use, then the short form. Drop acronyms that the listener does not need.
7. Give every abstract claim one concrete example, story, or analogy. Prefer things from the listener's own life (see `listener.md`).
8. Repeat on purpose: say the point, explain it, say it again in other words. On paper this is redundant; by ear it is how the point sticks.
9. Announce lists by count first ("there are three reasons"), then give them as sentences. No bullet lists, no tables.
10. Use contractions and everyday words. Write what a knowledgeable friend would say aloud. No rhetorical questions: every question is a real one, put as a `Q:` line, and the episode answers it within a few minutes.
11. Put a `[pause]` after every recall question and after every point that the listener needs to think about, and at least one every three minutes. Never put two new ideas between two pauses. Use `[pause 3]` after the heaviest point of the episode. Pauses go at the end of a paragraph, never mid-sentence. (R: pauses at sentence and clause ends restore recall.)
12. Spoken forms only: no URLs, no symbols, no markdown inside paragraphs, no `e.g.`. Spell out what TTS reads badly ("C sharp", "version two point five"). Write names as they are pronounced when TTS may get them wrong.
13. Cut everything that does not serve one of the three to five points. (R: removing extra material improves learning.)
14. Pace is set by the script, not by the voice: fewer ideas per minute, short sentences, and real pauses. The voice speaks at a normal conversational pace. (R: recall was best at about 170 to 190 words per minute with few ideas, worse at a slow pace with dense content.) The render prints the measured spoken words per minute.
15. Story carries the point: explain a mechanism through one case first, then the principle. Cut an anecdote that does not carry the point, however interesting. (R: interesting but irrelevant details hurt learning.)
16. No music or sound effects under the speech. Silence is the sound cue between sections.

## Engines, voices, and cost

- **OpenAI** (`engine: openai`, needs `OPENAI_API_KEY`). `render.py` asks `GET /v1/models` (free) and picks the newest speech model that takes style instructions and has a known price in `PRICE_PER_MIN`. When OpenAI ships a newer model, the dry run names it as `NEWER MODEL WITHOUT PRICE`; look up its price and add it. In October 2026, `gpt-4o-mini-tts` cost about USD 0.015 per minute, so a 20-minute episode costs about USD 0.30. OpenAI names `marin` and `cedar` as its best voices. Style instructions (`--instructions`, `--ask-instructions`) shape the delivery.
- **Kokoro-82M** (`engine: kokoro`). Runs on a normal CPU, about four times faster than real time, costs nothing, and needs no key; after the first download it works offline. It takes no style instructions. Voices that start with `a` are American English, `b` British; `f` is female, `m` male (`af_heart`, `am_puck`, `bf_emma`). Kokoro sends unknown words to espeak-ng, which often guesses wrong, and it can put the stress wrong across a phrase ("pull request" with the stress on "request"). A word list does not fix that.
- **Audio check.** faster-whisper `base.en` on the CPU, free, about 50 times faster than real time. `--transcriber openai` uses `gpt-4o-mini-transcribe` instead (paid). `--no-verify` skips the check.
- **Audio format.** Ogg Opus at 16 kbps mono: about 120 KB per minute. In a blind test the author heard no difference from MP3 at 64 kbps, which is four times the size.
- **First run.** `render.py` pins Python 3.12 (Kokoro does not install on 3.13 or later) and downloads Kokoro, faster-whisper, and a spaCy model even when you use OpenAI. That happens once.

## Rules learned from listening

When the user gives feedback on an episode, add one dated line to the same section in `listener.md`, and follow it over the rules above when they conflict.

The author's own lines, as a start:

- Numbers and pipeline details were useless on a run. Keep the audio version free of identifiers.
- Early episodes felt like a waterfall of words, with no time to store a point. Hence rules 8 and 11 and the fixed section shape.
- A male and a female voice help, but as roles (narrator and asker), not as voices that take turns per section.
- Short blind samples said a free model matched the paid one; full-length episodes said it did not. Judge a voice on a long episode, not on a sample.
