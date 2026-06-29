# gmux — Rate-Limit Detection, Display & Intelligent Throttling

**Design report. No code changes. Investigation + concrete plan.**
Date: 2026-06-16
Scope: minute-level (RPM/ITPM/OTPM) rate-limit detection across multiple
concurrent Claude Code / opencode agents running in PTYs inside one gmux session.

---

## 0. TL;DR / Executive summary

- **The minute-level limits are real and small.** On the *API-key* path, Anthropic
  enforces per-minute **RPM**, **input-tokens-per-minute (ITPM)**, and
  **output-tokens-per-minute (OTPM)** buckets, *per model class*, using a
  **token-bucket** algorithm (continuous replenishment, not a fixed reset). At
  Tier 1, Sonnet 4.x is only **50 RPM / 30k ITPM / 8k OTPM** — trivially trippable
  by 3–4 concurrent agents.
- **The clean signal (HTTP headers) is hidden from gmux** because agents run in
  PTYs — gmux sees terminal text, not raw HTTP. The headers
  (`anthropic-ratelimit-*`, `retry-after`) exist but live *inside* each agent
  process.
- **gmux already has two partial detection paths** (monitor.py): an SSE
  `session.status: retry` signal from qalcode2, and a regex scan of the last
  terminal line for `rate.?limit|429|too many requests|...`. It already has a
  `RATE_LIMITED` pane state and a `_extract_retry_after()` parser.
- **gmux's usage bars are 5h/7d windows only** — the existing `usage.rs` hits
  `api.anthropic.com/api/oauth/usage`, which returns `five_hour` / `seven_day`
  *utilization* and reset times. **There is no per-minute signal in that data.**
- **Subscription (OAuth) vs API-key paths expose different headers.** OAuth/Max
  uses `anthropic-ratelimit-unified-*` (5h/7d utilization, overage status);
  API-key uses `anthropic-ratelimit-{requests,input-tokens,output-tokens}-*`
  (true per-minute). The minute problem the user hits most cleanly maps to the
  API-key path.
- **Cheapest high-value first step:** a **concurrency governor + staggered
  restart** driven purely by the detection signals gmux *already has* (the
  `RATE_LIMITED` state + `retry-after`). No proxy, no header access required for
  the MVP. A **local proxy** is the "full" solution that unlocks true
  header-accurate budgeting.

---

## 1. Rate-limit headers & the bucket model (from Anthropic docs)

Source: **docs.claude.com/en/api/rate-limits** (and the identical
docs.anthropic.com mirror), fetched 2026-06-16.

### 1.1 The bucket model — token bucket, continuously replenished

Direct quotes from the docs:

> "The API uses the **token bucket algorithm** to do rate limiting. This means
> that your capacity is **continuously replenished up to your maximum limit,
> rather than being reset at fixed intervals**."

> "You might hit rate limits over shorter time intervals. For instance, a rate of
> 60 requests per minute (RPM) might be enforced as **1 request per second**.
> Short bursts of requests can exceed the limit and trigger rate limit errors."

Implications for gmux:
- It is **not** a sliding-window-per-minute counter you can "wait out" to a
  clean minute boundary. The bucket refills continuously. The practical rate
  ceiling for RPM=60 is ~1 req/sec; bursting 4 agents simultaneously can trip it
  even when the per-minute average is fine.
- There is **no clean "minute boundary"** to align to. Backoff must be in terms
  of *rate* (spread requests out), not "wait for the top of the next minute".
- A separate **acceleration limit** exists: a sharp *increase* in usage can 429
  you even below your nominal limit. Quote: *"ramp up your traffic gradually and
  maintain consistent usage patterns."* — this directly validates the
  additive-increase governor proposed in §4.

### 1.2 The three per-minute buckets (Messages API, API-key path)

Limits are **per model class** (Sonnet 4.x is one pooled class, Opus 4.x another):

| Bucket | Meaning |
|---|---|
| **RPM** | requests per minute |
| **ITPM** | input tokens per minute (uncached only on most models — see below) |
| **OTPM** | output tokens per minute (counted in real time as tokens stream) |

