# Maestro Usage Display — Study + Comparison vs gmux

**Date:** 2026-05-18
**Maestro source:** `/tmp/maestro` (cloned from `github.com/its-maestro-baby/maestro`)
**gmux source:** `/home/fivelidz/projects/gmux_v4`

## Executive summary

**gmux's `app/src-tauri/src/commands/usage.rs` is byte-identical to maestro's
`src-tauri/src/commands/usage.rs`.** The previous gmux work already lifted
maestro's exact usage-fetching strategy into gmux. There is nothing more
to copy on the backend.

The only delta is the frontend layer (vanilla JS for gmux vs React+Zustand
for maestro) and a few small UX choices.

---

## Backend: identical

Both apps:
1. Try the OS credential store first (macOS Keychain via `security` CLI,
   Linux Secret Service via the `keyring` crate, Windows Credential
   Manager).
2. Fall back to reading `~/.claude/.credentials.json` directly.
3. Validate `expiresAt` with a 60-second safety buffer.
4. POST to `https://api.anthropic.com/api/oauth/usage` with the access
   token and headers:
   - `Authorization: Bearer {token}`
   - `anthropic-beta: oauth-2025-04-20`
   - `User-Agent: claude-code/2.0.32`
5. Return a `UsageData` struct with five_hour / seven_day / seven_day_opus
   percentages + reset timestamps + `needs_auth` flag.
6. Cache the response in a static `Mutex<Option<(Instant, ttl, data)>>`.
7. On HTTP 429 use the `Retry-After` header as the cache TTL.

**No in-app OAuth flow exists in either app.** Both rely on the user
running `claude /login` externally to obtain / refresh tokens. Maestro
just shows a "sleeping" tamagotchi when `needsAuth=true`; gmux shows
the "🔑 Token expired" badge.

---

## Frontend differences

| Aspect | maestro | gmux (current) |
|---|---|---|
| Tech | React + Zustand store | vanilla JS in inline `<script>` |
| Poll interval | 60s with exponential backoff to 5min on errors | 30s, no backoff |
| Visual | Tamagotchi pixel-art creature + bar | Coloured dot + label |
| Mood thresholds | <20 hungry, <40 bored, <60 content, <80 happy, ≥80 ecstatic | Same %s, mapped to red/orange/purple/blue/green |
| Click behaviour | Hover shows tooltip; clicking goes to a settings page | Click cycles daily/weekly/opus view |
| Auth-needed state | Tamagotchi sleeps; tooltip "Zzz... Run `claude` to wake me!" | Badge says "🔑 Token expired — claude /login" (alpha.16) |

### gmux already has parity in concept

The user said: *"the usage bar should follow whatever worked for maestro
right?"*. The answer is **yes — gmux's `usage.rs` is literally maestro's
file**. The maestro mood thresholds (the 20/40/60/80 % bands with
hungry→ecstatic mapping) are mirrored in gmux's alpha.16 dot-colour rule.

### Improvements maestro has that we could copy

1. **Exponential backoff on errors.** If the API returns 5xx or a network
   error, maestro doubles the poll interval up to a 5-minute cap. gmux
   keeps polling every 30s. Low priority — bandwidth is trivial.
2. **Ref-counted polling.** Maestro starts one global poller when the
   first component mounts and stops when the last unmounts. gmux just
   has an IIFE-scope interval. Doesn't matter for a single-window UI.
3. **Tamagotchi character.** Pixel-art creature with mood states. Pure
   UX flourish; could be added later.

---

## Why does the user see "Token expired" in gmux when `claude` CLI works?

This is the actual diagnostic question.

When `claude --print "say only the word OK"` succeeds on the CLI, the
Claude CLI auto-refreshes `~/.claude/.credentials.json`. But gmux uses
the **OLD value cached in its in-memory `USAGE_CACHE`** for up to 30s
after the failure. After 30s, the next poll will read the fresh file
and the badge updates.

There are TWO behaviours making this slow:
1. `CACHE_TTL_SECS = 30` — cache lasts 30s even for auth errors.
2. `CREDENTIAL_STORE_FAILED` atomic latch — if the keyring lookup ever
   failed (e.g. because there's no Secret Service entry), the app
   *permanently* skips the keyring for the rest of the process and only
   reads the file. This is correct here (file fallback works) but means
   on Linux the keyring path is dead after first failure.

**Recommended fix (alpha.16+):** when `needs_auth=true`, use a SHORTER
cache TTL (5 seconds) so a fresh `claude /login` is picked up within
~5s instead of ~30s. Maestro doesn't have this nuance because their
60s poll just hides the delay.

---

## What the user actually asked for

User: *"At the end of the day all it need to do is also access this page
<https://claude.ai/settings/usage> from the main browser"*

So the gmux usage badge should be **clickable to open the actual Claude
usage page in the user's default browser** as a fallback for when the
embedded API has gone stale. This is a small feature — just call
`tauri-plugin-shell`'s `open` command from JS.

User: *"one will require the opencode oauth system for actual
authentication, but the usage bar should follow whatever worked for
maestro right?"*

So they understand the OAuth flow is a separate larger project (akin to
opencode/qalcode's flow). They want the small win now: gmux's usage bar
behaves like maestro's, plus a click-to-open-usage-page link.

---

## Action items

- [ ] **alpha.16-dev6**: drop auth-error cache TTL to 5s so `claude
      /login` is picked up fast.
- [ ] **alpha.16-dev6**: clicking the usage badge (in either auth state)
      opens `https://claude.ai/settings/usage` in the default browser
      via `shell.open()`.
- [ ] **alpha.17 (future)**: implement opencode-style in-app OAuth flow:
      PKCE → open browser → user pastes code → exchange for tokens →
      write `~/.claude/.credentials.json`.
- [ ] **alpha.17+ (future, nice-to-have)**: add the maestro tamagotchi
      pixel-art character to the sidebar — purely visual.
- [ ] **alpha.17+ (future)**: exponential backoff on error in the
      frontend poll loop.

---

## References

- Maestro's `usage.rs`: `/tmp/maestro/src-tauri/src/commands/usage.rs`
- Maestro's `usageParser.ts`: `/tmp/maestro/src/lib/usageParser.ts`
- Maestro's `useUsageStore.ts`: `/tmp/maestro/src/stores/useUsageStore.ts`
- gmux's `usage.rs`: `app/src-tauri/src/commands/usage.rs` (identical to maestro)
- gmux's frontend usage code: `app/src/index.html` lines ~9128-9300
