---
name: genius-queue
description: >
  Capitalize on temporary access to a much smarter model. When you get a top-tier
  "genius" model for a while (a frontier trial, a temporarily-unlocked higher tier,
  a better harness — anything sharper than your day-to-day driver), this skill runs
  your highest-leverage backlog through it across many projects, then materializes
  the genius's plans/findings to disk so the cheaper day-to-day models can execute
  them later. It is the LOOP; the per-project unit of work lives in the
  `genius-check` skill. Use when: (1) the user says "/genius-queue", "genius queue",
  "run the genius queue", (2) "the smart model is back / available for a bit",
  (3) any time scarce access to a more capable model opens up and you want to extract
  maximum value. Scopes: the curated queue (Tier 0/1 deep work) and/or a checkup
  sweep over projects.
user_invocable: true
arg_description: "Optional: genius model id + scope, e.g. '/genius-queue', '/genius-queue checkup', '/genius-queue opus tier0', '/genius-queue all'"
author: Rutger de Knijf
version: 2.0.0
---

# genius-queue

Sometimes you get access to a much more capable model than the one you run
day-to-day. The window typically lasts a day or several days — enough time to **run
the whole batch in one go, then materialize the findings once at the end.** No
per-item checkpoint ceremony; just run it and collect.

This skill is the **loop**. The per-project review is a separate skill,
[`genius-check`](../genius-check/SKILL.md) — one source of truth for the review
prompt and output contract. `genius-queue` resolves the model, picks the scope, fans
the work out across many projects/queue items, and materializes results at the end.

The skill is model-agnostic — point it at whatever top-tier model is available
(a frontier trial alias when one exists, otherwise your highest tier).

## Core principles

1. **Leverage-first ordering.** Do the work that compounds first. Global
   instruction-layer fixes (Tier 0) lift every later session, including cheaper-model
   ones. Then high-stakes/gnarly items (Tier 1). Then breadth (the checkup sweep).
2. **Run, then materialize.** The window is long enough (a day or more) to run the
   whole batch before writing anything up. Each genius agent writes its own one
   artifact at the end of its run; the loop collects summaries and does the final
   write-up (queue update, task-tracker notes, highlights) once, after the batch — not
   per item. Don't build resume/checkpoint machinery for a window this size.
3. **Capture for the cheaper models.** Every genius output is a concrete, executable
   artifact (a plan, a redlined diff, a root-cause + fix) that your day-to-day models
   can act on later. The genius **thinks**; the cheaper models **execute** afterward.
4. **The genius runs in subagents.** The main session model can't change mid-run, so
   the genius thinks inside `Workflow`/`Agent` calls set to the genius model. The main
   thread orchestrates and writes up.

## The backlog (where work comes from)

- **A queue file** — a curated, prioritized list (Tier 0 global layer, Tier 1 gnarly
  problems with ready-to-paste prompts, Tier 3 checkup list, Skip list). This is the
  source of truth; read it first. Default location: `~/GENIUS_QUEUE.md` (override to
  wherever you keep it).
- **Optional: a task tracker.** If you mirror the queue into a task manager
  (e.g. a `genius` label/tag, each task's note holding the ready prompt + a pointer
  back to the queue file), read that too as the live backlog.
- If neither exists, rebuild the queue first — see "Rebuild".

## Step 1 — Resolve the genius model

- Default: the highest-capability model alias your harness exposes. Override from the
  invocation arg if the user names another (e.g. a frontier trial alias).
- The genius runs in subagents, so this must be a valid `model:` alias for
  Agent/Workflow calls.
- **Probe before fanning out.** Spawn ONE tiny agent set to the genius model (prompt
  "reply READY") and verify it returns. If it errors (model pulled / alias gone), tell
  the user and stop — don't silently fall back to a weaker model and waste the run.

## Step 2 — Pick scope

Map the arg (or a quick ask about window size) to a scope:

- **`tier0`** — global instruction layer (your global agent config, hooks/settings).
  Highest ROI; do this first if the window is short.
- **`tier1`** — the gnarly per-project problems (the deep queue items).
- **`checkup`** — the breadth sweep: one `genius-check` pass per stable project,
  "look the whole car over." Cheap, parallel, good for a medium/large window.
