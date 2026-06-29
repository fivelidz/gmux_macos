# Composition Gaps — The Stitching-Not-Building Work

> "Most of the wins from now on come from composition, not new builds."

This doc names every place where two existing systems should talk to each
other but don't yet. Each gap is a small piece of glue, not a new project.
Listed roughly in order of value-to-effort.

---

## 🔗 Gap 1 — Knowledge_systems ↔ gmux-brain (MCP)

**What's there:** Knowledge_systems has a query API. gmux-brain knows which
agent is asking. MCP is the right protocol for them to talk.

**What's missing:** An MCP server that wraps Knowledge_systems with two
tools (`knowledge_query`, `knowledge_cite`) and registers it in gmux-brain's
config.

**Why it matters:** Agents inside gmux gain access to your verifiable claim
graph as a callable tool, not as a prompt-injected blob. Citations stop
being hallucinations.

**Effort:** ~half a day. Write a thin MCP server (one Python file using the
existing FastMCP package), expose `knowledge_query(query, limit=N)` and
`knowledge_cite(claim)`, point gmux-brain at it.

**Test:** ask an agent a factual question, observe it call the MCP tool
rather than answering from training data.

---

## 🔗 Gap 2 — mempalace ↔ gmux-brain

**What's there:** mempalace has 96.6% LongMemEval R@5. gmux-brain has a
three-memory injection pattern. They overlap.

**What's missing:** mempalace exposed as the canonical "what was said"
backend for gmux-brain. Currently gmux-brain has its own memory store —
should defer to mempalace where they collide.

**Why it matters:** Single source of truth for episodic memory. No
duplication. gmux-brain becomes a *routing* layer over mempalace + kalarc
+ Knowledge_systems, not its own fourth store.

**Effort:** 1–2 days. Define the mempalace REST surface gmux-brain uses,
deprecate the redundant store in gmux-brain.

**Test:** start a session, talk to an agent, restart, see the agent recall
the conversation via mempalace.

---

## 🔗 Gap 3 — Memory panel ↔ Knowledge_systems (Activity tab)

**What's there:** The `dummy_ui/` for the memory panel is built. The
"Activity" tab is wired in v3.4 as a "coming soon" stub. The data source
exists in `panes[].tool_history` (live, real).

**What's missing:** Replace the stub Activity tab with the real renderer
from `dummy_ui/js/panel_activity.js`. Phase 1 of the integration playbook.

**Why it matters:** First useful tab in the memory panel ships, the
"coming soon" badge moves to the next three tabs. Demonstrable progress
on the integration story.

**Effort:** ~1 day. The playbook in `gmux_memory_integration/docs/03_INTEGRATION_GUIDE.md`
is step-by-step.

**Test:** trigger tool calls in an agent, see them stream into the Activity tab.

---

## 🔗 Gap 4 — DeerFlow as the harness above gmux

**What's there:** gmux supervises multiple agents but doesn't plan
long-horizon work. DeerFlow is the reference for that planner pattern.

**What's missing:** A DeerFlow instance that
- subscribes to gmux's state SSE
- decomposes a high-level goal into agent tasks
- sends prompts to the right agent via OpenCode's prompt API
- monitors completion, retries, escalates

**Why it matters:** The single architectural gap identified in the
research batch. Once this lands you have a planner above the workspace
and a planner-aware workspace — which is rare even among commercial
products.

**Effort:** 3–5 days. Mostly study and integration, not new code.

**Test:** give DeerFlow a 5-step research task, watch it spawn agents
across gmux windows, see results consolidated.

---

## 🔗 Gap 5 — claude_TUI multi-transport

**What's there:** claude_TUI is voice-only at input. Phone APK works over
Tailscale.

**What's missing:** Multi-transport input (Signal, Telegram, Slack, etc.)
using the DeerFlow IM-channel pattern. Same gateway, multiple transports.

**Why it matters:** The phone path becomes optional, not required, for
remote control. Any messaging tool that can talk to a webhook becomes a
control surface.

**Effort:** 2–3 days per transport. The architecture is the same — just
new adapters.

---

## 🔗 Gap 6 — humanizer as a default skill

**What's there:** `humanizer` is in the research batch.

**What's missing:** Install it as a default skill in `AI-coding-configs`
so transcribed voice input goes through it before becoming a prompt. The
voice-input quality jump is non-trivial.

