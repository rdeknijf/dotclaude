# dotclaude

Skills for any agent harness: [Claude Code](https://claude.com/claude-code),
[Codex](https://developers.openai.com/codex), or anything else that reads
`SKILL.md` files. They're the bits of my own setup worth sharing.

It's a hand-picked mirror, not a sync. Everything here is scrubbed of private
paths, project names, and secrets.

## Skills

| Skill | What it does |
|-------|--------------|
| [`genius-check`](skills/genius-check/SKILL.md) | One brilliant pass over **one** project. The genius reviews it read-only and writes a prioritized, executable `GENIUS-CHECKUP.md` a weaker model can act on later. The reusable unit. |
| [`genius-queue`](skills/genius-queue/SKILL.md) | The **loop**. Runs your highest-leverage backlog (global instruction-layer fixes, then gnarly per-project problems, then a breadth checkup sweep) through the genius across many projects, then materializes every plan to disk in one pass at the end. |
| [`humanizer`](skills/humanizer/SKILL.md) | Strips the tells of AI-generated prose — inflated significance, promotional language, em-dash overuse, rule-of-three, hedging, and 30-odd more patterns drawn from Wikipedia's "Signs of AI writing" guide. Edits your text in place so it reads like a person wrote it. |
| [`podcast-it`](skills/podcast-it/SKILL.md) | Turns a report, research, meeting notes or a book into an episode on your own private podcast. Writes a script for the ear, renders it with a voice you picked in a blind test, checks the audio, and adds it to a feed your podcast app can subscribe to. Background: [Your to-read pile as a podcast](https://deknijf.com/posts/your-to-read-pile-as-a-podcast/). |

The genius skills exist to solve one problem. You occasionally get temporary
access to a much smarter model (a frontier trial, a temporarily-unlocked higher
tier, a better harness), and the window closes before you've extracted its value.
The genius model should *think*; your cheaper day-to-day models should *execute* its
plans afterward. The skills turn that into a routine: leverage-first ordering, run
the whole batch then materialize once, every output a concrete artifact a weaker
model runs later. Reviews are read-only; proposals are `.proposed` / `GENIUS-*.md`
files, so nothing outward-facing happens without you. Both are model-agnostic; only
the model alias changes.

## Install

Easiest: point your agent at this repo and let it do the work. Better still, let
it read a skill and build a version that fits you. Something like:

> Read https://github.com/rdeknijf/dotclaude and install the skills I want
> (`genius-check`, `genius-queue`, `humanizer`) into my setup, wherever makes
> sense for me (global `~/.claude/skills/`, or this project). For the genius
> skills, adapt the genius-model alias to whatever top-tier model I actually have.

Or, for the podcast skill:

> Read https://github.com/rdeknijf/dotclaude/tree/main/skills/podcast-it and
> https://deknijf.com/posts/your-to-read-pile-as-a-podcast/, then set the skill up for
> me. Do the setup steps with me.

It reads the `SKILL.md` files, drops them where your harness looks for skills, and
fixes up what needs fixing. That's the point of shipping them as plain,
self-describing markdown.

Prefer to do it by hand? Copy a skill folder to where your harness looks for skills:

```bash
git clone https://github.com/rdeknijf/dotclaude.git
cp -r dotclaude/skills/* ~/.claude/skills/   # Claude Code (or pick single skill folders)
cp -r dotclaude/skills/* ~/.agents/skills/   # Codex
```

In Claude Code, invoke a skill with `/podcast-it`, `/humanizer` or `/genius-check <path>`.
Codex and other harnesses pick a skill by its description, or when you name it.

## License

[MIT](LICENSE)
