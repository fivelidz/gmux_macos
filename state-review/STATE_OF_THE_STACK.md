# State of the Stack — November 2026

## The picture in one paragraph

You have all six layers of a serious autonomous AI system: a multi-agent
workspace (gmux), an episodic memory with state-of-the-art retrieval
(mempalace), a citable knowledge graph (Knowledge_systems), a project-local
handoff layer (kalarc-memory), a voice surface with speaker ID (qalarc-voice),
and a voice-routed control plane with phone presence (claude_TUI). On top of
that there's a gesture-control suite and a 96 GB local-models substrate. The
external research batch identifies one architectural gap — a long-horizon
harness — and **DeerFlow already exists** as the reference for it.

Most people building "AI assistants" have one or two of these layers. The
remarkable property of this stack is that you have all six at
production-adjacent quality.

---

## The six stacks, mapped to projects

### 1. Workspace — `gmux` + `gmux-brain` + `gmux-system` + `gmuxtest`

**What it does:** Lets a human supervise multiple AI agents running in tmux
panes, see their state at a glance, swap between them, approve/reject
permission prompts, send chat by voice or keyboard.

**Where it stands:**
- 14 panes / 5 sessions live in monitor right now
- Backend daemon (`monitor.py`) is rock-solid — psutil RAM/CPU/uptime,
  per-pane OpenCode SSE subscription, REST aggregation for tokens/cost/model,
  HTTP + SSE on `:8769`, voice WS on `:8770`
- Browser UI is v3.4 — markdown chat, click-to-rename themes, transparent
  options overlay, memory-panel stub, accurate per-pane todos
- Tauri app boots, mirrors PTY, autospawns sidecars, but is laggy in dev
  mode (WebKitGTK + Vite HMR) — release build path is unblocked, just
  hasn't been built yet
- VM deployment verified working (Pattern B — headless server + host
  browser)

**Marketing-grade claim available:**  
*"Watch ten agents at once, approve them by gesture, chat to them by voice,
no per-agent terminal switching."*

---

### 2. Memory (episodic) — `mempalace`

**What it does:** Stores full conversation transcripts, lets agents recall
what was said with semantic search. The retrieval layer that doesn't lose
context to LLM summarisation.

**Where it stands:**
- **96.6% LongMemEval R@5 in raw mode** — the **highest published score for
  a free local system**. This number deserves a position in every public
  description of the system and currently appears nowhere prominent
- AAAK summarisation mode is honest about its regression vs raw mode (you
  document this in the README, which is unusual and good)
- Per-project "wings" pattern — same memory store, different access scopes
  for different agents

**The gap on the research list:** a relevance-filter step between embedding
hit and prompt injection (steal from `jcode`'s side-agent-verifies-relevance
pattern).

**Marketing-grade claim available:**  
*"96.6% recall @5 on LongMemEval — top published result for a free local
memory system."*

---

### 3. Knowledge (verifiable claims) — `Knowledge_systems`

**What it does:** Every factual sentence in the knowledge base is hash-pinned
to a source. The answer to "but how do we know the agent is right?"

**Where it stands:**
- 14,790 files modified in the last 30 days — actively being built out
- 5.6 GB on disk
- Ingestion pipeline ready; public legal/general library manifests defined,
  unfinished step is the ingestion run itself
- Direct integration with a long-horizon agent like DeerFlow is the next
  composition move — the calls `knowledge_query` and `knowledge_cite` would
  make sense as MCP tools

**Position most competitors don't take:** when other systems answer "how does
the agent know X?" with vibes, this system answers with a hash and a source
location. That's a marketing line.

**Marketing-grade claim available:**  
*"Every claim hash-pinned to its source — no hallucinated citations."*

---

### 4. Memory (handoff) — `kalarc-memory`

**What it does:** Project-local memory that an agent can load on wake-up.
Defined a 400-token interface for "what does this agent need to know right
now?" Tiny, fast, composable.

**Where it stands:**
- Stable interface — 108 KB total, 7 files, no recent churn (good — it's
  stopped iterating because the interface settled)
- The 400-token wake-up is a clean spec other tools can target

**Marketing-grade claim available:**  
*"400-token agent wake-up — drops context cost ~90% vs naive prompt-loading."*

---

