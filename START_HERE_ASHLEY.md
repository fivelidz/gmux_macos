# 👋 Hi Ashley — How to use your new coding setup

This is written super simply. Just follow the pictures-in-words. You can't break
anything by trying.

---

## 🟣 1. Open iTerm (your terminal)

**iTerm** is a window where you type commands. Think of it like a chat box for
your computer.

- Press **Cmd (⌘) + Space**, type **`iTerm`**, press **Return**.
- A window opens where you can type. 🎉

That's it. iTerm is just the window everything else lives in.

> *(We tried "Ghostty" first but it needs a newer macOS than this Mac has, so we
> use iTerm instead — it does the exact same job.)*

---

## 📁 2. Your projects live in one folder

All your coding work goes in **one place**:

```
/Users/ashleychapman-davies/projects
```

Inside Ghostty, you can jump there any time by typing:

```
proj
```
…and pressing **Return**. (`proj` is a magic shortcut word we set up for you.)

To **see what's in the folder**, type:
```
ls
```
You'll see your projects like `mosman-dry-eye-website`, `optometry-pms`, etc.

To **go into one**, type `cd` then the name. Example:
```
cd mosman-dry-eye-website
```
(Tip: type the first few letters then press **Tab** — it finishes the name for you.)

To **go back out** to the projects folder:
```
proj
```

> 🧠 Remember: `proj` = go to projects. `ls` = look around. `cd name` = go inside.

---

## 🤖 3. Talk to the AI coder (qalcode)

**qalcode** is your AI helper that can write and change code by talking to it —
exactly like talking to me right now, but inside Ghostty.

### To start it:
1. First go into the project you want to work on (see step 2). For example:
   ```
   proj
   cd mosman-dry-eye-website
   ```
2. Then type:
   ```
   qalcode
   ```
   and press **Return**.

### The very first time only — log in
The first time, it will ask you to **log in to Claude**. Follow the on-screen
prompt (it opens a web page to sign in). You only do this **once**. After that it
remembers you.

### Then just talk to it
A box appears. **Type what you want in plain English** and press Return. Examples:
- *"What files are in this project?"*
- *"Add a contact form to the home page."*
- *"Fix the spelling mistakes in README.md."*

The AI will think, then do it. You watch it work.

### Handy keys while it's open
- **Tab** — switches the AI's "mode" (e.g. careful planning vs. just-do-it).
- **Type `/help`** — shows what else you can do.
- To **quit**, press **Esc** a couple of times, or close the iTerm tab.

> 💡 You always **pick the folder first** (step 2), **then** run `qalcode`. The AI
> only works inside the folder you started it in. That keeps things tidy and safe.

---

## 🧠 4. The "memory" — how the AI remembers things

The AI keeps notes about your projects so it doesn't forget what you've been doing.

- It **automatically** remembers things as you work — you don't have to do anything.
- If you want it to remember something on purpose, just **tell it**:
  *"Remember that the client's brand colour is dark green."*
- Next time you open qalcode in that project, it can recall those notes.

You don't need to manage this. Just know: **the more you tell it, the more it
remembers.** Talk to it like a colleague who takes notes.

---

## 🖥️ 5. gmux — run several AIs at once and watch them

**gmux** lets you run **more than one AI helper at the same time** and see what
each one is doing — like a control room. It works right in the terminal.

You don't need this to start. But when you want it:

```
gmux attach
```
This opens a **split-screen workspace** (called tmux). Inside it:
- **Ctrl-a then "** — splits the screen so you can run a *second* qalcode
- **Ctrl-a then arrow keys** — move between the splits
- **the mouse works too** — click a split to focus it, scroll to read history

To see a quick list of what's running, in a normal terminal type:
```
gmux status
```
…and it prints each AI helper and what it's up to.

> 🧠 Think of it like this: **iTerm** is one window. **gmux attach** turns it into
> several windows side-by-side, each able to run its own AI. **gmux status** is the
> bird's-eye view.

To leave the split-screen without closing it: **Ctrl-a then d** ("detach").
Come back any time with `gmux attach`.

---

## ✅ The whole thing in 4 lines

```
1. Open iTerm              (Cmd+Space → "iTerm")
2. proj                    (go to your projects)
3. cd some-project-name    (go into one)
4. qalcode                 (start talking to the AI)
```

That's it. You're coding. 🚀

**Want multiple AIs at once?**  →  `gmux attach`  (then `Ctrl-a "` to split)

---

### If something looks stuck
- Close the iTerm window and open a fresh one.
- Type `proj` to get back home.
- If qalcode won't start, type `qalcode --help` to check it's there.
- Still stuck? fivelidz can see your Mac remotely and help.

---

### 🔑 First-time setup (do this once)
The very first time you run `qalcode`, it asks you to **log in to Claude**:
1. Type `qalcode` and press Return.
2. It shows a login screen — choose **Anthropic / Claude** and follow the prompt
   (it opens a web page to sign in, or asks for an API key).
3. Once you're logged in, it remembers you forever. You won't see this again.
