/* =====================================================================
   data.js — data layer for the agent activity dashboard.

   Sources, in priority order:
     1. live   — /tmp/gmuxtest-*.json (when served behind a tiny proxy)
     2. mock   — ../dummy_ui/data/*.json (the existing dummy data)

   Falls back automatically. The dropdown in the topbar lets the user pin
   a source.

   Public API:
     DATA.start({ source: 'auto' })
     DATA.stop()
     DATA.on(key, fn)         // key: agents | activity | files | memories | ready | source
     DATA.agents              // {pane_id: agent}
     DATA.activity            // [event, ...]   newest first
     DATA.files               // {abs_path: file}
     DATA.memories            // [memory, ...]
     DATA.source              // 'live' | 'mock'
   ===================================================================== */

window.DATA = (function () {
  const subs = {};
  const state = {
    agents: {},
    activity: [],
    files: {},
    memories: [],
    source: null,
    ready: false,
    paused: false,
    requestedSource: 'auto',
    singleAction: false,    // v4.5: debug mode — one op per agent at a time
    _lastEventId: null,
    _roundRobinIdx: 0,      // v4.5: which agent gets the single active op
  };

  // candidate URL pairs
  const SOURCES = {
    live: {
      agents:   '/tmp/gmuxtest-pane-state.json',
      activity: '/tmp/gmuxtest-activity.json',
      files:    '/tmp/gmuxtest-files.json',
      memories: '/tmp/gmuxtest-memory.json',
    },
    mock: {
      agents:   '../dummy_ui/data/agents.json',
      activity: '../dummy_ui/data/activity.json',
      files:    '../dummy_ui/data/files.json',
      memories: '../dummy_ui/data/memories.json',
    },
  };

  function on(key, fn) {
    (subs[key] = subs[key] || []).push(fn);
    if (key !== 'ready' && key !== 'source' && state.ready && state[key] !== undefined) {
      try { fn(state[key]); } catch (e) { console.error(e); }
    }
  }
  function emit(key) {
    (subs[key] || []).forEach(fn => { try { fn(state[key]); } catch (e) { console.error(e); } });
  }

  async function tryFetch(url) {
    try {
      const r = await fetch(url, { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  /** v4.3 — merge two object maps: incoming takes precedence on shared keys,
   *  but any key only in the current map is preserved (synthetic records
   *  added by seedActiveOps / evolveMock survive the next poll). */
  function mergePreserveSynthetic(current, incoming) {
    if (!current || !Object.keys(current).length) return { ...incoming };
    const out = { ...current };
    for (const k of Object.keys(incoming)) {
      // For files, preserve our bumped touch counters if they're higher
      const cur = current[k];
      const inc = incoming[k];
      if (cur && inc && typeof cur === 'object' && typeof inc === 'object') {
        out[k] = { ...inc };
        // file-style counters: keep the max of incoming vs current
        ['touches_5m','touches_30m','touches_1h'].forEach(f => {
          if (typeof cur[f] === 'number') {
            out[k][f] = Math.max(cur[f] || 0, inc[f] || 0);
          }
        });
        // preserve `agents` union for file records
        if (Array.isArray(cur.agents) && Array.isArray(inc.agents)) {
          out[k].agents = [...new Set([...inc.agents, ...cur.agents])];
        }
      } else {
        out[k] = inc;
      }
    }
    return out;
  }

  async function probeSource() {
    if (state.requestedSource === 'live') return 'live';
    if (state.requestedSource === 'mock') return 'mock';
    // auto: prefer live if the agents file exists
    const live = await tryFetch(SOURCES.live.agents);
    return live ? 'live' : 'mock';
  }

  async function loadAll() {
    const src = await probeSource();
    if (src !== state.source) {
      state.source = src;
      emit('source');
    }
    const urls = SOURCES[src];

    const [a, ev, f, m] = await Promise.all([
      tryFetch(urls.agents),
      tryFetch(urls.activity),
      tryFetch(urls.files),
      tryFetch(urls.memories),
    ]);

    if (a) {
      // agents may be wrapped: { agents: {...} } OR direct map
      // v4.3 — MERGE instead of replace, preserving anything seedActiveOps()
      // or evolveMock() added since the last poll. Otherwise the 2s poll wipes
      // synthetic agent/file records and the chain disappears for 1-2s every
      // cycle (= the "missing lines" bug).
      const incoming = a.agents || a;
      state.agents = mergePreserveSynthetic(state.agents, incoming);
      Object.values(state.agents).forEach(synthesiseTodoItems);
      emit('agents');
    }
    if (ev) {
      // v4.3 — same merge logic for activity: keep seeded/evolve events that
      // aren't in the file yet
      const arr = ev.events || ev;
      const fileIds = new Set(arr.map(e => e.id));
      const seededNotInFile = state.activity.filter(e => !fileIds.has(e.id) && (e.id?.startsWith('seed_') || e.id?.startsWith('evo_')));
      const merged = [...arr, ...seededNotInFile];
      state.activity = merged.sort((x, y) => (y.ts || '').localeCompare(x.ts || ''));
      emit('activity');
    }
    if (f) {
      const incoming = f.files || f;
      state.files = mergePreserveSynthetic(state.files, incoming);
      emit('files');
    }
    if (m) {
      const arr = m.memories || m;
      state.memories = Array.isArray(arr) ? arr : Object.values(arr || {});
      emit('memories');
    }

    if (!state.ready) {
      state.ready = true;
      emit('ready');
    }
  }

  /* -------- live mock evolution (only when src === 'mock') --------
     v4.2 — much more aggressive. Two functions:
       evolveMock()    runs every ~700ms, synthesises 1 new op on a random pane
       seedActiveOps() called from start() and every ~4s, guarantees every
                       agent has at least one tool_start without matching
                       tool_end (so the canvas always has visible activity)
  */

  // Stable per-pane folder + file pools so the same agent keeps editing
  // a coherent set of files instead of random new ones every tick.
  // v4.4 — pane IDs are now #N (not %N) to match tmux display convention
  const PANE_FILE_POOLS = {
    '#1': ['src/auth/auth.py', 'src/voice/daemon.py', 'src/status/bar.py'],
    '#2': ['src/compositor/main.cpp', 'src/overlay/layer.cpp', 'src/compositor/renderer.cpp'],
    '#3': ['src/components/Rail.tsx', 'src/components/FlowChart.tsx', 'src/theme/index.ts'],
    '#4': ['src/gesture-engine.js', 'src/main.js', 'src/exports/scanner.ts'],
    '#5': ['dummy_ui/index.html', 'dummy_ui/css/panel.css', 'dummy_ui/js/app.js'],
    '#6': ['src/voice/voice_router.py', 'src/voice/daemon.py', 'src/status/session_tracker.py'],
    '#7': ['eval/queries.json', 'eval/results.json', 'src/lawyer/agent.py'],
    '#8': ['ram_tracker.py', 'scripts/install.sh', 'tests/test_ram.py'],
  };
  const TOOLS = ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep'];

  function pickFileForPane(pane) {
    const pool = PANE_FILE_POOLS[pane] || ['src/main.py'];
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function makeFileRecordIfMissing(relPath, pane, ts) {
    const absPath = `/home/fivelidz/projects/gmux/${relPath}`;
    if (!state.files[absPath]) {
      state.files[absPath] = {
        path: absPath, rel_path: relPath,
        touches_5m: 0, touches_30m: 0, touches_1h: 0,
        agents: [], last_touch_ts: ts, last_writer: pane,
        is_hot: false, is_conflict: false, is_god_node: false, callers: 0,
      };
    }
    const fr = state.files[absPath];
    if (!fr.agents.includes(pane)) fr.agents.push(pane);
    fr.last_touch_ts = ts;
    return fr;
  }

  function evolveMock() {
    if (state.source !== 'mock') return;
    if (state.singleAction) return;   // v4.5: single-action mode disables random evolution
    if (!Object.keys(state.agents).length) return;

    const paneIds = Object.keys(state.agents);
    const pane = paneIds[Math.floor(Math.random() * paneIds.length)];
    const agent = state.agents[pane];
    if (!agent) return;

    const tool = TOOLS[Math.floor(Math.random() * TOOLS.length)];
    const file = pickFileForPane(pane);

    const now = new Date().toISOString();
    const id = 'evo_' + Date.now() + '_' + Math.floor(Math.random() * 1000);

    const evt = {
      id, ts: now, pane_id: pane, agent_name: agent.window_name,
      kind: 'tool_start', tool, args: { file_path: file },
      duration_ms: null, result: null,
    };
    state.activity.unshift(evt);

    // ~40% chance of immediate completion (leaves ~60% as still-active)
    if (Math.random() > 0.6) {
      const dur = 5 + Math.floor(Math.random() * 200);
      // v4.3 — Write/Edit ops carry +N/-N line deltas (code change log)
      let deltas = {};
      if (tool === 'Write') {
        deltas = { lines_added: 5 + Math.floor(Math.random() * 80), lines_removed: 0 };
      } else if (tool === 'Edit') {
        deltas = { lines_added: 1 + Math.floor(Math.random() * 20), lines_removed: Math.floor(Math.random() * 15) };
      }
      state.activity.unshift({
        ...evt, id: id + '_end', kind: 'tool_end',
        duration_ms: dur, result: Math.random() > 0.95 ? 'error' : 'ok',
        ...deltas,
      });
    }

    // bump file touch counters
    const fr = makeFileRecordIfMissing(file, pane, now);
    fr.touches_5m++; fr.touches_30m++; fr.touches_1h++;
    if (tool === 'Write' || tool === 'Edit') fr.last_writer = pane;
    if (fr.touches_5m >= 6) fr.is_hot = true;
    if (fr.agents.length >= 2) fr.is_conflict = true;

    if (state.activity.length > 500) state.activity.length = 500;

    emit('activity');
    emit('files');
  }

  /** v4.2 — guarantee every agent has at least one in-flight tool_start in
   *  the last 6 seconds. Without this, the default-agent flowchart can
   *  spend long stretches showing zero active edges.
   *
   *  v4.5 — when state.singleAction === true, exactly ONE agent has ONE
   *  in-flight op at any moment. We round-robin which agent it is every
   *  call. Before starting a new op for that agent, we complete any other
   *  in-flight ops (write a tool_end). This produces a clean, easy-to-read
   *  test view.
   */
  function seedActiveOps() {
    if (state.source !== 'mock') return;
    if (!Object.keys(state.agents).length) return;
    const nowMs = Date.now();
    const SIX_SEC = 6_000;
    const panes = Object.keys(state.agents);

    // v4.5 — SINGLE-ACTION MODE
    if (state.singleAction) {
      // 1. Complete any in-flight ops on any agent
      const completedIds = new Set(state.activity.filter(e => e.kind === 'tool_end').map(e => e.id.replace(/_end$/, '')));
      const inFlight = state.activity.filter(e =>
        e.kind === 'tool_start' && !completedIds.has(e.id)
      );
      inFlight.forEach(e => {
        const dur = 200 + Math.floor(Math.random() * 800);
        const tool = e.tool || '';
        let deltas = {};
        if (tool === 'Write') deltas = { lines_added: 5 + Math.floor(Math.random() * 60), lines_removed: 0 };
        else if (tool === 'Edit') deltas = { lines_added: 1 + Math.floor(Math.random() * 12), lines_removed: Math.floor(Math.random() * 8) };
        state.activity.unshift({
          ...e, id: e.id + '_end', kind: 'tool_end',
          ts: new Date().toISOString(),
          duration_ms: dur, result: 'ok', ...deltas,
        });
      });
      // 2. Pick the next agent (round-robin) and start ONE new op
      const pane = panes[state.singleActionAgentIdx % panes.length];
      state.singleActionAgentIdx = (state.singleActionAgentIdx + 1) % panes.length;
      const agent = state.agents[pane];
      if (agent) {
        const tool = TOOLS[Math.floor(Math.random() * TOOLS.length)];
        const file = pickFileForPane(pane);
        const now = new Date().toISOString();
        const id = 'sa_' + Date.now() + '_' + pane.replace(/[#%]/g,'');
        state.activity.unshift({
          id, ts: now, pane_id: pane, agent_name: agent.window_name,
          kind: 'tool_start', tool, args: { file_path: file },
          duration_ms: null, result: null,
        });
        const fr = makeFileRecordIfMissing(file, pane, now);
        fr.touches_5m++; fr.touches_30m++; fr.touches_1h++;
      }
      if (state.activity.length > 500) state.activity.length = 500;
      emit('activity');
      emit('files');
      return;
    }

    // Normal mode: guarantee every agent has an in-flight op
    panes.forEach(pane => {
      let hasInFlight = false;
      for (const e of state.activity) {
        if (e.pane_id !== pane) continue;
        const ts = new Date(e.ts).getTime();
        if (nowMs - ts > SIX_SEC) break;
        if (e.kind === 'tool_start') {
          const endId = e.id + '_end';
          const ended = state.activity.find(x => x.id === endId);
          if (!ended) { hasInFlight = true; break; }
        }
      }
      if (hasInFlight) return;

      const agent = state.agents[pane];
      const tool = TOOLS[Math.floor(Math.random() * TOOLS.length)];
      const file = pickFileForPane(pane);
      const now = new Date().toISOString();
      const id = 'seed_' + Date.now() + '_' + pane.replace(/[#%]/g,'');
      state.activity.unshift({
        id, ts: now, pane_id: pane, agent_name: agent.window_name,
        kind: 'tool_start', tool, args: { file_path: file },
        duration_ms: null, result: null,
      });
      const fr = makeFileRecordIfMissing(file, pane, now);
      fr.touches_5m++; fr.touches_30m++; fr.touches_1h++;
    });

    if (state.activity.length > 500) state.activity.length = 500;
    emit('activity');
    emit('files');
  }

  /* v4.1 — generate plausible todo items from window name + done/total counts.
     Stable per agent so they don't reshuffle on every poll. */
  const TODO_TEMPLATES = {
    doofing:        ['port phone-link AI to minirig', 'add bridge watchdog', 'webhook for whatsapp status', 'health endpoint', 'persist message CSV', 'reconnect logic on signal-cli crash', 'expose mojo over wireguard', 'docs for ops'],
    volkus:         ['refactor compositor', 'fix overlay z-index bug', 'theme tokens', 'gpu probe', 'wayland fallback'],
    ai_UI:          ['agent rail v2', 'flow chart pulse alignment', 'detail panel todos', 'theme: light-wood', 'copy-path button'],
    expose:         ['scan src/**/*.ts for unused exports', 'detect dead css', 'report json schema', 'cli args', 'tests for tree-shake'],
    UI_creation:    ['build memory panel prototype', 'wire to gmuxtest tauri', 'shared theme tokens', 'episodic view', 'semantic view', 'pin/share actions', 'integration guide', 'screenshot for README'],
    'voice-router': ['refactor voice_router.py', 'add streaming mode', 'tests for noisy input', 'docs'],
    'lawyer-prototype': ['eval harness', 'load fixture cases', 'baseline metric', 'compare to GPT-4o', 'write up findings', 'export to notion', 'final report'],
    ram_tracker:    ['fix psutil import', 'log rotation', 'add CPU tracking', 'dashboard widget'],
  };

  function synthesiseTodoItems(a) {
    if (Array.isArray(a.todo_items) && a.todo_items.length) return;
    const done  = a.todo_done  || 0;
    const total = a.todo_total || 0;
    if (!total) { a.todo_items = []; return; }
    const tpl = TODO_TEMPLATES[a.window_name] || [
      `${a.window_name || 'task'}: subtask 1`,
      `${a.window_name || 'task'}: subtask 2`,
      `${a.window_name || 'task'}: subtask 3`,
      'cleanup', 'tests', 'docs', 'review', 'ship',
    ];
    const items = [];
    for (let i = 0; i < total; i++) {
      items.push({ text: tpl[i % tpl.length], done: i < done });
    }
    a.todo_items = items;
  }

  function randomName() {
    const stems = [
      'router', 'handler', 'service', 'tracker', 'monitor',
      'parser', 'engine', 'manager', 'loader', 'config',
      'graph', 'cache', 'queue', 'worker', 'bridge',
    ];
    return stems[Math.floor(Math.random() * stems.length)];
  }

  // -------- public --------
  let pollHandle = null;
  let evolveHandle = null;
  let seedHandle = null;

  return {
    get agents()   { return state.agents; },
    get activity() { return state.activity; },
    get files()    { return state.files; },
    get memories() { return state.memories; },
    get source()   { return state.source; },
    get ready()    { return state.ready; },
    get paused()   { return state.paused; },

    on, emit,

    setSource(s) {
      state.requestedSource = s;
      loadAll();
    },
    pause(p) { state.paused = !!p; },

    /** v4.5 — single-action test mode. When ON, exactly ONE agent has ONE
     *  in-flight op at any time; agents are picked round-robin. */
    setSingleAction(on) {
      state.singleAction = !!on;
      state.singleActionAgentIdx = state.singleActionAgentIdx || 0;
      // Trigger an immediate seed so the UI updates right away
      setTimeout(seedActiveOps, 20);
    },
    get singleAction() { return state.singleAction; },

    async start({ source = 'auto', pollMs = 2000, evolveMs = 700, seedMs = 4000 } = {}) {
      state.requestedSource = source;

      // ── Tauri sub-window mode ──────────────────────────────────────────
      // When the dashboard is loaded as a Tauri webview (gmuxtest "dashboard"
      // window), the main Rust process broadcasts events every 1s. Subscribe
      // to them instead of fetching /tmp files. The browser dev path (port
      // 1900, `./serve.sh`) keeps using fetch+mock — the detection below is
      // explicitly false there.
      const isTauri = (typeof window !== 'undefined') && (
        !!window.__TAURI_INTERNALS__ ||
        !!(window.__TAURI__ && (window.__TAURI__.event || window.__TAURI__.core))
      );
      console.info('[data] Tauri webview detected:', isTauri,
                   '— __TAURI__:', !!window.__TAURI__,
                   '__TAURI_INTERNALS__:', !!window.__TAURI_INTERNALS__);

      // Show a tiny on-screen connection HUD (top-right corner) so you don't
      // have to open devtools just to verify the data path. Click it to copy
      // the current event counts to clipboard.
      window._gmuxDataHud = { gmuxState: 0, memory: 0, activity: 0, files: 0, lastError: '', tauri: isTauri };
      function _renderHud() {
        const h = window._gmuxDataHud;
        let el = document.getElementById('_gmux-data-hud');
        if (!el) {
          el = document.createElement('div');
          el.id = '_gmux-data-hud';
          el.style.cssText = 'position:fixed;top:4px;right:4px;z-index:9999;background:rgba(0,0,0,.7);color:#9cf;padding:4px 8px;border-radius:6px;font:11px monospace;line-height:1.4;cursor:pointer;border:1px solid rgba(255,255,255,.15);';
          el.title = 'gmux data feed — click to copy diagnostic';
          el.onclick = () => navigator.clipboard.writeText(JSON.stringify(window._gmuxDataHud, null, 2)).catch(()=>{});
          document.body.appendChild(el);
        }
        const dot = h.tauri ? (h.gmuxState ? '🟢' : '🟡') : '⚪';
        el.innerHTML = `${dot} ${h.tauri ? 'tauri' : 'mock'} · state:${h.gmuxState} mem:${h.memory} act:${h.activity} files:${h.files}` + (h.lastError ? `<br><span style="color:#f99">${h.lastError}</span>` : '');
      }
      _renderHud();
      window._renderHud = _renderHud;

      if (isTauri) {
        // Tauri 2 exposes the event module under window.__TAURI__.event when
        // `withGlobalTauri: true` is set in tauri.conf.json. If the page loads
        // before the runtime injection finishes, poll for up to 3s.
        let listen = null;
        for (let i = 0; i < 30 && !listen; i++) {
          listen = (window.__TAURI__ && window.__TAURI__.event && window.__TAURI__.event.listen) ||
                   (window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.event && window.__TAURI_INTERNALS__.event.listen) ||
                   null;
          if (!listen) await new Promise(r => setTimeout(r, 100));
        }
        if (!listen) {
          console.warn('[data] Tauri detected but no event.listen API — falling back to mock');
        } else {
          console.info('[data] subscribing to Tauri events …');
          state.source = 'tauri';
          emit('source');
          try {
            await listen('gmux-state', e => {
              try {
                window._gmuxDataHud.gmuxState++;
                const parsed = JSON.parse(e.payload);
                const incoming = parsed.agents || parsed;
                if (incoming && typeof incoming === 'object' && Object.keys(incoming).length) {
                  state.agents = mergePreserveSynthetic(state.agents, incoming);
                  Object.values(state.agents).forEach(synthesiseTodoItems);
                  emit('agents');
                  if (!state.ready) { state.ready = true; emit('ready'); }
                }
                window._renderHud && window._renderHud();
              } catch (err) {
                window._gmuxDataHud.lastError = 'gmux-state: ' + err.message;
                window._renderHud && window._renderHud();
                console.warn('[data] gmux-state parse', err);
              }
            });
            await listen('memory-update', e => {
              try {
                window._gmuxDataHud.memory++;
                const parsed = JSON.parse(e.payload);
                const arr = parsed.memories || parsed;
                state.memories = Array.isArray(arr) ? arr : Object.values(arr || {});
                emit('memories');
                window._renderHud && window._renderHud();
              } catch (err) { console.warn('[data] memory-update parse', err); }
            });
            await listen('activity-tick', e => {
              try {
                window._gmuxDataHud.activity++;
                const parsed = JSON.parse(e.payload);
                const arr = parsed.events || parsed;
                if (Array.isArray(arr)) {
                  state.activity = arr.sort((x, y) => (y.ts || '').localeCompare(x.ts || ''));
                  emit('activity');
                }
                window._renderHud && window._renderHud();
              } catch (err) { console.warn('[data] activity-tick parse', err); }
            });
            await listen('files-update', e => {
              try {
                window._gmuxDataHud.files++;
                const parsed = JSON.parse(e.payload);
                const incoming = parsed.files || parsed;
                // v3.6.4 — in Tauri (live) mode, take the incoming snapshot
                // verbatim. The previous mergePreserveSynthetic kept old
                // touch counters around forever via Math.max, so the panel
                // never showed live decay when ops aged past the rolling
                // window. The backend already computes 5m/30m/1h windows
                // correctly; trust those numbers.
                if (incoming && typeof incoming === 'object') {
                  state.files = { ...incoming };
                  emit('files');
                }
                window._renderHud && window._renderHud();
              } catch (err) { console.warn('[data] files-update parse', err); }
            });
            console.info('[data] Tauri listeners attached. Awaiting first gmux-state…');
            return;
          } catch (err) {
            console.warn('[data] Tauri listen() failed, falling back to fetch mode:', err);
          }
        }
      }

      await loadAll();

      if (pollHandle)   clearInterval(pollHandle);
      if (evolveHandle) clearInterval(evolveHandle);
      if (seedHandle)   clearInterval(seedHandle);

      pollHandle = setInterval(() => {
        if (!state.paused) loadAll().catch(() => {});
      }, pollMs);
      evolveHandle = setInterval(() => {
        if (!state.paused) evolveMock();
      }, evolveMs);
      // v4.2 — guarantee every agent has at least one in-flight op
      // v4.5 — single-action mode uses a longer cadence so each op is
      //        visible for a few seconds before the next agent takes over
      let lastSeed = 0;
      seedHandle = setInterval(() => {
        if (state.paused) return;
        const interval = state.singleAction ? 5500 : seedMs;
        if (Date.now() - lastSeed >= interval) {
          lastSeed = Date.now();
          seedActiveOps();
        }
      }, 500);   // poll every 500ms, but only fire on the desired cadence
      // and once immediately, so on load every agent is already active
      setTimeout(seedActiveOps, 50);
    },

    stop() {
      if (pollHandle)   clearInterval(pollHandle);
      if (evolveHandle) clearInterval(evolveHandle);
      if (seedHandle)   clearInterval(seedHandle);
      pollHandle = evolveHandle = seedHandle = null;
    },

    refresh() { return loadAll(); },
  };
})();
