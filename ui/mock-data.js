/**
 * shared/mock-data.js
 * Canonical mock data for all UI systems.
 * Mirrors the real /tmp/gmuxtest-pane-state.json schema exactly.
 * Also mirrors what the Tauri "gmux-state" event emits.
 *
 * Real schema (from lib.rs + monitor.py):
 * {
 *   "<pane_id>": {
 *     pane_id, window_index, window_name, state,
 *     has_ai, last_line, current_tool,
 *     todo_done, todo_total, session_name, sub_agent_permission
 *   }
 * }
 *
 * Extended mock adds: ram_mb, vram_mb, cpu_pct, token_in, token_out,
 *   model, tool_history, uptime_s — fields coming from ram_tracker integration.
 */

export const AGENT_STATES = ['idle','not_started','working','waiting','permission','sub_permission','done','error'];

export const STATE_COLOR = {
  idle:            '#4b5563',
  not_started:     '#4b5563',
  working:         '#22c55e',
  waiting:         '#ef4444',
  permission:      '#f97316',
  sub_permission:  '#f97316',
  done:            '#3b82f6',
  error:           '#ef4444',
};

export const STATE_LABEL = {
  idle:           'idle',
  not_started:    'off',
  working:        'working',
  waiting:        'waiting',
  permission:     '! approve',
  sub_permission: '^! approve',
  done:           'done',
  error:          'error',
};

export const STATE_PRIORITY = { permission:0, sub_permission:1, waiting:2, error:3, working:4, done:5, idle:6, not_started:7 };

/** Full mock pane state — 8 agents across 2 tmux sessions */
export const MOCK_PANES = {
  '%1': {
    pane_id: '%1', window_index: 1, window_name: 'volkus',
    state: 'working', has_ai: true,
    last_line: '  ✓ Writing src/gesture-engine.js',
    current_tool: 'write',
    todo_done: 6, todo_total: 8,
    session_name: 'gmux',
    sub_agent_permission: false,
    // Extended mock fields
    ram_mb: 1240, vram_mb: 180, cpu_pct: 34,
    token_in: 42800, token_out: 18300,
    model: 'claude-sonnet-4-5',
    tool_history: ['read','glob','read','write'],
    uptime_s: 847,
  },
  '%2': {
    pane_id: '%2', window_index: 2, window_name: 'planner',
    state: 'waiting', has_ai: true,
    last_line: 'Ready for your next instruction.',
    current_tool: null,
    todo_done: 3, todo_total: 5,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 780, vram_mb: 60, cpu_pct: 2,
    token_in: 31200, token_out: 9800,
    model: 'claude-sonnet-4-5',
    tool_history: ['bash','read','bash'],
    uptime_s: 1240,
  },
  '%3': {
    pane_id: '%3', window_index: 3, window_name: 'research',
    state: 'permission', has_ai: true,
    last_line: 'About to edit: src/main.rs — confirm?',
    current_tool: 'edit',
    todo_done: 2, todo_total: 4,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 540, vram_mb: 90, cpu_pct: 8,
    token_in: 110400, token_out: 44200,
    model: 'claude-opus-4-5',
    tool_history: ['glob','read','read','edit'],
    uptime_s: 3600,
  },
  '%4': {
    pane_id: '%4', window_index: 4, window_name: 'deepseek',
    state: 'working', has_ai: true,
    last_line: '  Scanning src/**/*.ts...',
    current_tool: 'glob',
    todo_done: 7, todo_total: 9,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 2140, vram_mb: 340, cpu_pct: 61,
    token_in: 230800, token_out: 88100,
    model: 'deepseek-r1',
    tool_history: ['bash','glob','read','bash','glob'],
    uptime_s: 290,
  },
  '%5': {
    pane_id: '%5', window_index: 5, window_name: 'deploy',
    state: 'done', has_ai: true,
    last_line: '✓ Deployment complete. Build passed.',
    current_tool: null,
    todo_done: 5, todo_total: 5,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 3420, vram_mb: 0, cpu_pct: 0,
    token_in: 43000, token_out: 12000,
    model: 'claude-haiku-4-5',
    tool_history: ['bash','bash','bash'],
    uptime_s: 4200,
  },
  '%6': {
    pane_id: '%6', window_index: 6, window_name: 'gemini',
    state: 'idle', has_ai: false,
    last_line: '',
    current_tool: null,
    todo_done: 0, todo_total: 0,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 220, vram_mb: 0, cpu_pct: 0,
    token_in: 0, token_out: 0,
    model: null,
    tool_history: [],
    uptime_s: 0,
  },
  '%7': {
    pane_id: '%7', window_index: 7, window_name: 'haiku',
    state: 'working', has_ai: true,
    last_line: '  Reading docs/GESTURES.md...',
    current_tool: 'read',
    todo_done: 1, todo_total: 3,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 890, vram_mb: 120, cpu_pct: 18,
    token_in: 15600, token_out: 4200,
    model: 'claude-haiku-4-5',
    tool_history: ['read','read'],
    uptime_s: 124,
  },
  '%8': {
    pane_id: '%8', window_index: 8, window_name: 'claude-3',
    state: 'error', has_ai: true,
    last_line: '✗ Error: exit code 1 — node build.js failed',
    current_tool: null,
    todo_done: 2, todo_total: 6,
    session_name: 'gmux',
    sub_agent_permission: false,
    ram_mb: 1800, vram_mb: 200, cpu_pct: 0,
    token_in: 99000, token_out: 38000,
    model: 'claude-3-5-sonnet',
    tool_history: ['bash','bash'],
    uptime_s: 600,
  },
};

