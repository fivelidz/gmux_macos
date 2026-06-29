# 👋 Hi Ashley — How to use your new coding setup

This is written super simply. Just follow the pictures-in-words. You can't break
anything by trying.

---

## 🟣 1. Open Ghostty (your terminal)

**Ghostty** is a window where you type commands. Think of it like a chat box for
your computer.

- Press **Cmd (⌘) + Space**, type **`Ghostty`**, press **Return**.
- A dark window opens. **It already starts inside your `projects` folder.** 🎉

That's it. Ghostty is just the window everything else lives in.

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
- To **quit**, press **Esc** a couple of times, or close the Ghostty tab.

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

## 🖥️ 5. gmux (the fancy dashboard) — *optional, later*

**gmux** is a bigger app with a visual dashboard that shows what your AI helpers
are doing — like a control room. **You don't need it to start coding.** Steps 1–4
above are everything you need for real work today.

We're still finishing gmux for your Mac. When it's ready, you'll open it like any
app (Cmd+Space → type `gmux`). Until then, **just use Ghostty + qalcode** — that's
a complete, working coding system.

---

## ✅ The whole thing in 4 lines

```
1. Open Ghostty            (Cmd+Space → "Ghostty")
2. proj                    (go to your projects)
3. cd some-project-name    (go into one)
4. qalcode                 (start talking to the AI)
```

That's it. You're coding. 🚀

---

### If something looks stuck
- Close the Ghostty window and open a fresh one.
- Type `proj` to get back home.
- If qalcode won't start, type `qalcode --help` to check it's there.
- Still stuck? fivelidz can see your Mac remotely and help.