**Cache-aware ITPM (critical for the budget scheduler):**
- `input_tokens` (after last cache breakpoint) → **counts**
- `cache_creation_input_tokens` (cache writes) → **counts**
- `cache_read_input_tokens` (cache reads) → **does NOT count** (except Haiku 3.5, marked †)
- So `total_input = cache_read + cache_creation + input_tokens`, but only the
  last two count toward ITPM. A high cache-hit rate dramatically raises your
  effective ITPM ceiling. **This is why agents with long shared context (same
  repo, cached system prompt) can run more concurrently than naïve token math
  suggests.**
- OTPM counts only actual tokens generated; `max_tokens` does **not** factor in.

**Tier-1 standard limits (the user is most likely here on an API key):**

| Model | RPM | ITPM | OTPM |
|---|---|---|---|
| Sonnet 4.x | 50 | 30,000 | 8,000 |
| Haiku 4.5 | 50 | 50,000 | 10,000 |
| Opus 4.x | 50 | 500,000 | 80,000 |

Tier-2 jumps to 1,000 RPM and 450k ITPM for Sonnet. **The 8,000 OTPM on
Tier-1 Sonnet is the most likely thing the user trips** — a single agent
streaming a long response can eat that, and 3 agents will collide.

### 1.3 Response headers (API-key path) — exact names

From the docs "Response headers" table (verbatim header names):

| Header | Description |
|---|---|
| `retry-after` | seconds to wait before retry (429 only) |
| `anthropic-ratelimit-requests-limit` | max requests in the period |
| `anthropic-ratelimit-requests-remaining` | requests left before limited |
| `anthropic-ratelimit-requests-reset` | RFC-3339 time when requests fully replenish |
| `anthropic-ratelimit-tokens-limit` | max tokens in period (most restrictive of in/out) |
| `anthropic-ratelimit-tokens-remaining` | tokens left (rounded to nearest 1,000) |
| `anthropic-ratelimit-tokens-reset` | RFC-3339 reset time |
| `anthropic-ratelimit-input-tokens-limit` | max input tokens/period |
| `anthropic-ratelimit-input-tokens-remaining` | input tokens left (nearest 1,000) |
| `anthropic-ratelimit-input-tokens-reset` | RFC-3339 reset |
| `anthropic-ratelimit-output-tokens-limit` | max output tokens/period |
| `anthropic-ratelimit-output-tokens-remaining` | output tokens left (nearest 1,000) |
| `anthropic-ratelimit-output-tokens-reset` | RFC-3339 reset |
| `anthropic-priority-*` | same set, Priority Tier only |

