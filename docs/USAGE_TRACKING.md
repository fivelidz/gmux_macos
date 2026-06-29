# Usage Tracking — Design

Goal: show per-provider quota / current-hour usage / rate-limit headroom
in the gmux UI, like Claude Console's
[Usage page](https://claude.ai/settings/usage) does in the browser.

**Status:** spec only — not implemented. Planned for v3.8.
**Why:** so users know WHY their agent paused (rate-limited) and WHEN it
will recover, without having to open the Claude Console in a browser.

---

## The two layers of usage data

There are two distinct things to surface, and they come from different
places:

### Layer 1 — per-request, returned in every API response

Anthropic, OpenAI, and Google all return rate-limit metadata as HTTP
response headers on every API call. This is real-time, free, and exact.

**Anthropic headers** (confirmed in `docs.anthropic.com/en/api/rate-limits`):
```
anthropic-ratelimit-requests-limit
anthropic-ratelimit-requests-remaining
anthropic-ratelimit-requests-reset            (RFC 3339)
anthropic-ratelimit-input-tokens-limit
anthropic-ratelimit-input-tokens-remaining
anthropic-ratelimit-input-tokens-reset
anthropic-ratelimit-output-tokens-limit
anthropic-ratelimit-output-tokens-remaining
anthropic-ratelimit-output-tokens-reset
retry-after                                   (only on 429)
```

**OpenAI headers**:
```
x-ratelimit-limit-requests
x-ratelimit-limit-tokens
x-ratelimit-remaining-requests
x-ratelimit-remaining-tokens
x-ratelimit-reset-requests
x-ratelimit-reset-tokens
```

**Google Gemini headers**:
- Less standardised; uses gRPC-style trailers and HTTP `Retry-After`.

opencode itself proxies these requests; **we don't see the headers
directly**. We need a way to expose them.

### Layer 2 — cumulative hourly / daily usage from the Console API

For Claude specifically, the long-term view (hourly totals for the
current hour and previous hour) lives at the **Console API** endpoint —
not the regular Messages API. The console doesn't have a documented
"current hourly usage" REST endpoint in public docs; the
`claude.ai/settings/usage` UI fetches it from a private backend.

What we CAN use:
- The **`/v1/organizations/{org_id}/cost_report`** endpoint (Admin API)
  returns daily token + dollar totals — granular enough.
- For the hour-bucket view: aggregate the per-response Layer 1 data ourselves.
  Every time we see `anthropic-ratelimit-input-tokens-remaining` drop by N,
  log "N tokens used at this minute" and bucket by hour.

---

## Architecture — where to instrument

opencode owns the API requests. We have three options:

### Option A — opencode plugin (preferred, future)
opencode supports a plugin system that fires on every model call. A
plugin could capture the response headers and emit them to a local
socket. **Not implemented yet upstream**; this is the cleanest path.

### Option B — opencode HTTP API (immediate)
opencode exposes `/session/{id}/message` which returns the full message
history including provider metadata. Some opencode versions include
`response_headers` in the metadata block.

Need to verify: poll one of our running opencode instances and see what
metadata fields are present. Action item for tomorrow.

### Option C — mitm via proxy (deepest, last-resort)
Set `ANTHROPIC_BASE_URL=http://127.0.0.1:9090` on the agent's env and
run a tiny Python proxy at `:9090` that forwards to
`https://api.anthropic.com` while capturing headers. Works for any
provider, but adds latency and complexity, and breaks streaming if not
careful.

**Decision:** start with Option B by inspecting opencode's message
metadata. Add C as a fallback for providers where B doesn't expose
headers.

---

## Implementation plan

### Phase 1 — capture (v3.8)

`backend/status/usage_tracker.py` (new):

```python
"""
Polls each opencode instance for recent message metadata and extracts
rate-limit / usage headers. Aggregates into /tmp/gmuxtest-usage.json.

Schema:
{
  "by_provider": {
    "anthropic": {
      "rpm_limit": 1000,
      "rpm_remaining": 942,
      "rpm_reset_ts": 1736003900,
      "input_tpm_limit": 450000,
      "input_tpm_remaining": 384000,
      "input_tpm_reset_ts": 1736003900,
      "output_tpm_limit": 90000,
      "output_tpm_remaining": 72000,
      "output_tpm_reset_ts": 1736003900,
      "current_hour_input_tokens": 156000,
      "current_hour_output_tokens": 18000,
      "previous_hour_input_tokens": 423000,
      "previous_hour_output_tokens": 51000,
      "model_breakdown": {
        "claude-sonnet-4.5": {"in": 130000, "out": 15000},
        "claude-haiku-4.5":  {"in":  26000, "out":  3000}
      },
      "last_429_ts": null,
      "last_429_retry_after_s": null
    },
    "openai":   { ... similar shape ... },
    "google":   { ... },
    "deepseek": { ... }
  },
  "by_pane": {
    "%42": { "provider": "anthropic", "tokens_session": 23000, "cost_session": 0.42 }
  },
  "last_aggregated_ts": "2026-05-13T22:34:56Z"
}
```

How:
1. Every 10s (in monitor.py's existing `_aggregate_worker`), for each
   pane with an active opencode session:
   - GET `http://127.0.0.1:<port>/session/<id>/message?directory=<cwd>`
   - Walk messages, find the most recent with `metadata.response_headers`
   - Update `by_provider[provider]` with the latest header values
2. Bucket per-hour token usage by aggregating drops in `*-tokens-remaining`
   minute over minute.
3. Atomic write to `/tmp/gmuxtest-usage.json`.

### Phase 2 — Tauri broadcast (v3.8)

`app/src-tauri/src/lib.rs`:
- State-poll thread reads `/tmp/gmuxtest-usage.json`
- Emits `usage-update` event to main + dashboard windows

### Phase 3 — UI (v3.8)

**Main UI status bar** — new compact widget on the right side of the
bottom bar:
```
● anthropic 942/1000 RPM · 156k/450k ITPM · resets in 23s
```
Click → opens detail modal with per-provider breakdown.

**Dashboard** — new "Usage" tab in the right detail panel:
- Bar charts for current-hour vs previous-hour for each provider
- Progress bars for RPM / ITPM / OTPM remaining
- Big red banner if any limit < 10% remaining
- Estimated time-to-exhaustion based on current burn rate

**New-agent modal** — show "Provider quota: 942 RPM, 156k ITPM"
under the model dropdown so users pick a model that has headroom.

### Phase 4 — Rate-limit prediction (v3.9)

With historical data we can predict "you'll hit your limit in ~3 minutes
at this burn rate". Surface as a warning before the agent gets 429'd.

---

## How this ties to existing rate-limit detection

v3.7's `PaneState.RATE_LIMITED` covers the **after** case — we saw a 429
and surfaced it. Usage tracking is the **before** case — show headroom
so users avoid the 429.

The two work together: rate-limit detection sets RATE_LIMITED state and
records retry-after; usage tracking shows the gauge that was approaching
the limit and now reads 0 remaining.

---

## Per-provider quirks

### Anthropic
- Headers are clean and standardised — easiest to integrate
- Bonus: `priority-*` headers when on Priority Tier
- Cache-aware ITPM: `cache_read_input_tokens` do NOT count (most models)
- Hourly aggregation matches what the Console shows

### OpenAI
- Two limits: requests-per-minute and tokens-per-minute
- Some headers in seconds reset time, others in ISO timestamps — adapter
  must normalise both
- Burst capacity not exposed in headers; documented separately

### Google Gemini
- Sparse headers; rely on 429 retry-after only
- Quota lives in Google Cloud Console — could pull via Admin API key
  but most users won't have one

### DeepSeek / Mistral / Groq / xAI
- All follow either OpenAI-compatible or Anthropic-compatible header
  conventions
- Adapter layer abstracts away differences

### Ollama (local)
- No quota; always "unlimited"
- Show as "local · no quota" in UI

---

## What to do tomorrow

1. **Confirm opencode exposes response headers.** Connect to a running
   opencode session, request `/session/{id}/message`, inspect what's in
   `metadata`. If headers are there: go with Option B. If not: prototype
   Option C proxy.

2. **Implement `usage_tracker.py` skeleton** that produces the JSON
   schema above with fake data, so the UI can be built against it before
   the real ingestion works.

3. **Wire the status-bar widget** in `ui/v3/index.html`. Compact, clickable,
   live-updating.

4. **Add `usage-update` event broadcast** in the Rust state-poll thread.

5. **Document** the integration in `INTEGRATION.md`.

---

## Test plan

- Empty usage file → UI shows "no provider data yet"
- Single provider near limit → status bar widget turns yellow at <30%, red at <10%
- 429 received → status bar widget shows countdown, dashboard usage tab shows red banner
- Multi-provider → status bar widget cycles through them every 4 seconds
- Provider absent from auth.json → not shown
- Local-only (Ollama) → shows "local · no quota"

---

## Open questions

1. **Should we ALSO query Anthropic's Admin API for org-level cost?**
   Requires the org admin API key (not the user's OAuth). Could be a
   per-machine config option ("show monthly spend gauge") since it's
   optional.

2. **Per-pane vs per-provider?** If you have 5 panes all using Anthropic,
   they share one rate limit. The status bar should show the **provider**
   gauge (shared). The per-pane Token tab in detail panel already shows
   per-pane cumulative — keep that, add provider gauge separately.

3. **History retention?** Hour buckets for 24 hours = 24 rows. Cheap.
   Daily for 30 days = 30 rows. Also cheap. Store in
   `~/.local/share/gmux/usage-history.json`?