/** Convert pane state JSON (as received from Tauri event) to sorted array */
export function panesArray(panesObj) {
  return Object.values(panesObj)
    .sort((a, b) => (STATE_PRIORITY[a.state] ?? 9) - (STATE_PRIORITY[b.state] ?? 9)
      || a.window_index - b.window_index);
}

/** Format RAM in MB to human string */
export function fmtRam(mb) {
  if (!mb) return '—';
  if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB';
  return mb + ' MB';
}

/** Format token count to human string */
export function fmtTokens(n) {
  if (!n) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return Math.round(n / 1000) + 'k';
  return String(n);
}

/** Format uptime in seconds to human string */
export function fmtUptime(s) {
  if (!s) return '—';
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm';
  return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
}

/** Get RAM percentage of a "high" threshold (3GB = 100%) */
export function ramPct(mb, max = 3072) {
  return Math.min(100, Math.round((mb / max) * 100));
}

/** Slowly evolve mock state for realistic demo animation */
export function startMockEvolution(panesObj, onUpdate) {
  const TOOLS = { bash: 'bash', read: 'read', glob: 'glob', write: 'write', edit: 'edit' };
  const TOOL_LIST = Object.values(TOOLS);

  return setInterval(() => {
    const ids = Object.keys(panesObj);
    const id = ids[Math.floor(Math.random() * ids.length)];
    const p = panesObj[id];

    // RAM drift ±20MB
    if (p.ram_mb) p.ram_mb = Math.max(100, p.ram_mb + (Math.random() - 0.48) * 40);
    // CPU drift
    if (p.state === 'working') p.cpu_pct = Math.min(99, Math.max(5, p.cpu_pct + (Math.random() - 0.4) * 12));

    // State transitions (low probability)
    if (p.state === 'working' && Math.random() > 0.80) {
      p.state = Math.random() > 0.55 ? 'waiting' : 'done';
      p.current_tool = null;
      p.cpu_pct = 0;
    } else if (p.state === 'waiting' && Math.random() > 0.85) {
      p.state = 'working';
      p.current_tool = TOOL_LIST[Math.floor(Math.random() * TOOL_LIST.length)];
      p.todo_done = Math.min(p.todo_total, p.todo_done + 1);
    } else if (p.state === 'done' && Math.random() > 0.95) {
      p.state = 'idle';
      p.cpu_pct = 0;
    } else if (p.state === 'working') {
      // Token drift
      if (p.token_in) p.token_in += Math.floor(Math.random() * 400);
      if (p.token_out) p.token_out += Math.floor(Math.random() * 150);
      // Tool change
      if (Math.random() > 0.92) {
        const t = TOOL_LIST[Math.floor(Math.random() * TOOL_LIST.length)];
        p.current_tool = t;
        p.tool_history = [...(p.tool_history || []).slice(-4), t];
      }
    }

    onUpdate({ ...panesObj });
  }, 2200);
}

/** Try to connect to real Tauri backend, fall back to mock */
export async function initDataSource(panesObj, onUpdate) {
  try {
    // Check if we're inside Tauri
    if (window.__TAURI_INTERNALS__) {
      const { listen } = await import('https://cdn.jsdelivr.net/npm/@tauri-apps/api@2/event');
      // Listen to real gmux-state events
      await listen('gmux-state', (event) => {
        try {
          const real = JSON.parse(event.payload);
          // Merge real data fields onto our mock (preserves extended fields)
          for (const [id, pane] of Object.entries(real)) {
            if (panesObj[id]) {
              Object.assign(panesObj[id], pane);
            }
          }
          onUpdate({ ...panesObj });
        } catch(e) { /* ignore parse errors */ }
      });
      console.log('[gmux] Connected to Tauri backend — live data');
      return 'tauri';
    }
  } catch(e) { /* not in Tauri */ }

  // Browser mode — use mock evolution
  console.log('[gmux] Browser mode — mock data');
  startMockEvolution(panesObj, onUpdate);
  return 'browser';
}
