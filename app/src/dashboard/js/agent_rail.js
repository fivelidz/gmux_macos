/* =====================================================================
   agent_rail.js v3 — left rail: agent list with show/hide checkboxes.

   v3 changes:
   - Checkbox click is now SEPARATE from name click (point #11)
   - Each row shows mini-stats (RAM, todos) (point #8)
   - Active gmux pane gets a 📌 marker if follow-active mode is on
   - Filter by session (point #12)
   ===================================================================== */

window.RAIL = (function () {
  const { esc } = UTIL;

  let listEl;
  const state = {
    watching: null,
    shown: new Set(),
    checked: new Set(),         // bulk-op tick marks (independent of shown)
    sessionFilter: '*',         // '*' = all sessions
    followActive: false,
  };

  function init() {
    listEl = document.getElementById('agent-list');

    document.getElementById('btn-select-all').addEventListener('click', () => {
      visibleAgents().forEach(([p]) => state.shown.add(p));
      render(); APP.notifyChange();
    });
    document.getElementById('btn-clear-all').addEventListener('click', () => {
      state.shown.clear();
      render(); APP.notifyChange();
    });
    // v4: sub-agent UI hidden (point #11) — qalcode2 will provide parent_id
    // when integrated for real. Manual grouping not needed for now.
    // Buttons removed from index.html; SUBAGENTS module kept for future use.

    document.getElementById('rail-collapse').addEventListener('click', () => {
      document.body.classList.toggle('rail-collapsed');
    });

    DATA.on('agents', () => {
      // First load: show all + watch the first
      if (state.watching === null) {
        const ids = Object.keys(DATA.agents);
        if (ids.length) {
          state.watching = ids[0];
          ids.forEach(p => state.shown.add(p));
          APP.notifyChange();
        }
      }
      // Follow-active: switch to whichever pane is currently active in gmux
      if (state.followActive) {
        const active = Object.values(DATA.agents).find(a => a.is_active);
        if (active && active.pane_id !== state.watching) {
          state.watching = active.pane_id;
          state.shown.add(active.pane_id);
          APP.notifyChange();
        }
      }
      // Update session dropdown options
      updateSessionOptions();
      render();
    });
  }

  function visibleAgents() {
    const all = Object.entries(DATA.agents || {});
    if (state.sessionFilter === '*') return all;
    return all.filter(([_, a]) => a.session_name === state.sessionFilter);
  }

  function updateSessionOptions() {
    const sel = document.getElementById('session-pick');
    if (!sel) return;
    const sessions = new Set(Object.values(DATA.agents || {}).map(a => a.session_name).filter(Boolean));
    const current = sel.value;
    sel.innerHTML = `<option value="*">(all sessions)</option>` +
      [...sessions].sort().map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
    sel.value = sessions.has(current) || current === '*' ? current : '*';
  }

  function render() {
    if (!listEl) return;
    const ids = visibleAgents().map(([p]) => p);
    if (!ids.length) {
      listEl.innerHTML = '<div style="padding:20px;color:var(--muted);font-size:12px;text-align:center">no agents…</div>';
      return;
    }

    const ordered = orderAgents(ids);

    listEl.innerHTML = ordered.map(p => {
      const a = DATA.agents[p];
      if (!a) return '';
      const isSub = SUBAGENTS.isSub(p);
      const isWatching = p === state.watching;
      const isShown = state.shown.has(p);
      const isChecked = state.checked.has(p);
      const isActive = a.is_active;
      const state_ = a.state || 'idle';
      const todoStr = a.todo_total ? `${a.todo_done || 0}/${a.todo_total}` : '';
      const ramStr  = a.ram_mb ? `${a.ram_mb}MB` : '';
      // v4.1 — todo count promoted to right-side pill; duplicate 📌 removed
      // (the coloured state-dot already shows is_active visually)
      const todoPctCls = a.todo_total && a.todo_done >= a.todo_total ? 'done' : '';
      // v3.7 — rate-limit badges in rail
      const rlBadge = (state_ === 'rate_limited' || a.rate_limit_msg)
        ? `<span class="ar-rl-badge" title="${esc(a.rate_limit_msg||'rate-limited')}">⏱</span>`
        : '';
      const authBadge = a.auth_expired
        ? `<span class="ar-auth-badge expired" title="Auth token expired — re-login">🔒</span>`
        : a.auth_expiring
          ? `<span class="ar-auth-badge expiring" title="Auth token expiring soon">🔑</span>`
          : '';
      return `
        <div class="agent-row ${isShown ? 'shown' : ''} ${isWatching ? 'watching' : ''} ${isActive ? 'is-active' : ''}"
             data-pane="${esc(p)}">
          <div class="ar-check"
               data-action="check"
               title="Click to toggle visibility on canvas"></div>
          <div class="ar-state-dot ${esc(state_)}" title="${esc(state_)} · ${isActive ? 'active in gmux' : 'background'}"></div>
          <div class="ar-name-region" data-action="watch" title="Click to watch this agent in the main canvas">
            <div class="ar-name">${esc(a.window_name || p)}${rlBadge}${authBadge}</div>
            <div class="ar-mini-stats">
              ${ramStr  ? `<span class="ms" title="RAM in MB">${ramStr}</span>` : ''}
              <span class="ms ar-pane">${esc(p)}</span>
            </div>
          </div>
          ${todoStr ? `<div class="ar-todo-pill ${todoPctCls}" title="todos done / total — click agent to see the list">${esc(todoStr)}</div>` : ''}
        </div>
      `;
    }).join('');

    // Wire events — separated checkbox vs name click (v3 point #11)
    listEl.querySelectorAll('.agent-row').forEach(row => {
      const pane = row.dataset.pane;
      row.querySelector('.ar-check').addEventListener('click', (e) => {
        e.stopPropagation();
        // Checkbox: toggle visibility only
        if (state.shown.has(pane)) state.shown.delete(pane);
        else state.shown.add(pane);
        render(); APP.notifyChange();
      });
      row.querySelector('.ar-name-region').addEventListener('click', (e) => {
        e.stopPropagation();
        // Name click: set watching (also shows if hidden)
        state.watching = pane;
        state.shown.add(pane);
        render(); APP.notifyChange();
      });
    });

    // Session dropdown
    const sel = document.getElementById('session-pick');
    if (sel) {
      sel.onchange = (e) => {
        state.sessionFilter = e.target.value;
        render(); APP.notifyChange();
      };
    }
  }

  function orderAgents(ids) {
    const result = [];
    const seen = new Set();
    const subsByParent = {};
    ids.forEach(id => {
      const p = SUBAGENTS.parentOf(id);
      if (p) (subsByParent[p] = subsByParent[p] || []).push(id);
    });
    ids.forEach(id => {
      if (SUBAGENTS.isSub(id)) return;
      result.push(id); seen.add(id);
      (subsByParent[id] || []).forEach(s => { result.push(s); seen.add(s); });
    });
    ids.forEach(id => { if (!seen.has(id)) result.push(id); });
    return result;
  }

  function setFollowActive(on) { state.followActive = on; render(); }

  return {
    init, render,
    get watching() { return state.watching; },
    get shown()    { return state.shown; },
    setWatching(p) { state.watching = p; state.shown.add(p); render(); APP.notifyChange(); },
    setFollowActive,
    get followActive() { return state.followActive; },
  };
})();
