# Avatar System (archived from v3.1)

Extracted from `ui/v3/index.html` on 2026-05-12 because it was too distracting
for daily use. Kept here for future revival — to re-enable, follow the
"Reintegration" section below.

---

## What it was

A small animated avatar in the chat side panel + a larger one in the bottom-right
corner during fullscreen pane mode. The avatar reflected the agent's state:

- **working** → green, bouncing
- **waiting** → red, slow breathing
- **permission** → orange, fast flashing (demand attention)
- **done** → purple, one-shot spin
- **error** → red, no animation
- **idle** → grey, dim breathing

Four rendering modes, picked via Options panel:

| Mode | Visual |
|------|--------|
| `off` | hidden entirely |
| `crab` | full SVG crab from the aquarium (eyes, claws, gradient body) |
| `cat` | ASCII art cat in monospace, state-based face: `(o.o)`, `(-.-)`, `(@.@)` etc |
| `dot` | coloured circle with window index inside |

Stored selection in `localStorage['gmux.avatarMode']`.

---

## Files in this folder

- `avatar-system.css` — the `#cp-avatar*`, `#fs-avatar*`, animations
- `avatar-system.html` — the two DOM elements (chat-panel + fullscreen overlay)
- `avatar-system.js` — `AVA_COLORS`, `AVA_LABELS`, `_blend`, `makeCrabSVG`, `makeCatAscii`, `updateAvatar`, `setAvatarMode`
- `options-dropdown.html` — the `<select id="opts-avatar">` snippet for the Options panel

---

## Reintegration steps

If you want it back, edit `ui/v3/index.html`:

### 1. CSS
Paste contents of `avatar-system.css` into the main `<style>` block (anywhere near
the other UI element styles works — original location was right after the chat
panel CSS).

### 2. HTML — chat panel
Inside `<div id="chat-panel">`, just after the `cp-head` div and before
`#cp-summary`, paste the chat avatar block from `avatar-system.html`.

### 3. HTML — fullscreen overlay
Just before `<!-- Graph panel -->`, paste the fullscreen avatar block from
`avatar-system.html`.

### 4. JS
Paste contents of `avatar-system.js` into the main `<script>` block. Anywhere
above `renderChatPanel` works. Then add this one line inside `renderChatPanel`,
right at the end:
```js
  updateAvatar(p);
```
And at startup, restore the dropdown's value:
```js
const _avatarSel = $('opts-avatar');
if (_avatarSel) _avatarSel.value = localStorage.getItem('gmux.avatarMode') || 'crab';
```

### 5. Options dropdown
Paste contents of `options-dropdown.html` into the Layout tab of the Options
panel — near the gesture-sensitivity slider works well.

---

## Why we removed it

User feedback in the v3.2 redesign session:

> "drop the avatar system... I want clear documentation..."

The avatar competed with the state dot, the status chip, and the pane border
glow for attention. Removing it produced a cleaner chat panel where the
message stream is the main focal point.

Pinned for revival if the aquarium becomes a separate window — the crab SVG
generator is genuinely good and can be reused there.
