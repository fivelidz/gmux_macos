# Installing the QTK plugin on macOS — Instructions for a Claude Agent

> **You are a Claude coding agent.** Install **QTK** (Qalarc Token Killer), an
> OpenCode plugin that compresses tool outputs to save tokens, into the qalcode
> install. **This is optional** — qalcode runs fine without it. Do this after
> qalcode itself is working ([`../qalcode2/INSTALL_FOR_CLAUDE.md`](../qalcode2/INSTALL_FOR_CLAUDE.md)).

---

## What QTK is

QTK silently compresses noisy tool outputs (`git status`, `ls -la`, `rg`,
`pytest`, `cargo test`, `Read`/`Grep`/`Glob`, `kubectl`, `terraform plan`, JUnit
XML, …) **before they reach the model's context window**. No LLM, no prompt
injection, ~99% reduction on the worst offenders, sub-millisecond latency, and
zero change to how you use the agent. Pure token/cost savings.

- **Public repo:** https://github.com/qalarc/QTK
- **npm package:** `@qalarc/qtk-plugin`
- **Integration doc (authoritative):** https://github.com/qalarc/QTK/blob/main/docs/INTEGRATION.md
- Requires: Bun ≥ 1.3.5 (already installed for qalcode), OpenCode ≥ 1.1.21
  (qalcode satisfies this).

> Context: QTK is an OpenCode-specific sibling of **[RTK](https://rtk-ai.app)**
> (Rust Token Killer). If your friend uses other agents too (Claude Code, Cursor,
> etc.), RTK is the broader cross-tool option. For qalcode/OpenCode, QTK is the
> in-process plugin.

---

## Install — npm method (recommended)

QTK is a plain OpenCode plugin. Install it into the qalcode project, then
register it in the config.

```bash
# $OC = the qalcode OpenCode project root (from the qalcode install step):
OC="$HOME/qalcode/packages/opencode"
cd "$OC"

# Add the published plugin:
bun add @qalarc/qtk-plugin
```

Then register it in your global config so it loads in every project. Edit
`~/.config/opencode/opencode.jsonc` and set the `plugin` array:

```jsonc
{
  "plugin": [
    "@qalarc/qtk-plugin"
  ]
}
```

> The bundled settings in this repo ship with `"plugin": []` (QTK off). Change it
> to the line above to turn QTK on. If you applied those settings already, just
> edit that one line.

Restart qalcode. On startup you should see something like:
```
QTK active — N compressors registered
```

✅ **Checkpoint:** launch `qalcode`, confirm the "QTK active" banner appears.

---

## Optional — the Rust sidecar (extra compressors)

QTK works without it, but a small Rust sidecar binary adds structured
compressors (terraform/kubectl/cargo-json/junit). Pick the macOS artifact:

```bash
OC="$HOME/qalcode/packages/opencode"
mkdir -p "$OC/.opencode/plugin"

case "$(uname -sm)" in
  "Darwin x86_64") ARTIFACT=qtk-core-x86_64-apple-darwin ;;   # Intel Mac
  "Darwin arm64")  ARTIFACT=qtk-core-aarch64-apple-darwin ;;  # Apple Silicon
esac
curl -L -o "$OC/.opencode/plugin/qtk-core" \
    "https://github.com/qalarc/QTK/releases/latest/download/$ARTIFACT"
chmod +x "$OC/.opencode/plugin/qtk-core"
```

(With the npm install you do **not** need to download `qtk.js` — only the sidecar
binary above, and only if you want the extra structured compressors.)

✅ **Checkpoint (optional):** `qtk-core` is on disk and executable.

---

## Verify savings

After using qalcode for a bit, QTK can report what it saved:

```bash
qtk gain        # if the qtk CLI is on PATH; otherwise see the repo docs
```

For everything else (filter DSL, architecture, troubleshooting) read the repo's
`docs/INTEGRATION.md` and `README.md`.