Notes:
- `retry-after` is **seconds** on the 429. There is also an undocumented-in-this-table
  but real **`retry-after-ms`** header (qalcode2's `retry.ts` reads it first — see §2.3).
- `anthropic-ratelimit-tokens-*` shows the **most restrictive** limit currently
  in effect (workspace per-minute if you exceeded that, else org total).
- `*-remaining` is **rounded to the nearest 1,000** — fine-grained budgeting from
  these headers has ±1k token granularity.
- **These are the gold signal for a proxy** (§3.2): every successful response
  carries `*-remaining` and `*-reset`, so a proxy sees the true minute budget
  drain in real time *before* a 429 ever happens.

### 1.4 Subscription / OAuth path headers (what the Max user actually sees)

The OAuth/subscription path (Claude Code logged in via claude.ai) does **not**
expose the per-minute `anthropic-ratelimit-{requests,tokens}-*` headers the same
way. Instead, from qalcode2's own captured headers
(`docs/issues/AUTH_ISSUES_2026-04-14.md`, `README.md`, `MAINTENANCE.md`):

```
anthropic-ratelimit-unified-status: allowed
anthropic-ratelimit-unified-5h-utilization: 0.03
anthropic-ratelimit-unified-7d-utilization: 0.12
anthropic-ratelimit-unified-overage-disabled-reason: org_level_disabled
anthropic-ratelimit-unified-overage-status: rejected
```

So on the subscription path:
- `anthropic-ratelimit-unified-5h-utilization` / `-7d-utilization` are the **5h
  and 7d window utilizations** (0.0–1.0). **These map exactly to gmux's existing
  5h / 7d usage bars** — see §2.4.
- There is **no per-minute unified header** in this set. The subscription
  enforces the long windows + per-model tier gating; the minute problem on the
  subscription path manifests as **429s on Sonnet/Opus while Haiku still works**
  (documented in the AUTH_ISSUES table). That is *tier/overage* gating, not a
  clean per-minute counter you can read.

**Bottom line on (1):** clean per-minute numbers (`*-remaining`, `*-reset`) only
exist on the **API-key** path. On the **subscription** path you get 5h/7d
utilization (already shown) plus opaque 429s. The detection strategy must
therefore degrade gracefully (§3): proxy-read headers when on an API key;
text/retry-signal detection always.

---

## 2. Claude Code / opencode specifics & what gmux already captures

### 2.1 OAuth (subscription) vs API key — they expose different headers

| | Subscription / OAuth (claude.ai Max login) | API key (console) |
|---|---|---|
| Per-minute RPM/ITPM/OTPM headers | ❌ not exposed in unified form | ✅ `anthropic-ratelimit-*` |
| 5h / 7d utilization | ✅ `anthropic-ratelimit-unified-*-utilization` + `/api/oauth/usage` | partial |
| `retry-after` on 429 | ✅ | ✅ |
| Overage status | ✅ `unified-overage-*` | n/a |
| Minute-limit failure mode | 429 on higher-tier model (Sonnet/Opus), Haiku still works | clean 429 naming the bucket exceeded |

This matters: **if the user is on a Max subscription, gmux cannot read true
TPM-remaining from headers** — even a proxy only sees the `unified` headers. The
governor (§4) must then run in *reactive* mode (learn the safe concurrency from
observed 429s) rather than *predictive* mode (compute from `*-remaining`).

### 2.2 Where Claude Code / opencode surface rate-limit info in the terminal

These are the **exact strings gmux can match in PTY output**:

- **Claude Code CLI** prints a status line during automatic retries, e.g.
  `Retrying in Ns…` / messages containing `rate limit` / `overloaded` /
  `Please try again in Xh Ym Zs` (the Anthropic 429 body). It auto-retries with
  backoff internally, so a transient minute-limit may only flash briefly.
- **opencode / qalcode2** maps the error to a session status `retry` and the TUI
  shows `Retrying...` / `waiting` (confirmed in qalcode2 sources:
  `sidebar.tsx` → `"waiting"`, `prompt/index.tsx` → status `retry`,
  `subagent-panel.tsx`/`session-tabs.tsx` → status `error`/`retry`).
- The retryable classifier in qalcode2 (`session/retry.ts`) recognizes:
  - JSON `{"type":"error","error":{"type":"too_many_requests"}}` → `"Too Many Requests"`
  - `message.includes("Overloaded")` → `"Provider is overloaded"`
  - `code === "Some resource has been exhausted"` → `"Provider is overloaded"`

### 2.3 qalcode2's existing 429 / retry handling — `session/retry.ts`

The fork already implements exponential backoff that honours the headers:

```
RETRY_INITIAL_DELAY      = 2000 ms
RETRY_BACKOFF_FACTOR     = 2
RETRY_MAX_DELAY_NO_HEADERS = 30_000 ms
```

`delay(attempt, error)` logic (paraphrased from source):
1. If `retry-after-ms` header present → use it (float ms).  ← **note: `-ms` variant**
2. Else if `retry-after` header present → seconds×1000, or parse as HTTP-date.
3. Else if headers exist but no retry-after → `2000 * 2^(attempt-1)` (uncapped).
4. Else (no headers) → `min(2000 * 2^(attempt-1), 30_000)`.

So **each agent already backs off individually**. The multi-agent problem gmux
must solve is the *thundering herd*: N agents each independently backing off and
then all re-firing near the same time, re-tripping the bucket. qalcode2's
per-agent backoff has **no cross-agent coordination** — that's gmux's job (§4).

The README/MAINTENANCE also document the subscription-path 429 signature
(`anthropic-ratelimit-unified-overage-disabled-reason: org_level_disabled`) and
the per-model behavior (Haiku OK, Sonnet/Opus 429).

### 2.4 What gmux ALREADY captures — two layers

**Layer A — `app/src-tauri/src/commands/usage.rs` (the usage bars):**
- Calls `GET https://api.anthropic.com/api/oauth/usage` with the Claude Code
  OAuth Bearer token + `anthropic-beta: oauth-2025-04-20` + UA `claude-code/2.0.32`.
- Parses `five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus` →
  each `{ utilization, resets_at }`.
- Surfaces: `session_percent` (5h), `weekly_percent` (7d all), `weekly_sonnet_percent`,
  `weekly_opus_percent`, plus reset timestamps.
- Caches 30s; on 429 it reads `retry-after` and extends cache TTL.
- **No per-minute data.** This endpoint only returns the long windows. *This is
  the source of the "5hr limit" and "sonnet limit" usage bars the user sees.*

**Layer B — `backend/status/monitor.py` (the per-pane state machine):**
- Has a dedicated `PaneState.RATE_LIMITED` ("⏱ ORANGE-RED").
- **Signal A (SSE):** subscribes to each qalcode2 instance's `/event` SSE; on
  `session.status { type: "retry" }` (and the record form
  `{sessionID: {type:"retry"}}`) it flags the pane.
- **Signal C (PTY text):** scans the last terminal line with
  `_RATE_LIMIT_RE = rate.?limit|429|too many requests|quota exceeded|resource_exhausted`
  and, if matched, sets `RATE_LIMITED` + `rate_limit_msg` + `rate_limit_until`.
- `_extract_retry_after(text)` parses, in order:
  1. `Retry-After: N` → now+N (or raw epoch if N > 1e9)
  2. `try again in Xh Ym Zs` → now+total+30s grace
  3. `resets at HH:MM AM/PM UTC` → that wall-clock time
  4. **Fallback: now + 310s** if rate-limit text present but no timer (the 5-min
     padding is deliberate — hammering right after reset re-trips on some accounts).
- It already stores `rate_limit_until` per pane so a frontend auto-resume loop
  "has a concrete target to wait for."

**So gmux is ~60% of the way to detection already.** What it lacks:
- A **per-minute** signal (only 5h/7d + the binary RATE_LIMITED flag exist).
- **Cross-agent coordination** of restart timing.
- A **concurrency-vs-429** feedback loop and UI for it.

---

## 3. Detection strategy for gmux (PTY-constrained)

Three signal sources, in increasing fidelity:

### 3.1 PTY text parsing (have it; harden it)

Already implemented (§2.4 Signal C). Recommended additions:
- Match the qalcode2 TUI strings too: `Retrying...`, `Too Many Requests`,
  `Provider is overloaded`, `Overloaded`.
- Match Claude Code's `Retrying in Ns` so we can read N directly.
- Capture **per-pane timestamps of each detected 429** into a ring buffer — this
  is the raw data the governor needs ("how many 429s in the last 60s, across all
  panes").
- Caveat: PTY text is **lossy and laggy** — Claude Code auto-retries silently, so
  a brief minute-limit may never print. Use this as a *floor*, not the source of
  truth.

### 3.2 Local proxy (the high-fidelity option) — feasibility + design

**Idea:** run a tiny local HTTPS forward-proxy that all agents route through
(`ANTHROPIC_BASE_URL=http://127.0.0.1:PORT`). The proxy forwards to
`api.anthropic.com`, and on every response **reads the `anthropic-ratelimit-*`
and `retry-after` headers** centrally — giving gmux the *true* minute budget for
the whole agent fleet in one place.

**Feasibility: HIGH for API-key, MEDIUM for subscription.**
- Both Claude Code and opencode honour `ANTHROPIC_BASE_URL` (opencode via
  provider config; Claude Code via env). gmux already launches agents, so it can
  inject the env var per pane.
- The proxy needs no TLS-MITM if it's a *forward* proxy to which clients send
  plain HTTP and it re-originates HTTPS to Anthropic. (Clients talk HTTP to
  localhost; proxy talks HTTPS upstream.) No cert installation needed.
- **Subscription caveat:** the OAuth path uses spoofed UA / beta headers and only
  returns `unified-*` headers — the proxy still sees those (5h/7d utilization +
  overage status) but **not** per-minute remaining. Still useful: it gets the
  *exact* `retry-after` on every 429 with zero PTY-parsing ambiguity.

**Rough design:**
```
agents ──HTTP──▶ gmux-proxy (127.0.0.1:PORT) ──HTTPS──▶ api.anthropic.com
                      │
                      ├─ on each response: parse anthropic-ratelimit-* headers
                      ├─ maintain a fleet-wide RateBudget {rpm,itpm,otpm}_remaining + reset
                      ├─ on 429: record retry-after, feed governor (multiplicative decrease)
                      └─ expose GET /gmux/ratebudget for the UI + governor
```
- Stateless pass-through for bodies (stream them through untouched — important
  for SSE token streaming; do **not** buffer the whole response).
- Tag each request with the originating pane (via a custom request header gmux
  injects, e.g. `x-gmux-pane: <id>`) so per-agent attribution works.
- Optional **request gate**: the proxy can *hold* a request for a few hundred ms
  if `*-remaining` is near zero, smoothing bursts into the token-bucket refill
  rate (this is the cleanest place to implement the budget scheduler in §4.3).

**Cost / risk:** one extra long-lived process; must be rock-solid (it's in the
critical path of every agent request). Streaming pass-through must be correct or
it breaks the TUIs. This is the **"full" milestone**, not the MVP.

### 3.3 Estimating TPM/RPM from data gmux already has

Without a proxy, gmux can *approximate*:
- **RPM proxy metric:** count `message.part.updated` / turn-boundary SSE events
  per pane per 60s window → rough requests/min across the fleet. (One agent
  "turn" ≈ one or more API requests; not exact but trend-accurate.)
- **TPM proxy metric:** opencode emits token usage per message in its SSE/`/session`
  data; sum `input + cache_creation` (for ITPM) and `output` (for OTPM) across
  panes over a sliding 60s window. Claude Code is harder (less structured output)
  — fall back to the proxy or to RPM-only.
- **Prediction:** compare the rolling 60s sum to the tier limits in §1.2. If the
  fleet's 60s ITPM is >70% of 30k (Tier-1 Sonnet), show amber; >90% red. This is
  a *heuristic* because the bucket is continuous, but it's a useful early-warning
  the user currently has zero of.
- The existing 5h/7d `utilization` from `usage.rs` is **not** a minute signal and
  should not be used for minute prediction — but it IS the right input for "you're
  about to burn your whole 5h window" warnings.

---

## 4. Intelligent throttling design (concrete algorithms)

### 4.1 Concurrency governor — AIMD (TCP-style)

Maintain a single fleet-wide integer **`N_safe`** = max agents allowed to be
*actively in a turn* simultaneously. Agents wanting to start a turn acquire a
slot from a semaphore of size `N_safe`.

**Additive-Increase / Multiplicative-Decrease:**
- **State:** `N_safe` (float, floor 1), `N_max` (hard cap, e.g. 8), tunables below.
- **On a clean window** (no 429 across the fleet for `T_probe = 60s`):
  `N_safe += 1` (additive increase — mirrors the docs' "ramp gradually" advice).
- **On any 429** (from proxy header or PTY/SSE detection):
  `N_safe = max(1, floor(N_safe * 0.5))` (multiplicative decrease), AND enter a
  **cooldown** for `retry_after` seconds (from §4.2) during which no increase happens.
- **Damping:** ignore additional 429s within a `T_quiet = 5s` window of the first
  (they're the same congestion event — N agents all hit it at once); only one
  halving per event.
- **Persistence:** remember the last stable `N_safe` per (model-class, account)
  across sessions so a fresh launch doesn't re-probe from 1 every time.

Concrete defaults to start: `N_safe_init = 2`, `N_max = 8`, increase step `+1`,
decrease ×0.5, `T_probe = 60s`, `T_quiet = 5s`. These converge to the true safe
concurrency within a few minutes and self-heal when the tier/window changes.

### 4.2 Staggered restart with exponential backoff + jitter

The core fix for "loop restarts all agents → instantly re-trip". When a loop or
the governor releases agents after a rate-limit event, **never fire them
simultaneously.**

For agent *i* of the waiting set (i = 0..k-1), schedule its restart at:

```
base_i      = retry_after            # from retry-after / _extract_retry_after fallback (now+310s)
backoff_i   = min(BASE * 2^attempt, CAP)         # per-agent attempt count
jitter_i    = random_uniform(0, SLOT)            # decorrelated jitter
stagger_i   = i * SLOT                            # deterministic spread across the fleet
start_i     = base_i + backoff_i + stagger_i + jitter_i
```

Concrete numbers tied to the minute window (token bucket ≈ RPM/60 per sec):
- `BASE = 2s`, `CAP = 60s` (matches qalcode2's own 2s/30s feel, slightly higher cap).
- `SLOT = 1.5s` — spread agents ~1.5s apart so that at RPM=50 (≈0.83 req/s ceiling)
  the fleet's restart burst stays under the per-second token-bucket refill.
- Prefer **"decorrelated jitter"** (AWS-style):
  `sleep = min(CAP, random_uniform(BASE, prev_sleep * 3))` per agent — this
  avoids synchronized retries better than fixed exponential.
- For RPM-limited tiers, the safe restart cadence is **≈ RPM/60 starts per second**.
  At Tier-1 (50 RPM) that's ~1 agent every 1.2s → use `SLOT ≈ 1.5s`. At Tier-2
  (1000 RPM) you can shrink `SLOT` to ~0.2s.

### 4.3 Token-budget scheduler (proxy-enabled / predictive mode)

When the proxy (§3.2) gives true `*-remaining` + `*-reset`:
- Compute refill rate: for ITPM, `rate = limit / 60` tokens/sec (token bucket).
- Maintain a **fleet budget** = `min(requests_remaining as req-equiv,
  input_tokens_remaining, output_tokens_remaining)` for the active model class.
- **Admission control:** before letting an agent start a turn, estimate its cost
  (use a rolling average of that agent's recent input+output tokens). Admit only
  if `estimated_cost ≤ remaining * SAFETY (0.8)`. Otherwise queue it until
  `*-reset` or until enough refill (`elapsed * rate`) accrues.
- **Fair share:** divide remaining budget by number of waiting agents so one
  greedy agent can't starve the rest (mirrors the per-workspace split idea in
  Anthropic's docs).
- **Cache awareness:** since `cache_read` tokens don't count toward ITPM, agents
  sharing a cached system prompt / repo context are *cheaper* — weight their
  estimated cost by the observed cache-hit rate to admit more of them.

### 4.4 UI indicators

| Indicator | Source | States |
|---|---|---|
| **Minute meter** "X/Y req this min" + "ITPM 18k/30k" | proxy headers (full) or estimated counters (MVP) | green <70%, amber 70–90%, red >90% |
| **Concurrency dial** "N_safe = 3 (max 8)" | governor | shows current cap + how many slots in use |
| **"Safe to add agent?" lamp** | governor + minute meter | 🟢 slot free & budget <70% / 🟡 slot free but budget high / 🔴 no slot or rate-limited |
| **Per-pane ⏱ badge + countdown** | existing `RATE_LIMITED` + `rate_limit_until` | already present; add live "resumes in Ns" |
| **5h / 7d bars** | existing `usage.rs` | already present; keep |
| **Fleet 429 sparkline** | governor's 429 ring buffer | last 5 min of 429 events |

The "safe to add agent?" lamp is the single highest-value new widget — it
directly answers the user's question "how many agents can I run right now?"

---

## 5. Concrete recommendation — phased plan

### Phase 0 — MVP (days, no proxy, reuse existing signals)
**Goal: stop the thundering herd; give the user a concurrency number.**
1. **Fleet 429 aggregator** in monitor.py: collect every `RATE_LIMITED`
   transition + `rate_limit_until` into a fleet-wide ring buffer (timestamp,
   pane, retry_after). *(Detection already exists — just aggregate it.)*
2. **AIMD concurrency governor** (§4.1) as a small coordinator: a semaphore of
   size `N_safe` that agent-restart logic must acquire. Start `N_safe = 2`,
   halve on 429, +1 per clean 60s.
3. **Staggered restart** (§4.2): replace any "resume all panes" logic with the
   `stagger_i + jitter` schedule. `SLOT = 1.5s`, `BASE = 2s`, `CAP = 60s`,
   decorrelated jitter.
4. **UI:** concurrency dial + "safe to add agent?" lamp + per-pane resume
   countdown (the data is already in `rate_limit_until`).

This is the **cheapest high-value step** and needs no header access — it's pure
coordination on top of detection gmux already has.

### Phase 1 — Estimated minute meter (weeks)
5. Add rolling 60s **RPM/ITPM/OTPM estimators** from opencode SSE token-usage
   events (§3.3). Compare to tier table (§1.2). Drive the amber/red minute meter.
6. Let the user set their **tier** (or infer it) so the meter has correct limits.
   Default to Tier-1 Sonnet (the tightest, safest assumption).

### Phase 2 — Local proxy (the "full" solution)
7. Ship the **gmux local proxy** (§3.2). Inject `ANTHROPIC_BASE_URL` per agent.
   Read true `anthropic-ratelimit-*` + `retry-after(-ms)` centrally.
8. Switch the governor from *reactive* (learn from 429s) to *predictive*
   (admission control from `*-remaining`, §4.3). Add the token-budget scheduler
   with cache-aware costing.
9. Proxy-level **request gating** to smooth bursts into the token-bucket refill
   rate — the cleanest place to actually prevent 429s rather than recover from them.

### Notes / gotchas to carry forward
- **Per model class:** Sonnet 4.x and Opus 4.x have *separate* buckets — the
  governor and meter must be keyed by model class, not global.
- **Subscription users can't get per-minute headers** — Phase 2's predictive mode
  degrades to Phase 0's reactive mode for them; that's expected, not a bug.
- **`retry-after-ms` exists** and is more precise than `retry-after` — read it
  first (qalcode2 already does in `retry.ts`).
- **The token bucket has no minute boundary** — never "wait for the top of the
  minute"; spread requests at ≈ RPM/60 per second instead.
- **Cache reads are free for ITPM** — agents sharing cached context can run more
  concurrently than naïve token math implies; the scheduler should exploit this.

---

## Appendix — file/source references

- `app/src-tauri/src/commands/usage.rs` — 5h/7d usage bars; `/api/oauth/usage`;
  429 handling reads `retry-after` (L511–529). **No per-minute data.**
- `backend/status/monitor.py` — `PaneState.RATE_LIMITED` (L112); SSE `retry`
  detection (L584–620, L1525); `_RATE_LIMIT_RE` (L943); `_extract_retry_after`
  (L951–1003); PTY-text fallback (L1945–1961).
- `qalcode2/packages/opencode/src/session/retry.ts` — per-agent backoff
  (2s init, ×2, 30s cap; reads `retry-after-ms` then `retry-after`); retryable
  classifier (`too_many_requests`, `Overloaded`, `resource exhausted`).
- `qalcode2/docs/issues/AUTH_ISSUES_2026-04-14.md`,
  `qalcode2/README.md` (L161–169), `qalcode2/MAINTENANCE.md` (L222–230) —
  subscription-path `anthropic-ratelimit-unified-*` headers + per-model 429s.
- Anthropic docs: **docs.claude.com/en/api/rate-limits** (token-bucket model,
  RPM/ITPM/OTPM tables, full `anthropic-ratelimit-*` header table), fetched
  2026-06-16.
