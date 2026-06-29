# State Review — November 2026

A snapshot of where the autonomous-AI stack actually is, written when it
became clear that the system is closer to ready than the day-to-day work
makes it feel.

## What's in here

| File | What it covers |
|---|---|
| `STATE_OF_THE_STACK.md` | The 6-stack composition — what each layer does, how mature it is, the rare-in-public observation that *you have all six* |
| `DEPLOY_STATUS.md` | Honest deploy state: what runs, what installs cleanly, what's blocked on Tauri reliability, what works on the VM |
| `WHAT_TO_SHIP.md` | The "stop iterating, ship the thing" list. Growth features vs ship blockers, separated honestly |
| `MARKETING_LINES.md` | Lines you already deserve to use but aren't (96.6% LongMemEval, "every claim hash-pinned", 400-token wake-up) |
| `COMPOSITION_GAPS.md` | The stitching-not-building work. Most remaining wins come from formal composition, not new components |

## Why this folder exists

The catalyst was a clear outside read of the stack:

> Stacks 1–6 of `AI_SYSTEMS_GUIDE.md` cover every layer of a serious agentic
> system: workspace (gmux), memory (mempalace + Knowledge_systems +
> kalarc-memory), voice (qalarc-voice), control (claude_TUI), substrate
> (local-models on 96GB APU), gestures (gesture-control suite). The only
> architectural gap is **long-horizon harness above all of it**, and
> DeerFlow exists.

That's an unusually concentrated lineup and it deserves its own honest
status doc rather than being implicit across a dozen READMEs.

## How to read it

1. Start with `STATE_OF_THE_STACK.md` for the picture
2. Then `DEPLOY_STATUS.md` for the realistic install/deploy answer
3. Then `WHAT_TO_SHIP.md` for the ship-now list
4. `MARKETING_LINES.md` and `COMPOSITION_GAPS.md` are reference

## Source documents this review builds on

- `~/projects/github_repos/research_2026_05/AI_SYSTEMS_GUIDE.md` — the
  outside framing that triggered this folder
- `~/projects/gmux/gmux_development/DECISIONS.md` — gmux-internal
  architecture decisions and what's locked in
- `~/projects/gmux-system/HANDOVER.md` — current gmux-system state
- `~/projects/gmux-system/DEPLOYMENT_TARGETS.md` — per-OS matrix
- `~/projects/gmux-system/DEPENDENCIES.md` — exact dep tree
- `~/projects/gmux-system/docs/VM_DEPLOYMENT_LOG.md` — the real VM run
