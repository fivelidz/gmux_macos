/* =====================================================================
   app.js v3 — bootstrap, top-bar wiring, glue.

   v3 changes:
   - history toggle DEFAULT ON (point #10)
   - auto-centre on agent change (point #6)
   - follow-active toggle (point #13)
   - session selector (point #12)
   - version label
   ===================================================================== */

window.APP = (function () {
  const { esc } = UTIL;

  const state = {
    overviewMode: false,
    showHistory:  true,         // DEFAULT ON (was off in v2 — point #10)
    needsAutofit: true,
    lastWatched:  null,
  };

  function setTitleAgent() {
    const pane = RAIL.watching;
    const a = pane && (DATA.agents || {})[pane];
    document.getElementById('title-agent').textContent = a ? (a.window_name || pane) : '—';
    document.getElementById('title-pane').textContent  = a ? pane : '';
    const stateEl = document.getElementById('title-state');
    if (a) {
      stateEl.textContent = a.state || 'idle';
      stateEl.className = 'title-state ' + (a.state || 'idle');
    } else {
      stateEl.textContent = '';
      stateEl.className = 'title-state';
    }
  }

  function rebuild(opts = {}) {
    const watched = RAIL.watching;
    const watchedChanged = watched !== state.lastWatched;
    state.lastWatched = watched;

    let model;
    if (state.overviewMode) {
      const visible = [...RAIL.shown];
      model = LAYOUT.buildOverview(visible);
    } else {
      if (!watched) { FLOW.render({ nodes: [], edges: [] }); setTitleAgent(); return; }
      const subPanes = SUBAGENTS.childrenOf(watched).filter(p => RAIL.shown.has(p));
      model = LAYOUT.buildSingleAgent(watched, subPanes, { showHistory: state.showHistory });
    }
    // v4.1 — never filter the model on history toggle (it caused layout jumps
    // every time the toggle flipped). Instead, mark the body with a class and
    // let CSS hide the .edge.h-* paths.
    document.body.classList.toggle('no-history', !state.showHistory);
    document.body.classList.toggle('overview-mode', state.overviewMode);

    const wantFit = opts.autofit || state.needsAutofit || watchedChanged;
    FLOW.render(model, { autofit: wantFit });
    state.needsAutofit = false;
    setTitleAgent();
  }

  function notifyChange() {
    rebuild();
  }

  function wireTopbar() {
    // v4 — button click handlers always use currentTarget (the button, not
    // the inner span that may have been clicked) and explicitly set/remove
    // the .active class. Fixes point #3.
    const btnOverview = document.getElementById('btn-overview');
    btnOverview.addEventListener('click', () => {
      state.overviewMode = !state.overviewMode;
      btnOverview.classList.toggle('active', state.overviewMode);
      state.needsAutofit = true;
      rebuild();
    });

    const btnHistory = document.getElementById('btn-history');
    btnHistory.addEventListener('click', () => {
      state.showHistory = !state.showHistory;
      btnHistory.classList.toggle('active', state.showHistory);
      rebuild();
    });
    btnHistory.classList.toggle('active', state.showHistory);

    const btnFollow = document.getElementById('btn-follow');
    btnFollow.addEventListener('click', () => {
      const next = !RAIL.followActive;
      RAIL.setFollowActive(next);
      btnFollow.classList.toggle('active', next);
      updateFollowStatus();
    });

    const btnPause = document.getElementById('btn-pause');
    btnPause.addEventListener('click', () => {
      const paused = !DATA.paused;
      DATA.pause(paused);
      btnPause.querySelector('.bi').textContent = paused ? '▶' : '⏸';
      btnPause.querySelector('.bl').textContent = paused ? 'play' : 'pause';
      btnPause.classList.toggle('active', paused);
    });
    document.getElementById('btn-fullscreen').addEventListener('click', () => {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen();
      else document.exitFullscreen();
    });
    // v4.2 — guide button + G keyboard shortcut
    const btnHelp = document.getElementById('btn-help');
    if (btnHelp) btnHelp.addEventListener('click', openHelp);

    // v4.4 — style options panel
    const btnStyle = document.getElementById('btn-style');
    if (btnStyle) btnStyle.addEventListener('click', toggleStylePanel);
    document.getElementById('sp-close').addEventListener('click', closeStylePanel);
    wireStyleOptions();

    document.getElementById('theme-pick').addEventListener('change', (e) => {
      document.documentElement.dataset.theme = e.target.value;
      try { localStorage.setItem('gmux-dashboard-theme', e.target.value); } catch (_) {}
      rebuild();   // re-render so curve/ortho switches apply
    });

    // Restore saved theme (default = obsidian).
    // v4: 'light-sand' renamed to 'light-wood' — migrate if seen.
    try {
      let t = localStorage.getItem('gmux-dashboard-theme') || 'obsidian';
      if (t === 'light-sand') t = 'light-wood';
      document.documentElement.dataset.theme = t;
      document.getElementById('theme-pick').value = t;
    } catch (_) {
      document.documentElement.dataset.theme = 'obsidian';
    }

    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.key === 'f' || e.key === 'F') document.getElementById('btn-fullscreen').click();
      if (e.key === ' ') { e.preventDefault(); document.getElementById('btn-pause').click(); }
      if (e.key === 'g' || e.key === 'G') openHelp();
      if (e.key === 'Escape') {
        if (document.querySelector('.help-overlay:not(.hidden)')) closeHelp();
        else if (document.querySelector('#style-panel:not(.hidden)')) closeStylePanel();
        else DETAIL.close();
      }
    });

    // v4.6 — top-left brand shows the currently-selected gmux session
    wireSessionNameDisplay();
  }

  /** v4.6 — keep the big brand-area session name in sync with the
   *  session-picker dropdown + the actual data. Updates on:
   *    (a) DATA.on('agents')   → sessions may have appeared
   *    (b) #session-pick change → user picked a different one
   *  Falls back to "(no session)" if no agents are known. */
  function wireSessionNameDisplay() {
    const big = document.getElementById('session-name-big');
    const pick = document.getElementById('session-pick');
    if (!big) return;

    function update() {
      const agents = DATA.agents || {};
      const sessions = [...new Set(Object.values(agents).map(a => a.session_name).filter(Boolean))];
      const picked = pick ? pick.value : '*';
      let name;
      if (!sessions.length) {
        name = '(no session)';
      } else if (picked && picked !== '*') {
        name = picked;
      } else if (sessions.length === 1) {
        name = sessions[0];
      } else {
        name = sessions[0] + ' +' + (sessions.length - 1);   // e.g. "gmux +2"
      }
      big.textContent = name;
    }

    DATA.on('agents', update);
    if (pick) pick.addEventListener('change', update);
    update();
  }

  // v4.2 — help modal (loads docs/USER_GUIDE.md, renders as HTML)
  let helpLoaded = false;
  async function openHelp() {
    let overlay = document.getElementById('help-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'help-overlay';
      overlay.className = 'help-overlay hidden';
      overlay.innerHTML = `
        <div class="help-modal" id="help-modal">
          <div class="help-modal-head">
            <h2>USER GUIDE · v${window.VERSION || '4.2'}</h2>
            <button class="help-modal-close" id="help-close">close (Esc)</button>
          </div>
          <div class="help-modal-body" id="help-body">loading…</div>
        </div>
      `;
      document.body.appendChild(overlay);
      overlay.addEventListener('click', (e) => { if (e.target === overlay) closeHelp(); });
      document.getElementById('help-close').addEventListener('click', closeHelp);
    }
    overlay.classList.remove('hidden');
    if (!helpLoaded) {
      try {
        const r = await fetch('../docs/USER_GUIDE.md', { cache: 'no-store' });
        const md = await r.text();
        document.getElementById('help-body').innerHTML = renderMarkdown(md);
        helpLoaded = true;
      } catch (e) {
        document.getElementById('help-body').textContent = 'Could not load user guide: ' + e.message;
      }
    }
  }
  function closeHelp() {
    const o = document.getElementById('help-overlay');
    if (o) o.classList.add('hidden');
  }

  /* ================================================================
   * v4.4 — STYLE OPTIONS PANEL
   * Controls: edge style, stroke weight, pulse size, label toggle
   * All apply as CSS custom-property overrides on <html> or <body>
   * and are persisted in localStorage.
   * ================================================================ */
  function toggleStylePanel() {
    const p = document.getElementById('style-panel');
    if (!p) return;
    p.classList.toggle('hidden');
  }
  function closeStylePanel() {
    const p = document.getElementById('style-panel');
    if (p) p.classList.add('hidden');
  }

  function wireStyleOptions() {
    // Helper to make a button-group exclusive
    function pickGroup(groupId, onChange) {
      const grp = document.getElementById(groupId);
      if (!grp) return;
      grp.querySelectorAll('.sp-opt').forEach(btn => {
        btn.addEventListener('click', () => {
          grp.querySelectorAll('.sp-opt').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          onChange(btn.dataset.val);
          try { localStorage.setItem('gad-style-' + groupId, btn.dataset.val); } catch (_) {}
        });
      });
      // restore saved
      try {
        const saved = localStorage.getItem('gad-style-' + groupId);
        if (saved) {
          const btn = grp.querySelector(`[data-val="${saved}"]`);
          if (btn) { grp.querySelectorAll('.sp-opt').forEach(b => b.classList.remove('active')); btn.classList.add('active'); onChange(saved); }
        }
      } catch (_) {}
    }

    // Edge style — sets --edge-style CSS var (curve / ortho / arc)
    // 'arc' is a new option: shorter, tighter bezier (cy = dy * 0.3)
    pickGroup('sp-edge-style', (val) => {
      document.documentElement.style.setProperty('--edge-style', val);
      rebuild();
    });

    // Stroke weight — sets --stroke-active CSS var
    const strokeMap = { thin: 2, normal: 3.5, thick: 5.5 };
    pickGroup('sp-stroke', (val) => {
      const w = strokeMap[val] || 3.5;
      document.documentElement.style.setProperty('--stroke-active', w);
      document.documentElement.style.setProperty('--stroke-history', (w * 0.65).toFixed(1));
    });

    // Pulse size
    const pulseMap = { small: 3, normal: 4.5, large: 7 };
    pickGroup('sp-pulse', (val) => {
      document.documentElement.style.setProperty('--pulse-r', pulseMap[val] || 4.5);
    });

    // Label toggle
    pickGroup('sp-labels', (val) => {
      FLOW.setShowLabels(val === 'on');
    });

    // v4.5 — Test mode: single-action (one in-flight op per agent at a time)
    pickGroup('sp-single', (val) => {
      DATA.setSingleAction(val === 'single');
    });
  }

  /** Tiny markdown→HTML — no deps. Covers headings, lists, tables, code,
   *  bold, links, hr. Good enough for the user guide. */
  function renderMarkdown(md) {
    // escape HTML first
    const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const lines = md.split('\n');
    let html = '';
    let inCode = false, inList = false, inTable = false, tableHead = false;
    let tableCols = 0;
    for (let i = 0; i < lines.length; i++) {
      let ln = lines[i];
      // code fence
      if (ln.startsWith('```')) {
        if (!inCode) { html += '<pre><code>'; inCode = true; }
        else { html += '</code></pre>'; inCode = false; }
        continue;
      }
      if (inCode) { html += esc(ln) + '\n'; continue; }
      // table
      if (ln.includes('|') && lines[i+1] && /^\s*\|?\s*[-:| ]+\|?\s*$/.test(lines[i+1])) {
        // start of table
        const cells = ln.split('|').map(s => s.trim()).filter((_, j, a) => !(j === 0 && a[0] === '') && !(j === a.length-1 && a[a.length-1] === ''));
        html += '<table style="border-collapse:collapse;margin:8px 0;width:100%"><thead><tr>' +
          cells.map(c => `<th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:11px;font-weight:600">${inlineMd(esc(c))}</th>`).join('') +
          '</tr></thead><tbody>';
        tableCols = cells.length;
        inTable = true; i++;   // skip separator
        continue;
      }
      if (inTable) {
        if (!ln.includes('|') || ln.trim() === '') { html += '</tbody></table>'; inTable = false; }
        else {
          const cells = ln.split('|').map(s => s.trim()).filter((_, j, a) => !(j === 0 && a[0] === '') && !(j === a.length-1 && a[a.length-1] === ''));
          html += '<tr>' + cells.map(c => `<td style="padding:4px 8px;border-bottom:1px solid var(--border);vertical-align:top">${inlineMd(esc(c))}</td>`).join('') + '</tr>';
          continue;
        }
      }
      // headings
      let m;
      if ((m = ln.match(/^(#{1,3})\s+(.*)$/))) {
        const lvl = m[1].length;
        html += `<h${lvl}>${inlineMd(esc(m[2]))}</h${lvl}>`;
        continue;
      }
      // hr
      if (/^---+$/.test(ln.trim())) { html += '<hr style="border:none;border-top:1px solid var(--border);margin:18px 0"/>'; continue; }
      // list
      if ((m = ln.match(/^[\-\*]\s+(.*)$/))) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${inlineMd(esc(m[1]))}</li>`;
        continue;
      } else if (inList && ln.trim() === '') {
        html += '</ul>'; inList = false; continue;
      } else if (inList && !/^\s+/.test(ln)) {
        html += '</ul>'; inList = false;
      }
      // blockquote
      if (ln.startsWith('> ')) { html += `<blockquote style="border-left:3px solid var(--accent);padding:4px 12px;color:var(--text-dim);margin:8px 0">${inlineMd(esc(ln.slice(2)))}</blockquote>`; continue; }
      // blank line
      if (ln.trim() === '') { html += ''; continue; }
      // paragraph
      html += `<p>${inlineMd(esc(ln))}</p>`;
    }
    if (inList) html += '</ul>';
    if (inTable) html += '</tbody></table>';
    return html;
  }
  function inlineMd(s) {
    return s
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--accent)">$1</a>');
  }

  function wireFlowClicks() {
    FLOW.setOnNodeClick((node) => {
      if (!node) { DETAIL.close(); return; }
      if (node.kind === 'agent' || node.kind === 'subagent') {
        DETAIL.showAgent(node.data);
      } else if (node.kind === 'folder') {
        DETAIL.showFolder(node.fullPath, node.pane);
      } else if (node.kind === 'file') {
        DETAIL.showFile(node.data, node.pane);
      }
    });
  }

  function updateConn() {
    const el = document.getElementById('conn-indicator');
    const src = document.getElementById('src-indicator');
    if (DATA.paused) { el.className = 'conn-indicator warn'; src.textContent = 'paused'; return; }
    el.className = 'conn-indicator';
    src.textContent = DATA.source || 'connecting';
  }

  // v4 — follow status pill in title
  function updateFollowStatus() {
    const el = document.getElementById('title-follow');
    if (!el) return;
    el.classList.toggle('hidden', !RAIL.followActive);
  }

  // v4 — draggable detail panel resize
  function wireResize() {
    const handle = document.getElementById('resize-handle');
    if (!handle) return;
    let startX = 0, startW = 0;
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      startX = e.clientX;
      const root = getComputedStyle(document.documentElement);
      startW = parseInt(root.getPropertyValue('--detail-width')) || 280;
      document.body.classList.add('resizing');
      function onMove(ev) {
        const dx = startX - ev.clientX;
        const newW = Math.max(180, Math.min(640, startW + dx));
        document.documentElement.style.setProperty('--detail-width', newW + 'px');
      }
      function onUp() {
        document.body.classList.remove('resizing');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        // persist
        try { localStorage.setItem('gmux-detail-width', document.documentElement.style.getPropertyValue('--detail-width')); } catch (_) {}
      }
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
    // restore
    try {
      const saved = localStorage.getItem('gmux-detail-width');
      if (saved) document.documentElement.style.setProperty('--detail-width', saved);
    } catch (_) {}
  }

  function init() {
    // version label
    const vt = document.getElementById('version-tag');
    if (vt && window.VERSION) vt.textContent = 'v' + window.VERSION;

    SUBAGENTS;
    RAIL.init();
    DETAIL.init();
    FLOW.init();
    PULSES.init();
    wireTopbar();
    wireFlowClicks();
    wireResize();

    DATA.on('agents',   () => rebuild());
    DATA.on('files',    () => rebuild());
    DATA.on('activity', () => rebuild());
    DATA.on('source',   updateConn);

    DATA.start({ source: 'auto', pollMs: 2000, evolveMs: 1800 });
    setInterval(updateConn, 1500);

    window.addEventListener('resize', () => { state.needsAutofit = true; rebuild(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { notifyChange, rebuild };
})();