- **`all`** — Tier 0 → Tier 1 → checkup, in that order.
- Or a list of queue numbers / task ids / project paths.

Default if unspecified: **Tier 0 first, then down Tier 1 as far as the window allows**,
and offer the checkup sweep as the breadth option.

## Step 3 — Run the batch (one Workflow, no resume ceremony)

Fan the selected work out with `Workflow`, one `agent()` per item, set to the genius
model.

- **Checkup scope** — apply the `genius-check` review prompt to each project (see
  the template below). One agent per project, run in parallel.
- **Tier 0/1 deep items** — one agent per queue item, each fed that item's ready prompt
  (from the queue file / task) plus: "You are the genius model. Produce a concrete,
  executable artifact a weaker model can act on later — specific files, line refs,
  exact changes, test cases."
- Each agent **writes its own artifact** and returns a short summary. Deep items write
  `GENIUS-REVIEW-<topic>.md` in the project they concern (a global-config item writes a
  redlined config as `<file>.proposed` — never overwrite the live file). Checkup items
  write `GENIUS-CHECKUP.md` per project.
- Just let the batch run to completion. Window is long; no `resumeFromRunId` needed.

### Checkup-sweep workflow (prebuilt template)

The "look the whole car over" fan-out. Uses the same review prompt as `genius-check`.
Adapt the project list to the run.

```js
export const meta = {
  name: 'genius-check-sweep',
  description: 'Genius-model checkup pass over stable projects; one executable review each',
  phases: [{ title: 'Checkup' }],
}
// args = { model: 'opus', projects: ['/home/you/code/app-a', ...] }
const MODEL = (args && args.model) || 'opus'
const PROJECTS = (args && args.projects) || []
phase('Checkup')
const results = await parallel(PROJECTS.map(p => () =>
  agent(
    `You are the genius model — a brilliant engineer with 50 years of experience. ` +
    `READ-ONLY review of the project at ${p}. Read its CLAUDE.md/STATUS/README and ` +
    `skim the code. Judge it as a master would: working well? sound architecture? ` +
    `what's fragile, over-engineered, or quietly wrong? what latent bugs / security ` +
    `holes / data-loss risks / better designs does the day-to-day model keep missing? ` +
    `Be specific: exact files, line numbers, exact fixes, test ideas. ` +
    `WRITE your findings to ${p}/GENIUS-CHECKUP.md as a prioritized (P0→P3) executable ` +
    `list a weaker model can apply. Return ONLY a 3-line highlight summary.`,
    { label: `checkup:${p.split('/').pop()}`, phase: 'Checkup', model: MODEL }
  )
))
return results.filter(Boolean)
```

> Note: the highest-stakes items may be worth an **interactive** genius session
> instead of a hands-off agent — offer the user that choice. To go interactive they
> relaunch `cd <project> && claude --model <genius-model>` and paste the prompt; this
> skill still records the outcome afterward.

## Step 4 — Materialize once, at the end

After the whole batch finishes:

1. Collect every artifact path + summary. Write a single run summary into the queue
   file under a dated "## Runs" section: what got reviewed, where each artifact landed,
   what's still queued.
2. If you use a task tracker, post each genius output as a note/comment on its matching
   task (batch, at the end — not per item). **Leave tasks open** for the user to verify
   + complete.
3. Tell the user the highlights + the single most important thing the genius surfaced,
   and which artifacts are ready for a cheaper model to execute.

## Rebuild (if there's no queue yet)

If the queue file is missing, rebuild it before running: sweep your project directories,
read each `CLAUDE.md` + `STATUS`, gather git/activity signal, and sort into Tier 0
(global agent-config layer) / Tier 1 (gnarly, genius-worthy) / Tier 3 (checkup) / Skip.
Then go to Step 1.

## Guardrails

- **Never overwrite live config** with genius output — propose (`.proposed`/`GENIUS-*.md`),
  let the user apply.
- **Don't auto-complete tasks** or take any outward action (commits, sends, deploys)
  from genius output without the user's confirmation.
- **Verify the model is the genius tier** before spending the window (Step 1 probe). A
  pulled model silently downgrading defeats the entire purpose.
