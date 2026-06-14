---
name: genius-check
description: >
  Deep review of ONE project by the most capable "genius" model you currently
  have access to. The genius reads the project, thinks like a 50-years-experience
  engineer, and writes a concrete, prioritized, executable findings file that your
  cheaper day-to-day models can act on later. This is the unit of work; the
  `genius-queue` skill loops it over many projects. Use when: (1) the user says
  "/genius-check <path>", "genius check", "genius checkup", "have the smart model
  look over <project>", (2) you want one brilliant pass over a single codebase.
user_invocable: true
arg_description: "Project path (defaults to cwd), optional genius model id. e.g. '/genius-check ~/code/myapp', '/genius-check . opus'"
author: Rutger de Knijf
version: 1.0.0
---

# genius-check

One brilliant pass over **one project**. The genius model does the thinking; the
output is an executable artifact a weaker model runs later. This is the reusable
unit — `genius-queue` calls it in a loop; you can also run it standalone on a
single project.

Point it at whatever top-tier model you currently have: a frontier model on a
temporary trial, your highest-effort tier, a better harness — whatever is
sharper than your day-to-day driver. The skill is model-agnostic; only the model
alias in Step 1 changes.

## Why a separate skill

The per-project review prompt and procedure live here so there's **one source of
truth**. Both standalone runs and the `genius-queue` sweep use the same prompt and
the same output contract, so results are comparable across projects.

## Step 1 — Resolve inputs

- **Project path**: from the arg; default to the current working directory.
- **Genius model**: from the arg; default to the highest-capability model alias
  your harness exposes (e.g. `opus`, or a frontier alias like `fable` when a
  trial model is temporarily available). The genius runs in subagents — the main
  session model can't change mid-run — so this must be a valid `model:` alias for
  Agent/Workflow calls.

## Step 2 — Run one genius agent over the project

Spawn a single subagent set to the genius model (genius runs in subagents — the
main session model can't change mid-run). Feed it the **canonical review prompt**
below. The agent reads, thinks, and **writes the artifact itself**, returning only
a short highlight summary to keep the main thread light.

### Canonical review prompt

> You are the genius model — a brilliant engineer with 50 years of experience across
> architecture, security, performance, and operations. READ-ONLY review of the project
> at `<PROJECT_PATH>`.
>
> 1. Read its `CLAUDE.md`, `STATUS.md`, `README`, and skim the actual code and config.
> 2. Judge it the way a master would on first contact: Is this working well? Is the
>    architecture sound? What's fragile, over-engineered, or quietly wrong? What latent
>    bugs, security holes, data-loss risks, or better designs does the day-to-day model
>    keep missing here?
> 3. Be specific and actionable. Reference exact files and line numbers. Give exact
>    changes, not vague advice. Where useful, sketch the diff or the test that proves it.
>
> WRITE your findings to `<PROJECT_PATH>/GENIUS-CHECKUP.md` as a prioritized, executable
> list (P0 must-fix → P3 nice-to-have), each item: what, where (file:line), why it
> matters, and the concrete fix a weaker model can apply. This file is the deliverable.
>
> Return ONLY a 3-line highlight summary: the single most important finding, the count
> by priority, and whether anything is urgent.

## Step 3 — Report

Surface the agent's 3-line summary and the path to `GENIUS-CHECKUP.md`. Don't act on
the findings automatically — they're a plan for a later (cheaper-model) session to
execute.

## Guardrails

- **Read-only review.** The genius proposes; it does not edit live code or config.
  The only file it writes is `GENIUS-CHECKUP.md` (the findings artifact).
- **Never overwrite live config** with genius output — findings are proposals.
- **Verify the model is the genius tier** before spending it. If the genius model
  probe errors (model pulled / alias gone), say so and stop — don't silently
  downgrade to a weaker model.