### 5. Voice surface — `qalarc-voice`

**What it does:** STT + TTS + speaker recognition + voice cloning. ~300 ms
TTS latency. TUI / Web / daemon modes.

**Where it stands:**
- 146 MB / 1,914 files — large because of model weights
- No churn in the last 30 days — interface stable
- Speaker recognition is the under-appreciated piece — most "AI voice"
  systems don't know who's talking

**The internal handshake left:** clarify which is voice surface (qalarc-voice)
and which is routing layer (claude_TUI) — see `COMPOSITION_GAPS.md`.

---

### 6. Control plane — `claude_TUI` (Kalarc)

**What it does:** Listens for wake-word "kalarc", routes voice input to the
right AI agent (QalCode by default). Has an APK served over Tailscale, so
the phone is an input/output device for the whole stack.

**Where it stands:**
- 385 MB on disk, 13,049 files (mostly bundled deps)
- Phone presence works
- DeerFlow-style multi-transport pattern would let it also accept Signal,
  Telegram etc. as peer transports — currently voice-only at input

---

### Supporting layers

#### Substrate — `local-models` (and the 96 GB APU it runs on)

96 GB unified memory means you can run llama-style models locally without
swapping. That's the foundation that makes "no API dependency" credible.

#### Gestures — `gesture-control` + siblings

MediaPipe Hands suite. Used as input (gmux navigation) and output
(robot_hand mirroring). 33 files modified in the last 30 days — active.

#### Glasses — `smart-glasses-face-tracker` + `glasses-ai-apk`

Glasses-camera POV → home computer → face recognition → push context to
phone. Loop end-to-end working. Sensor pattern for future always-on
devices.

---

## What's unusual about owning all six

Most people building "AI assistants" stop at one or two of these layers.
Concrete examples from the research batch:

- **jcode** = workspace + memory (no voice, no knowledge graph, no control plane)
- **DeerFlow** = harness + control plane (depends on external memory and search)
- **HALO** = self-improvement on top of *someone else's* workspace
- **Decepticon** = skills bundle, no surface beyond a single agent

The composition is rare. The opportunity is to **stitch what you have**
rather than build more layers.

---

## What's missing — three honest gaps

### A. Long-horizon harness above the workspace

A scheduler/planner that decomposes "do this big multi-day task" into the
small steps gmux already supervises. **DeerFlow** is the reference. Study
its memory + context-engineering docs first.

### B. Self-improvement loop

A way for the system to notice "this agent kept getting X wrong, here's
what changed in the prompt or skill that fixed it, propagate that learning."
**HALO** is the reference. Quick read, big idea.

### C. Honest agent quality scoring

Some pattern for "which agent is actually doing useful work and which is
spinning?" — borrowable from **ATLAS**'s Darwinian-weighting concept. Not a
blocker for shipping, but a strong post-launch feature.

---

## Stack-by-stack maturity score

| Stack | Maturity | Recent activity | Ship-ready? |
|---|---|---|---|
| Workspace (gmux+system) | 🟢 Production-adjacent | High | Yes, post-Tauri-release-build |
| Memory episodic (mempalace) | 🟢 Production | Medium | Yes |
| Knowledge graph | 🟡 Active build-out | Very high (14,790 files / 30d) | Manifests yes, ingestion pending |
| Memory handoff (kalarc) | 🟢 Stable | None (settled, good) | Yes |
| Voice surface (qalarc) | 🟢 Stable | None (settled) | Yes |
| Control plane (claude_TUI) | 🟡 Voice-only | Low | Needs multi-transport |
| Gestures | 🟢 Working | Medium | Yes (already in gmux) |
| Substrate (local-models) | 🟢 Working | None needed | Yes |

Seven of eight are green or close-to-green. That's a higher hit rate than
most "production" systems can show.

---

## How this folder builds on existing docs

This isn't a replacement for the per-project READMEs or for `AI_SYSTEMS_GUIDE.md`.
It's a **summary at the architecture level**, mostly written so the next
time someone (you, an investor, a collaborator, a future agent) reads
through the stack they don't have to reassemble the picture from a dozen
READMEs.

The single most important takeaway: **the stack is at the ship-then-iterate
threshold, not at the keep-building threshold.** The wins from now on come
from composition.
