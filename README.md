# dotclaude

My curated, publicly shareable [Claude Code](https://claude.com/claude-code)
config: the bits of `~/.claude` worth sharing. Skills today; custom commands,
agents, hooks, statusline, and sanitized settings as I clean more up.

It's a hand-picked mirror of `~/.claude`, not a sync. Everything here is scrubbed
of private paths, project names, and secrets. Structure mirrors the real thing, so
installing is just copying the pieces you want into your own `~/.claude/`.

## Skills

| Skill | What it does |
|-------|--------------|
| [`genius-check`](skills/genius-check/SKILL.md) | One brilliant pass over **one** project. The genius reviews it read-only and writes a prioritized, executable `GENIUS-CHECKUP.md` a weaker model can act on later. The reusable unit. |
| [`genius-queue`](skills/genius-queue/SKILL.md) | The **loop**. Runs your highest-leverage backlog (global instruction-layer fixes, then gnarly per-project problems, then a breadth checkup sweep) through the genius across many projects, then materializes every plan to disk in one pass at the end. |
| [`humanizer`](skills/humanizer/SKILL.md) | Strips the tells of AI-generated prose — inflated significance, promotional language, em-dash overuse, rule-of-three, hedging, and 30-odd more patterns drawn from Wikipedia's "Signs of AI writing" guide. Edits your text in place so it reads like a person wrote it. |

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

Easiest: point your agent at this repo and let it do the work. Something like:

> Read https://github.com/rdeknijf/dotclaude and install the skills I want
> (`genius-check`, `genius-queue`, `humanizer`) into my setup, wherever makes
> sense for me (global `~/.claude/skills/`, or this project). For the genius
> skills, adapt the genius-model alias to whatever top-tier model I actually have.

It reads the `SKILL.md` files, drops them where your harness looks for skills, and
fixes up the model alias for you. That's the point of shipping them as plain,
self-describing markdown.

Prefer to do it by hand? Everything mirrors `~/.claude/`, so just copy what you want:

```bash
git clone https://github.com/rdeknijf/dotclaude.git
cp -r dotclaude/skills/* ~/.claude/skills/   # or pick individual skill dirs
```

Either way, invoke them in Claude Code with `/genius-check <path>`, `/genius-queue`,
or `/humanizer`.

## License

[MIT](LICENSE)
