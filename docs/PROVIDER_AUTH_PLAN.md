# Provider Auth — Integration Plan

How the Tauri app should expose qalcode2/opencode's auth + provider system to
the user without making them drop to a terminal. Companion to
`TESTING_CHECKLIST.md § Provider auth`.

---

## Current state (v3.5)

- Tauri **`check_auth`** command exists — returns `true` if
  `~/.local/share/opencode/auth.json` exists. Used by the first-launch
  tutorial only.
- No Settings UI in gmux exposes provider sign-in.
- Users must run `opencode auth login` from a terminal once, before launching
  agents through gmux.
- If `auth.json` is missing, agent creation appears to "work" but the agent
  will exit immediately (visible only in the agent's pane terminal output).

This works for the developer building gmux. It does NOT work for a third
party trying to use the desktop app — they'll see a blank pane and not
understand why.

---

## What qalcode2 exposes

From `~/projects/github_repos/qalcode2/packages/opencode/src/cli/cmd/auth.ts`:

| Subcommand | What it does | UI need |
|---|---|---|
| `opencode auth login` | Interactive OAuth flow per provider (Anthropic, OpenAI, Google, etc.) | Replace prompt UI with Tauri dialog |
| `opencode auth list` | List configured providers | Render as a list/grid |
| `opencode auth logout` | Remove a credential | Button per provider row |
| `opencode models` | List available models for each authed provider | Driver for the model picker in new-agent modal |
| `opencode stats` | Token / cost usage | Optional dashboard widget |

Auth data lives in `~/.local/share/opencode/auth.json` —
flat JSON of `{ [providerID]: { type: "oauth"|"api", ... } }`.

Each provider also has env-var fallbacks (e.g. `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`) — opencode reads those automatically; the UI should display
which env vars are active so users know they're authed without needing to
log in.

---

## Plan: v3.6 Settings → Providers panel

### 1. New Tauri commands

Add to `app/src-tauri/src/lib.rs`:

```rust
#[tauri::command]
fn list_providers() -> Result<String, String> {
    // Spawn `opencode auth list --json` (if --json is supported; otherwise
    // parse the human-readable output). Return the JSON string.
    let out = std::process::Command::new("opencode")
        .args(["auth", "list", "--json"])
        .output()
        .map_err(|e| e.to_string())?;
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

#[tauri::command]
fn login_provider(provider_id: String) -> Result<String, String> {
    // Open a new terminal pane in tmux running `opencode auth login <id>`.
    // OAuth flow prints a URL the user can click; the CLI exits when complete.
    // After completion, fire an event so the UI can re-list providers.
    // ...
}

#[tauri::command]
fn logout_provider(provider_id: String) -> Result<String, String> {
    let out = std::process::Command::new("opencode")
        .args(["auth", "logout", &provider_id])
        .output()
        .map_err(|e| e.to_string())?;
    Ok(format!("logout {}: {}", provider_id, out.status))
}

#[tauri::command]
fn list_models() -> Result<String, String> {
    // `opencode models --json` (or parse text)
    // Used by the new-agent modal to populate the Model dropdown dynamically.
}
```

### 2. Settings UI block

Add a "Providers" tab to the Options modal (next to Layout / Style / Hotkeys):

```
┌───────────────────────────────────────────────────────────┐
│ Anthropic       Claude Sonnet/Opus/Haiku       [✓ authed] │ [logout]
│ OpenAI          GPT-4o / o3 / o4               [⚠ no key] │ [connect]
│ Google          Gemini 2.5 Pro                 [env: GOOGLE_API_KEY ✓] │
│ DeepSeek        deepseek-r1                    [⚠ no key] │ [connect]
│ Local / Ollama  whatever you have running      [auto-detect] │
└───────────────────────────────────────────────────────────┘
```

- **Connect** button → invokes `login_provider(id)`. Backend spawns
  `opencode auth login <id>` in a new tmux window. opencode's OAuth flow
  prints a URL; the UI surfaces it via `xdg-open` so the user just clicks.
- **Logout** → confirm dialog → `logout_provider(id)` → refresh.
- Polled refresh of provider state every 5s while the panel is open.

### 3. First-launch wizard

When `check_auth` returns false on first launch, show a single-step modal:

> **Connect a provider to use AI agents**
>
> [Anthropic Claude]  [OpenAI GPT]  [Google Gemini]
>
> Or skip — you can use the Terminal agent type without any provider.

Each button → `login_provider`. After completion → close wizard, refresh
provider list, allow agent creation.

### 4. Agent-creation interlock

In `createAgent()` (already in `ui/v3/index.html`):

```js
if (type !== 'terminal' && !window._gmuxAuthed) {
  toast('⚠️ Connect a provider first — Settings → Providers');
  openOptionsPanel('providers');
  return;
}
```

`window._gmuxAuthed` set by a Tauri event emitted whenever provider list
changes.

---

## OAuth flow details (for each provider)

### Anthropic (Claude)
- `opencode auth login anthropic` opens browser to console.anthropic.com OAuth
- Returns API key, stored in `auth.json` as `{type:"oauth", refresh, access, expires}`
- Browser-opening uses `xdg-open` on Linux, `open` on macOS, `start` on Windows

### OpenAI
- `opencode auth login openai` — opens platform.openai.com auth
- Stores API key (`{type:"api", key}`)

### Google (Gemini)
- `opencode auth login google` — Google OAuth flow
- May need a project ID; surface that as a follow-up prompt

### Local (Ollama / LM Studio)
- No auth — just detect that `ollama serve` is up on :11434
- Show as "auto-detected" if reachable, else "not running"

---

## Edge cases

- **opencode binary missing** — `list_providers` returns an error; Settings
  panel shows "opencode not installed" with `curl bun.sh/install` snippet.
- **Network down during OAuth** — opencode CLI hangs; we should timeout
  after 90s and surface an error.
- **Token expired** — `check_auth` shows authed but agent fails on launch.
  Detect by tailing the new agent's pane output for known error strings
  ("authentication failed", "invalid_token") in the first 5s, then prompt
  re-login.
- **Multi-user machines** — `auth.json` is per-user. No special handling
  needed; warn in docs that gmux runs as $USER and uses $USER's creds.

---

## What this is NOT trying to be

- Not a credential manager — opencode owns `auth.json`, we just call its CLI.
- Not a model marketplace — model list comes from opencode's `models.dev`
  registry, not our own list.
- Not a per-agent auth override — one auth.json per machine, period. If you
  need different keys per agent, use env vars at agent launch time
  (`open_agent` could accept an `env: HashMap<String,String>` arg in the
  future).

---

## Priority

**Must-have for first external user:**
- `list_providers` Tauri command + provider list in Settings
- `login_provider` that opens a terminal pane with the OAuth flow
- `check_auth`-driven first-launch wizard
- Agent-creation interlock

**Nice-to-have:**
- `list_models` driving the dropdown dynamically (currently hardcoded)
- Stats / cost widget
- Per-provider quota warnings

**Not now:**
- BYO custom provider registry
- SSO integration
- Hardware-key auth (yubikey)