**Why it matters:** Voice → faster-whisper STT → humanizer → agent prompt
is much cleaner than voice → STT → agent (which carries the "uh" "you
know" speech patterns into the agent's context).

**Effort:** ~half a day.

---

## 🔗 Gap 7 — jcode's `--dictate` for voice input

**What's there:** jcode has a `--dictate` flag.

**What's missing:** Wire claude_TUI's voice daemon as jcode's dictation
source.

**Why it matters:** Voice input lands in jcode the same way it lands in
gmux/claude. Same input layer, different harnesses.

**Effort:** few hours. Mostly adapter code.

---

## 🔗 Gap 8 — jcode's relevance-filter pattern in mempalace

**What's there:** mempalace recalls. jcode validates recalls with a side
agent.

**What's missing:** A relevance-filter step in mempalace's pipeline. After
embedding hit, before prompt injection, a small agent decides "is this
actually relevant to the current question?"

**Why it matters:** Lifts recall precision. Mostly free quality.

**Effort:** 1 day.

---

## 🔗 Gap 9 — MCP config layout convention

**What's there:** Different projects have MCP config in different places.

**What's missing:** Adopt jcode's three-tier pattern across all tools:
`~/.<tool>/mcp.json` (global), `.<tool>/mcp.json` (per-project), fallback
to `.claude/mcp.json`.

**Why it matters:** Reproducibility. Clone any tool's configs, get the
same agent. Currently per-tool conventions diverge.

**Effort:** half a day to define the convention, plus ad-hoc rollout per
project.

---

## 🔗 Gap 10 — ATLAS-style agent quality scoring

**What's there:** ATLAS / atlas-gic from the research batch.
gmux currently shows every agent as equally credible.

**What's missing:** A scoring layer that watches agent outputs over time,
weights them down when they keep producing bad work, surfaces this in the
UI as a confidence dot or numerical score.

**Why it matters:** When you're supervising ten agents, knowing which one
to trust is more valuable than knowing what state they're in.

**Effort:** 3–5 days. New backend logic + UI surfacing.

**Caveat:** Probably v1.1 — interesting but not a ship blocker.

---

## 🔗 Gap 11 — HALO self-improvement loop

**What's there:** HALO from the research batch.

**What's missing:** A way for the system to notice "this prompt change
fixed agent failures" and propagate that pattern.

**Why it matters:** The system gets better on its own. Long-term value.

**Effort:** 1–2 weeks. This is a real project, not glue.

**Caveat:** Definitely v1.1 or v1.2. Don't block v1 on this.

---

## 🔗 Gap 12 — A unified memory query interface

**What's there:** Three memory systems with three APIs.

**What's missing:** A single endpoint that:
- routes `who said X` to mempalace
- routes `is X true` to Knowledge_systems
- routes `what's this project's context` to kalarc-memory

Returns a unified `MemoryResult` schema.

**Why it matters:** Agents don't need to know which memory store they're
asking — they ask "memory" and get the right backend. Easier MCP tools,
cleaner prompts.

**Effort:** 2 days. Wrapper service over the existing stores.

---

## Gap inventory summary

| Gap | Effort | Value | When |
|---|---|---|---|
| 1. Knowledge_systems MCP | ½ day | High | v1 |
| 2. mempalace ↔ gmux-brain | 1–2 days | High | v1 |
| 3. Memory panel Activity tab | 1 day | Medium | v1 |
| 4. DeerFlow harness | 3–5 days | Very high | v1.1 |
| 5. Multi-transport claude_TUI | 2–3 days | Medium | v1.1 |
| 6. humanizer default skill | ½ day | Medium | v1 |
| 7. jcode --dictate | hours | Low | v1.1 |
| 8. Relevance-filter mempalace | 1 day | Medium | v1.1 |
| 9. MCP config convention | ½ day | Low | v1 |
| 10. ATLAS-style scoring | 3–5 days | High | v1.1 |
| 11. HALO self-improvement | 1–2 weeks | High long-term | v1.2 |
| 12. Unified memory query | 2 days | High | v1 |

Five gaps marked "v1" total ~5 days of work. Those would be a coherent
v1.0 stitching pass. The rest are post-launch.

---

## The composition argument restated

This whole document is the practical answer to the observation that:

> "The single biggest move you're underrating is **stitching them together
> formally** — most of the wins from now on come from composition, not new
> builds."

Twelve gaps. None of them require a new project. All of them are days of
glue work between projects that already exist. The cumulative effect of
filling the top five is significantly larger than any one of them
suggests.

**Compose, don't build.**
