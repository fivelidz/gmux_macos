# gmux alpha.22 — Orchestration Features & Marketing Log

_Round date: 2026-06-16. This logs every feature added in the
"frictionless creation → supervisor loops → rate-limit intelligence →
audio alerts → scheduling" arc, for marketing copy and a public write-up._

---

## The one-line pitch

> **gmux is the cockpit for running a *fleet* of AI coding agents — it keeps
> them moving, keeps them under the rate limit, and tells you (out loud) when
> one needs you.**

Most "agent" tools run one agent. gmux runs many, in one session, and adds the
layer nobody else has: **fleet coordination** — supervision loops, a
rate-limit-aware concurrency governor, scheduled launches, and audible alerts.

---

## Features shipped this round

### 1. Frictionless agent creation (the composer)
- Press **N** → the chat panel *becomes* the creation surface. An info bar
  shows agent / model / permission / folder, **all preselected** from your
  last-used defaults. Type a prompt, hit Enter — that's the whole flow.
- No "Create" button, no modal wall of options. The full dialog is still one
  keystroke away (**Shift+N**) for power users.
- Typing into a dead/empty pane rolls you straight into the composer with your
  text carried over.

**Marketing line:**
> *"Starting an agent is one keystroke and a sentence. Everything else is
> remembered."*

### 2. Permissions that actually apply — and that sub-agents inherit
- The safe / yolo / yolo-extreme choice is now wired end-to-end into the agent
  launch (`opencode --agent yolo`, `claude --dangerously-skip-permissions`,
  etc.). Previously it was computed and silently dropped.
- **Sub-agents inherit their parent's permission mode** automatically — a yolo
  parent spawns yolo children with no re-prompt. The mode survives app
  restarts.

**Marketing line:**
> *"Set the trust level once. Every agent and every sub-agent it spawns honours
> it — no babysitting permission prompts."*

### 3. Looping / supervisor agents ♻️
- At creation, tick **"Looping / supervisor agent"**. That agent gets a
  distinct dashed-teal panel and a `♻️ super` badge.
- Its job: **keep the work going.** When a worker agent in the session stalls
  (goes ready/idle/done), the supervisor reacts in one of two modes:
  - **Re-prompt** — sends a "continue with your tasks" nudge into the stalled
    worker's terminal so it picks up the next item.
  - **Notify** — POSTs a JSON event to a URL you set (webhook → phone, Slack,
    email, your own API) so a human gets pinged.
- Loop caps and per-worker cooldowns stop runaway nudging.

**Marketing line:**
> *"A supervisor agent that watches the others and keeps them working — or taps
> you on the shoulder when they're truly stuck. Autonomy with a safety rail."*

### 4. Smart concurrency governor ⚖️ (rate-limit intelligence)
The hard part of multi-agent work: **per-minute rate limits.** Run 4 agents and
they trip Anthropic's RPM/TPM buckets; naive "restart everything" loops just
re-trip them instantly. gmux's governor:
- Watches fleet-wide rate-limit hits and runs an **AIMD budget** (TCP-congestion
  style): +1 safe-concurrency per clean 60s, **halve on a 429**.
- **Staggers (re)starts and supervisor nudges** with decorrelated jitter so a
  batch of agents never all fire in the same second.
- Shows a **green / amber / red lamp** in the topbar: *"safe to add an agent?"*

Designed from a full research brief in `docs/RATE_LIMIT_DETECTION_DESIGN.md`.

**Marketing lines:**
> *"gmux runs your agents like TCP runs the internet — it backs off when it's
> hot and ramps up when it's clear, so you stop tripping the per-minute limit
> you couldn't even see before."*
>
> *"A traffic light for concurrency: green means add another agent, red means
> hold."*

### 5. Scheduled sessions & task timers ⏰
- Set a time of day to **launch an agent automatically** — e.g. fire a warm-up
  agent at 8:55am so your **5-hour Claude window starts before you sit down.**
- Optional prompt (run an actual task) or blank (just warm the session).
- Recurrence: once / daily / weekdays. Scheduled launches go through the same
  staggering governor so a batch of timers doesn't trip the minute limit.

**Marketing line:**
> *"Schedule your 5-hour window to start before you do. Walk in to a warm
> session and agents already on the job."*

### 6. Audible attention alerts 🚂
- A synthesised alert (no sound files shipped) plays when **any agent needs
  you** — finished, awaiting permission, errored, or rate-limited.
- Toggle on/off; pick the sound. **Default is a train whistle**; also chime,
  ding, bell, beep — with a one-click Test button.

**Marketing line:**
> *"Look away from the fleet. gmux whistles when an agent needs you."*

---

## Why this matters (positioning)

| Everyone else | gmux |
|---|---|
| One agent in a terminal | A *fleet* in one cockpit |
| You watch it | A supervisor agent watches it; gmux whistles for you |
| Hit invisible rate limits | A governor that sees them and backs off intelligently |
| Manual restarts that re-trip limits | Staggered, jittered, AIMD-aware restarts |
| Start cold when you sit down | Scheduled warm-ups before you arrive |

**The category line:**
> *"Not an agent. An agent **operations centre**."*

---

## Honest caveats (for an accurate write-up)
- Rate-limit detection on the **OAuth/subscription** path is signal-based (PTY
  text + the existing 5h/7d usage bars) — true per-minute headers need the
  API-key path or the planned local proxy (Phase 2 in the design doc).
- The governor's budget is an **adaptive estimate**, not a hard quota read from
  the API. It's conservative by design (halve-on-hit), which is the safe error.
- Supervisor "understanding the project" is as good as the underlying model —
  the loop drives continuation, it doesn't add reasoning the agent lacks.

---

## Where the code lives (for the write-up / future agents)
- All UI + logic: `app/src/index.html` (search `alpha.22`).
- Audio engine: `playAlertSound` / `_soundRecipe`.
- State-change detection: `_gmuxScanStateChanges` (hooked in
  `applyRealStateExtras`).
- Supervisor: `_supervisorOnStateChange` / `_supervisorNudge` / `_supervisorNotify`.
- Governor: `window._gov`, `_governorTick`, `_governorStaggerDelay`,
  `_governorOnRateLimit`, `_governorSignal`.
- Scheduler: `addSchedule` / `_scheduleTick` / `_fireSchedule`.
- Permission wiring (Rust): `app/src-tauri/src/lib.rs` →
  `build_agent_start_cmd_v4`, `open_agent_v4`, `spawn_sub_agent_v4`.
- Research: `docs/RATE_LIMIT_DETECTION_DESIGN.md`.
