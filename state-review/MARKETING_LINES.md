# Marketing Lines You Already Deserve

Things that are objectively true about this stack but that you're not using
in any public copy. Each one is defensible from a real benchmark or a real
architectural property — no marketing fluff.

---

## The three top lines

### 1. The memory line

> **"96.6% recall @5 on LongMemEval — top published result for a free local
> memory system."**

Defended by: `mempalace` raw-mode benchmark in your own README.
This is genuinely the strongest published result for a free local system.
It belongs in any place that talks about memory at all — gmux.ai homepage,
mempalace landing page, every demo intro, every README.

If you want a softer version: *"Beats the leading commercial memory systems
on the LongMemEval benchmark — running locally, free, no API."*

### 2. The provenance line

> **"Every claim hash-pinned to its source — no hallucinated citations."**

Defended by: the `Knowledge_systems` architecture. Other AI products say
"citations" and produce them by asking an LLM. You produce them from a
content-addressed store. That's a real position most competitors don't take.

Softer version: *"When the agent says 'here's the source', the source is
real and checkable, not generated."*

### 3. The wake-up line

> **"400-token agent wake-up — drops context cost ~90% vs naive prompt-loading."**

Defended by: the kalarc-memory protocol. Most agent systems either start
cold (lose context) or load megabytes of history (pay for tokens). 400
tokens is a specific, tested middle ground.

---

## Workspace-specific lines

### Composition lines

> **"Watch ten agents at once. Approve them by gesture. Talk to them by
> voice. No per-agent terminal switching."**

That's three input modalities + multi-agent visibility, which is unusual.

> **"Built on tmux. Bound to no API. Runs offline."**

Defended by: zero API dependencies in the backend. Voice, memory, models
all local. The mempalace memory is local. The Knowledge_systems graph is
local. The only thing that's optional/remote is the AI agents themselves
(opencode/claude/aider can be either local models or cloud).

### Specific feature lines

> **"Gesture-aware: pinch to scroll, swipe to switch, thumbs-up to approve."**

> **"Voice-first: faster-whisper STT, no cloud STT, no transcript leaves
> your machine."**

> **"Live data, not mock: monitor reads /proc/<pid>/cwd, polls OpenCode SSE,
> sums real token usage."**

---

## The "what makes this different" angles

These are the architectural positions worth taking publicly. Each is
defended by something concrete in the code.

### "Honest mock mode"

Most demos hide that they're showing fake data. The gmux demo shows a
banner the moment it can't reach a backend. *"Mock mode is labelled mock
mode."* — surprisingly rare.

### "Same code, every surface"

The browser UI, the Tauri desktop app, and the phone PWA are the same HTML
file. One bug fix, three places fixed. *"The UI is the same UI everywhere
— a single 300KB self-contained file."*

### "Per-agent context, automatically"

gmux-brain injects the right project memory into the right agent without
the human having to remember which agent gets which knowledge. The
research-batch comparison (jcode) has to do this manually. *"Every agent
boots into the project's context — automatically."*

### "Built where the work happens"

tmux is where developers already are. Most "AI workspace" products try to
replace the terminal. gmux **embeds in it**. That's a different positioning
choice from Cursor, Aider's web UI, or any IDE plugin.

### "Voice, gesture, keyboard — pick the one that's easiest right now"

Multi-modality isn't a gimmick when it's three modalities working in the
same UI. Voice for content, gesture for navigation, keyboard for precision.
The choice is the user's, frame by frame.

---

## Lines about specific projects

### `mempalace`

> "Free, local, faster than the cloud memory products, and the only one
> that publishes a benchmark."

> "Stores the full transcript. Recalls by meaning. Doesn't summarise the
> *why* away."

### `Knowledge_systems`

> "A claim graph, not a chatbot."

> "Every fact tied to a hash and a source. Versioned. Auditable."

### `kalarc-memory`

> "400 tokens is enough for an agent to wake up. Anything more and you're
> paying for context you don't need."

### `qalarc-voice`

> "300ms TTS. Local. Knows who's speaking."

### `claude_TUI` (Kalarc)

> "Voice-routed control plane. Phone-presence over Tailscale. Never leaves
> your network."

### The gesture suite

> "MediaPipe Hands, bidirectional: human hand controls the workspace, robot
> hand mirrors back. Same model both ways."

---

## What NOT to claim

Some things that *would* sound good but you can't currently defend:

- ❌ "Replaces your terminal" — gmux **augments** tmux, doesn't replace it
- ❌ "Self-improving" — no HALO loop yet
- ❌ "Long-horizon planning" — DeerFlow not integrated yet
- ❌ "Cross-platform desktop app" — Tauri release build not yet validated on
  macOS or Windows
- ❌ "Agent-quality scoring" — no ATLAS-style weighting yet

Save those for when they're true. The defended lines above are enough.

---

## The headline / sub-headline / CTA pattern

If gmux.ai needs a tighter pitch:

> **Headline:** Watch ten AI agents at once.
> **Sub:**     Voice control. Gesture control. Local memory. No API lock-in.
> **CTA:**     Try the demo →

Or longer-form:

> **Headline:** A workspace for the agent-multiplying era.
> **Sub:**     gmux gives you a single view of every AI agent you run,
>              with gesture/voice control and the most accurate local memory
>              system ever published.
> **CTA:**     See it run →

Both are defensible.

---

## Where each line maps to a project

| Line | Defended by | Public on… |
|---|---|---|
| 96.6% LongMemEval R@5 | mempalace README benchmark | mempalace.ai (if exists), gmux.ai, all mentions of memory |
| Every claim hash-pinned | Knowledge_systems architecture | Knowledge_systems README, gmux.ai about page |
| 400-token wake-up | kalarc-memory protocol | kalarc-memory README, agent context docs |
| Watch ten agents at once | gmux-system UI | gmux.ai homepage |
| No API lock-in | Backend dep tree (no cloud APIs required) | gmux.ai pricing/comparison page |
| Voice, gesture, keyboard | UI v3.x | gmux.ai feature grid |
| 300ms TTS | qalarc-voice benchmark | qalarc-voice README |
| Same UI everywhere | One HTML file → 3 surfaces | gmux.ai engineering page |

---

## The under-used summary

The single most under-used point: **you have all six layers of a serious
autonomous AI system at production-adjacent quality**. That itself is the
marketing line if the audience can value it:

> "Most AI assistants ship one of: memory, voice, gestures, or workspace.
> gmux ships all of them, locally, and they're built to compose."

Defensible. Specific. True. Currently un-published.
