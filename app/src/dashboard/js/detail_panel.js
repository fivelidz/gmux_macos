/* =====================================================================
   detail_panel.js v3 — right slide-in panel.

   v3 changes:
   - Agent panel has tabs: Info / Stats / Activity / Files (point #8)
   - Folder panel shows recursive tree of children (point #3)

   v3.6.4 changes (this revision):
   - Contents tree restored: "+" / "−" expand control per folder
   - Full absolute paths shown everywhere (no more ~/ collapse)
   - Detail panel auto-refreshes every 5s while open so live data is visible
   - Folder tree expands ALL ancestors of any touched file (no missing
     intermediate folders when only descendants have ops)
   - Historical (no-recent-touch) files render in grey with dashed lines
   ===================================================================== */

window.DETAIL = (function () {
  const { esc, fmtTime, fmtRelTime, fmtDur } = UTIL;

  // v3.6.4 — full absolute paths everywhere. homeCollapse is now a no-op
  // identity function so existing call sites keep compiling but no path
  // gets shortened. The user wants the full /home/<user>/... path visible
  // at all times so they can copy & paste, and so the path is unambiguous.
  function homeCollapse(p) { return p || ''; }
  // detectHomePrefix is kept for the breadcrumb logic but returns '' so
  // every crumb is computed from absolute path segments.
  function detectHomePrefix() { return ''; }
  // Expose for compatibility with other dashboard modules.
  window.homeCollapse = homeCollapse;

  let panel, body, titleEl, tabsEl, copyBtn;
  let currentNode = null;
  let currentTab  = 'info';
  let currentPath = null;        // path to copy on 📋 click

  function init() {
    panel   = document.getElementById('rail-right');
    body    = document.getElementById('rd-body');
    titleEl = document.getElementById('rd-title');
    tabsEl  = document.getElementById('rd-tabs');
    copyBtn = document.getElementById('rd-copy');
    document.getElementById('rd-close').addEventListener('click', close);
    // v4.1: the corner copy button is hidden (CSS); inline copy buttons live
    // next to the filename/foldername. Use event delegation on the body.
    if (copyBtn) copyBtn.style.display = 'none';
    body.addEventListener('click', (e) => {
      const btn = e.target.closest('.rd-copy-inline');
      if (!btn) return;
      e.stopPropagation();
      const path = btn.dataset.copyPath || currentPath;
      if (!path) return;
      currentPath = path;
      try {
        navigator.clipboard.writeText(path).then(showToast).catch(() => fallbackCopy(path));
      } catch (_) { fallbackCopy(path); }
    });

    // v3.6.4 — Live refresh tick. While the detail panel is open, re-render
    // the current view every REFRESH_MS so new activity is visible without
    // the user re-clicking. Folder tree: preserve which folders are collapsed
    // so the refresh doesn't reset the user's expansion state.
    setInterval(_liveRefreshTick, REFRESH_MS);
  }

  // How often the open detail panel re-renders from fresh DATA state.
  // 5s matches the user's requested cadence and is well above the 1s
  // event tick from Tauri, so we don't over-render the DOM.
  const REFRESH_MS = 5000;

  function _liveRefreshTick() {
    if (!currentNode) return;
    if (panel && panel.classList.contains('hidden')) return;
    // Preserve current scroll position + collapsed-folder state on refresh
    const scrollTop = body.scrollTop;
    const collapsedPaths = new Set(
      [...body.querySelectorAll('.rd-tree-node.folder.collapsed')]
        .map(el => el.dataset.folderPath)
    );

    if (currentNode.type === 'agent') {
      // Re-render the active tab from latest DATA.agents lookup
      const agent = (window.DATA && window.DATA.agents && window.DATA.agents[currentNode.data.pane_id])
        || currentNode.data;
      currentNode.data = agent;
      renderAgentTab(agent, currentTab);
    } else if (currentNode.type === 'folder') {
      _renderFolderBody(currentNode.path, currentNode.pane);
      // Re-apply preserved collapsed state
      collapsedPaths.forEach(p => {
        const el = body.querySelector(`.rd-tree-node.folder[data-folder-path="${cssEscapePath(p)}"]`);
        if (el && !el.classList.contains('collapsed')) {
          el.classList.add('collapsed');
          const btn = el.querySelector('.expand');
          if (btn && btn.textContent !== '·') btn.textContent = '+';
        }
      });
    } else if (currentNode.type === 'file') {
      // Look up the freshest file record
      const path = currentNode.data.path || currentNode.data.rel_path;
      const fresh = (window.DATA && window.DATA.files && window.DATA.files[path])
        || currentNode.data;
      currentNode.data = fresh;
      showFile(fresh, currentNode.pane);
    }

    body.scrollTop = scrollTop;
  }

  /** CSS attribute-selector-safe escape for an absolute path. Quotes the
   *  inner backslash and double-quote so the selector parses. */
  function cssEscapePath(p) {
    return (p || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  }

  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); showToast(); } catch (_) {}
    document.body.removeChild(ta);
  }

  function showToast() {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = 'copied: ' + (currentPath || '').slice(-50);
    t.classList.remove('hidden');
    clearTimeout(showToast._h);
    showToast._h = setTimeout(() => t.classList.add('hidden'), 1500);
  }

  function setCopyTarget(path) {
    currentPath = path;
    copyBtn.classList.toggle('hidden', !path);
  }

  function open() { document.body.classList.add('detail-open'); panel.classList.remove('hidden'); }
  function close() {
    document.body.classList.remove('detail-open');
    panel.classList.add('hidden');
    currentNode = null;
    setCopyTarget(null);
    if (FLOW) FLOW.deselect();
  }

  /* ----- AGENT (with tabs) ----- */
  function showAgent(agent) {
    if (!agent) return;
    currentNode = { type: 'agent', data: agent };
    titleEl.textContent = 'agent';
    setCopyTarget(null);   // no path on agent
    renderTabs(['info', 'stats', 'activity', 'files'], 'info');
    renderAgentTab(agent, 'info');
    open();
  }

  function renderTabs(tabs, defaultTab) {
    tabsEl.classList.remove('hidden');
    currentTab = defaultTab;
    tabsEl.innerHTML = tabs.map(t =>
      `<div class="rd-tab ${t === defaultTab ? 'active' : ''}" data-tab="${esc(t)}">${esc(t)}</div>`
    ).join('');
    tabsEl.querySelectorAll('.rd-tab').forEach(el => {
      el.addEventListener('click', () => {
        currentTab = el.dataset.tab;
        tabsEl.querySelectorAll('.rd-tab').forEach(x => x.classList.toggle('active', x === el));
        if (currentNode?.type === 'agent') renderAgentTab(currentNode.data, currentTab);
      });
    });
  }

  function renderAgentTab(agent, tab) {
    const head = `
      <div class="rd-title-big">${esc(agent.window_name || agent.pane_id)}</div>
      <div class="rd-subtitle">${esc(agent.pane_id)} · ${esc(agent.session_name || 'gmux')} · window ${esc(agent.window_index)}</div>
    `;

    if (tab === 'info') {
      // v4.1 — render real todo checklist below state info
      body.innerHTML = head + `
        <div class="rd-section">
          <h3>state</h3>
          <div class="rd-row"><span class="k">state</span><span class="v bright">${esc(agent.state || 'idle')}</span></div>
          ${agent.current_tool ? `<div class="rd-row"><span class="k">current tool</span><span class="v bright">${esc(agent.current_tool)}</span></div>` : ''}
          <div class="rd-row"><span class="k">model</span><span class="v">${esc(agent.model || '?')}</span></div>
          <div class="rd-row"><span class="k">is active</span><span class="v">${agent.is_active ? '✓ yes (gmux focus)' : 'no'}</span></div>
          ${agent.last_line ? `<div class="rd-row"><span class="k">last line</span><span class="v">${esc(agent.last_line)}</span></div>` : ''}
          ${agent.foreground_cmd ? `<div class="rd-row"><span class="k">cmd</span><span class="v">${esc(agent.foreground_cmd)}</span></div>` : ''}
        </div>
        ${renderTodoList(agent)}
      `;
    } else if (tab === 'stats') {
      body.innerHTML = head + `
        <div class="rd-section">
          <h3>process / runtime</h3>
          <div class="rd-row"><span class="k">RAM</span><span class="v bright">${agent.ram_mb || '?'} MB</span></div>
          <div class="rd-row"><span class="k">CPU</span><span class="v">${agent.cpu_pct != null ? agent.cpu_pct + '%' : '—'}</span></div>
          <div class="rd-row"><span class="k">session age</span><span class="v">${formatAge(agent.session_age_s)}</span></div>
          <div class="rd-row"><span class="k">api port</span><span class="v">${agent.api_port || '?'}</span></div>
          <div class="rd-row"><span class="k">sub-agents</span><span class="v">${SUBAGENTS.childrenOf(agent.pane_id).length}</span></div>
          <div class="rd-row"><span class="k">sub permission</span><span class="v">${agent.sub_agent_permission ? '✓' : '—'}</span></div>
        </div>
        <div class="rd-section">
          <h3>identity</h3>
          <div class="rd-row"><span class="k">pane id</span><span class="v">${esc(agent.pane_id)}</span></div>
          <div class="rd-row"><span class="k">session</span><span class="v">${esc(agent.session_name || '?')}</span></div>
          <div class="rd-row"><span class="k">window</span><span class="v">${agent.window_index} · ${esc(agent.window_name || '')}</span></div>
          <div class="rd-row"><span class="k">pane index</span><span class="v">${agent.pane_index}</span></div>
        </div>
      `;
    } else if (tab === 'activity') {
      body.innerHTML = head + renderRecentOps(agent.pane_id, 30);
    } else if (tab === 'files') {
      body.innerHTML = head + renderAgentFiles(agent.pane_id);
    }
    // Auto-scroll todo list (if present) to the active row + one row of history.
    requestAnimationFrame(() => window._gmuxScrollTodos && window._gmuxScrollTodos(body));
  }

  /** v4.1 — render todo checklist from agent.todo_items.
   *  Marks the first not-done row as ".active" so CSS can highlight it,
   *  and afterRender() scrolls it into view (one row of completed history
   *  visible above for context). */
  function renderTodoList(agent) {
    const items = agent.todo_items || [];
    const done  = agent.todo_done || 0;
    const total = agent.todo_total || items.length || 0;
    if (!total) return '';
    let activeMarked = false;
    const rows = items.map((it) => {
      const isActive = !it.done && !activeMarked;
      if (isActive) activeMarked = true;
      return `
        <div class="rd-todo ${it.done ? 'done' : ''}${isActive ? ' active' : ''}">
          <span class="cb">${it.done ? '☑' : (isActive ? '▶' : '☐')}</span>
          <span class="t">${esc(it.text)}</span>
        </div>
      `;
    }).join('');
    return `
      <div class="rd-section">
        <h3>todos <span class="todo-count ${done >= total ? 'all-done' : ''}">${done}/${total}</span></h3>
        <div class="rd-todo-list" data-autoscroll="true">${rows || '<div style="color:var(--muted);font-size:11px">no todo items yet</div>'}</div>
      </div>
    `;
  }

  /** Scroll any .rd-todo-list[data-autoscroll] so its .active row is near the
   *  top, with one row of history visible above. Called after detail-panel
   *  innerHTML is set. */
  function _scrollTodosToActive(root) {
    if (!root) return;
    root.querySelectorAll('.rd-todo-list[data-autoscroll="true"]').forEach(list => {
      const active = list.querySelector('.rd-todo.active') ||
                     list.querySelector('.rd-todo:not(.done)');
      if (!active) return;
      const rowH = active.offsetHeight || 22;
      list.scrollTop = Math.max(0, active.offsetTop - rowH);
    });
  }
  // Expose so detail_panel.js's main renderer can call after writing innerHTML.
  window._gmuxScrollTodos = _scrollTodosToActive;

  function renderAgentFiles(paneId) {
    // v3.6.4 — include any file whose agents list mentions this pane OR
    // whose touches_1h is positive (history retention extends past the 30m
    // window). This prevents the panel going empty when activity briefly
    // drops below the 30m window.
    const files = Object.values(DATA.files || {})
      .filter(f => {
        const inAgents = (f.agents || []).includes(paneId);
        return inAgents || (f.touches_1h || 0) > 0 || (f.touches_30m || 0) > 0;
      })
      .filter(f => (f.agents || []).includes(paneId) || (f.last_writer === paneId))
      .sort((a, b) => (b.touches_30m || 0) - (a.touches_30m || 0));
    if (!files.length) return '<div class="rd-section"><h3>files</h3><div style="color:var(--muted);font-size:11px">no files touched yet</div></div>';
    return `
      <div class="rd-section">
        <h3>files touched (${files.length})</h3>
        <div class="rd-tree">
          ${files.map(f => {
            const fullPath = f.path || f.rel_path || '';
            return `
            <div class="rd-tree-node file ${f.is_hot ? 'is-active' : ''}" data-path="${esc(fullPath)}" title="${esc(fullPath)}">
              <span class="icon">●</span>
              <span class="name" style="word-break:break-all;">${esc(fullPath)}</span>
              <span class="meta">${f.touches_30m || 0} ops</span>
            </div>
          `;
          }).join('')}
        </div>
      </div>
    `;
  }

  /* ----- FOLDER (nested tree, point #3) -----
   * v3.6.4 — Contents tree fully restored.
   * - Each folder row has a "+" / "−" expand control on the left.
   * - Children are visible by default (folders auto-expanded one level deep);
   *   deeper levels start collapsed but a single click on "+" opens them.
   * - Files with NO recent activity (no entry in DATA.files agents list
   *   matching pane, but the file exists in the project filesystem) render
   *   as grey/dashed historical entries — the user can see the structural
   *   neighbourhood, not just the freshly-touched files.
   * - The tree re-renders every 5s while the panel is open so new activity
   *   appears live without the user re-clicking the folder.
   */
  function showFolder(folderPath, agentPane) {
    currentNode = { type: 'folder', path: folderPath, pane: agentPane };
    titleEl.textContent = 'folder';
    setCopyTarget(folderPath);   // sets currentPath; head button is hidden in v4.1
    tabsEl.classList.add('hidden');
    _renderFolderBody(folderPath, agentPane);
    open();
  }

  /** Internal: render (or re-render) the folder panel body for a given path.
   *  Pulled out so the 5s live-refresh tick can call it without reopening. */
  function _renderFolderBody(folderPath, agentPane) {
    const tree = buildFolderTree(folderPath, agentPane);
    const breakdown = folderBreakdown(folderPath, agentPane);
    // v3.6.4 — breadcrumb uses absolute path only. Each segment is a
    // clickable folder; the final segment is bold non-link.
    const parts = folderPath.split('/').filter(Boolean);
    let acc = '';
    const crumbs = parts.map(seg => {
      acc += '/' + seg;
      return { label: seg, path: acc };
    });
    const crumbHtml = crumbs.map((c, i) =>
      i === crumbs.length - 1
        ? `<span style="color:var(--text);font-weight:600;">${esc(c.label)}</span>`
        : `<a href="#" class="folder-crumb" data-folder-path="${esc(c.path)}" style="color:var(--accent);text-decoration:none;">${esc(c.label)}</a>`
    ).join('<span style="color:var(--muted);margin:0 4px;">/</span>');

    const nodeCount = countNodes(tree);
    body.innerHTML = `
      <div class="rd-title-big">
        <span class="rd-title-text" style="word-break:break-all;">${esc(folderPath)}/</span>
        <button class="rd-copy-inline" data-copy-path="${esc(folderPath)}" title="Copy path to clipboard">📋</button>
      </div>
      <div class="rd-subtitle" style="font-family:monospace;font-size:11px;line-height:1.5;word-break:break-all;">
        /${crumbHtml}${agentPane ? ` <span style="color:var(--muted)">· agent ${esc(agentPane)}</span>` : ''}
      </div>
      ${renderBreakdown(breakdown)}
      <div class="rd-section">
        <h3>contents tree <span class="todo-count">${nodeCount}</span>${nodeCount === 0 ? ' — no files touched yet' : ''}</h3>
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">
          <span style="color:var(--accent)">+</span> expand · <span style="color:var(--accent)">−</span> collapse · click folder name to drill in · click file to inspect
        </div>
        <div class="rd-tree" id="folder-tree-root">
          ${renderTreeNode(tree, 0, /*defaultExpandedDepth*/ 1)}
        </div>
      </div>
    `;
    // Breadcrumb click handlers
    body.querySelectorAll('.folder-crumb').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        showFolder(el.dataset.folderPath, agentPane);
      });
    });
    wireTreeClicks();
  }

  /** v4: op breakdown widget — small coloured pills */
  function renderBreakdown(b) {
    if (!b) return '';
    const total = (b.read || 0) + (b.write || 0) + (b.edit || 0) + (b.bash || 0) + (b.perm || 0);
    if (!total) return '<div class="op-breakdown"><div class="op-pill" style="opacity:0.5"><span class="pill-name">no ops yet</span></div></div>';
    const pill = (name, count) =>
      count ? `<div class="op-pill ${name}"><span class="pill-dot"></span><span class="pill-name">${name}</span><span class="pill-count">${count}</span></div>` : '';
    return `<div class="op-breakdown">
      ${pill('write', b.write || 0)}
      ${pill('edit',  b.edit  || 0)}
      ${pill('read',  b.read  || 0)}
      ${pill('bash',  b.bash  || 0)}
      ${pill('perm',  b.perm  || 0)}
    </div>`;
  }

  function folderBreakdown(folderPath, pane) {
    // v3.6.2 — same absolute-path match as buildFolderTree above.
    const all = Object.values(DATA.files || {});
    const inFolder = all.filter(f => {
      const fp = f.path || f.rel_path || '';
      if (folderPath && !fp.startsWith(folderPath + '/') && fp !== folderPath) return false;
      if (pane && !(f.agents || []).includes(pane)) return false;
      return true;
    });
    const sum = { read: 0, write: 0, edit: 0, bash: 0, perm: 0 };
    inFolder.forEach(f => {
      const b = fileBreakdown(f, pane);
      Object.keys(sum).forEach(k => sum[k] += (b[k] || 0));
    });
    return sum;
  }

  function fileBreakdown(file, pane) {
    // v4.2 — use fuzzy path match (events use rel paths, files use abs)
    const matches = window.PATH_MATCHES || ((p, f) => p === (f.path || f.rel_path));
    const counts = { read: 0, write: 0, edit: 0, bash: 0, perm: 0 };
    (DATA.activity || []).forEach(e => {
      if (pane && e.pane_id !== pane) return;
      if (!e.args || !matches(e.args.file_path, file)) return;
      if (e.kind === 'tool_end') {
        const t = (e.tool || '').toLowerCase();
        if (t === 'write') counts.write++;
        else if (t === 'edit') counts.edit++;
        else if (t === 'read' || t === 'glob' || t === 'grep') counts.read++;
        else if (t === 'bash' || t === 'task') counts.bash++;
      } else if (e.kind === 'permission_request') {
        counts.perm++;
      }
    });
    return counts;
  }

  function buildFolderTree(folderPath, agentPane) {
    // v3.6.4 — match files by absolute path. The agentPane filter now
    // additionally includes files where `last_writer == pane` even when the
    // current 30m `agents` list is empty (counts decayed out of the window).
    // This is what lets historical files still appear in the tree as grey
    // entries instead of vanishing entirely when ops age out.
    const all = Object.values(DATA.files || {});
    const inFolder = all.filter(f => {
      const fp = f.path || f.rel_path || '';
      if (folderPath && !fp.startsWith(folderPath + '/') && fp !== folderPath) return false;
      if (agentPane) {
        const inAgents = (f.agents || []).includes(agentPane);
        const isLastWriter = f.last_writer === agentPane;
        if (!inAgents && !isLastWriter) return false;
      }
      return true;
    });

    const root = { name: folderPath.split('/').pop() || '(root)', path: folderPath, kind: 'folder', children: {}, files: [] };
    const stripPrefix = folderPath ? folderPath + '/' : '';

    inFolder.forEach(f => {
      const fullPath = f.path || f.rel_path || '';
      const rel = fullPath.startsWith(stripPrefix) ? fullPath.slice(stripPrefix.length) : fullPath;
      const parts = rel.split('/').filter(Boolean);
      if (!parts.length) return;
      let cur = root, accPath = folderPath;
      for (let i = 0; i < parts.length - 1; i++) {
        const seg = parts[i];
        accPath = accPath ? accPath + '/' + seg : seg;
        if (!cur.children[seg]) cur.children[seg] = { name: seg, path: accPath, kind: 'folder', children: {}, files: [] };
        cur = cur.children[seg];
      }
      cur.files.push(f);
    });
    return root;
  }

  /** v3.6.4 — Recursive tree renderer with "+"/"−" expand control.
   *  @param node               folder tree node from buildFolderTree
   *  @param depth              current depth (0 = panel root, not rendered as a row)
   *  @param defaultExpandedDepth  rows at depth <= this start expanded;
   *                               deeper rows start collapsed with a "+" badge
   *
   *  Folder rows: [+/−]  📁  name/   ops · N items
   *  File rows:   [ · ]  ·    name    ops    (grey & dashed when historical)
   *  Active files keep the .is-active class so CSS can highlight them.
   */
  function renderTreeNode(node, depth, defaultExpandedDepth) {
    const childKeys = Object.keys(node.children || {}).sort();
    const folderTouches = totalTouches(node);
    const childCount = childKeys.length + (node.files || []).length;
    const hasChildren = childCount > 0;
    // Default-collapsed starts at depth > defaultExpandedDepth.
    const startsCollapsed = depth > (defaultExpandedDepth ?? 1);
    let html = '';
    if (depth > 0) {
      // The "+/−" expand control. Always present; renders as "+" when
      // collapsed, "−" when expanded. The button is its own click target
      // (data-action=toggle). Clicking anywhere else on the row's name
      // drills into the folder (data-action=open).
      const expandIcon = hasChildren
        ? (startsCollapsed ? '+' : '−')
        : '·';   // leaf-only folder (no children) — neutral
      const collapsedCls = startsCollapsed ? 'collapsed' : '';
      html += `
        <div class="rd-tree-node folder ${collapsedCls}" data-folder-path="${esc(node.path)}" title="${esc(node.path)}">
          <span class="expand" data-action="toggle"${hasChildren ? '' : ' style="opacity:.3;cursor:default;"'}>${expandIcon}</span>
          <span class="icon">📁</span>
          <span class="name" data-action="open">${esc(node.name)}/</span>
          <span class="meta">${folderTouches} ops · ${childCount} items</span>
        </div>
      `;
    }
    const childrenHtml = childKeys.map(k => renderTreeNode(node.children[k], depth + 1, defaultExpandedDepth)).join('') +
      (node.files || []).map(f => {
        const fullPath = f.path || f.rel_path || '';
        const basename = fullPath.split('/').pop();
        const touches = f.touches_30m || 0;
        // v3.6.4 — historical (no-recent-touch) files render dimmer.
        // .historical class applied when touches_30m == 0 AND touches_1h <= 1.
        const isHistorical = touches === 0 && (f.touches_1h || 0) <= 1 && !f.is_hot;
        const histCls = isHistorical ? 'historical' : '';
        return `
        <div class="rd-tree-node file ${f.is_hot ? 'is-active' : ''} ${histCls}" data-path="${esc(fullPath)}" title="${esc(fullPath)}">
          <span class="expand"></span>
          <span class="icon">${f.is_hot ? '🔥' : f.is_conflict ? '⚠' : '·'}</span>
          <span class="name">${esc(basename)}</span>
          <span class="meta">${touches} ops</span>
        </div>
      `;
      }).join('');

    if (depth > 0) {
      html += `<div class="rd-tree-children">${childrenHtml}</div>`;
    } else {
      html += childrenHtml;
    }
    return html;
  }

  function totalTouches(node) {
    let n = (node.files || []).reduce((acc, f) => acc + (f.touches_30m || 0), 0);
    Object.values(node.children || {}).forEach(c => n += totalTouches(c));
    return n;
  }
  function countNodes(node) {
    let n = (node.files || []).length;
    Object.values(node.children || {}).forEach(c => n += countNodes(c));
    return n;
  }

  function wireTreeClicks() {
    body.querySelectorAll('.rd-tree-node.folder').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        // v3.6.4 — .expand button toggles collapse/expand; name drills in.
        // The button itself reads "+" when collapsed, "−" when expanded.
        const action = e.target.dataset && e.target.dataset.action;
        if (action === 'toggle') {
          const wasCollapsed = el.classList.toggle('collapsed');
          const btn = el.querySelector('.expand');
          if (btn && btn.textContent !== '·') {
            btn.textContent = wasCollapsed ? '+' : '−';
          }
        } else if (action === 'open') {
          // Click on the name → drill into the subfolder
          const folderPath = el.dataset.folderPath;
          if (folderPath) showFolder(folderPath, currentNode?.pane);
        }
        // Click anywhere else on the row body: do nothing
      });
    });
    body.querySelectorAll('.rd-tree-node.file').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const path = el.dataset.path;
        const file = (DATA.files || {})[path] ||
          Object.values(DATA.files || {}).find(f => (f.path === path || f.rel_path === path));
        if (file) showFile(file, currentNode?.pane);
      });
    });
  }

  /* ----- FILE ----- */
  function showFile(file, agentPane) {
    if (!file) return;
    currentNode = { type: 'file', data: file, pane: agentPane };
    titleEl.textContent = 'file';
    setCopyTarget(file.path || file.rel_path);
    tabsEl.classList.add('hidden');
    const breakdown = fileBreakdown(file, agentPane);
    const filePath = file.path || file.rel_path;
    const deltas = fileChangeDeltas(file, agentPane);
    // v4.4 — order: title → path → breakdown pills → touches → CODE CHANGES → op log
    body.innerHTML = `
      <div class="rd-title-big">
        <span class="rd-title-text">${esc((file.path || file.rel_path || '').split('/').pop())}</span>
        <button class="rd-copy-inline" data-copy-path="${esc(filePath)}" title="Copy path to clipboard">📋</button>
      </div>
      <!-- v3.6.4 — show the FULL absolute path as the subtitle. The user
           wants the path verbatim so it can be copied & located on disk
           without ambiguity. The 📋 button next to the basename copies it
           to the clipboard. -->
      <div class="rd-subtitle" title="${esc(file.path || '')}" style="word-break:break-all;font-family:monospace;font-size:11px;line-height:1.4;">${esc(file.path || file.rel_path || '')}</div>
      ${renderBreakdown(breakdown)}
      <div class="rd-section">
        <h3>touches</h3>
        <div class="rd-row"><span class="k">last 5m</span><span class="v">${file.touches_5m || 0} ops</span></div>
        <div class="rd-row"><span class="k">last 30m</span><span class="v">${file.touches_30m || 0} ops</span></div>
        <div class="rd-row"><span class="k">last 1h</span><span class="v">${file.touches_1h || 0} ops</span></div>
        <div class="rd-row"><span class="k">last touch</span><span class="v">${esc(fmtRelTime(file.last_touch_ts))}</span></div>
        <div class="rd-row"><span class="k">last writer</span><span class="v">${esc(agentName(file.last_writer))}</span></div>
        <div class="rd-row"><span class="k">flags</span><span class="v">
          ${file.is_hot ? '<span style="color:var(--op-write)">hot</span> ' : ''}
          ${file.is_conflict ? '<span style="color:var(--op-block)">conflict</span> ' : ''}
          ${file.is_god_node ? `<span style="color:var(--op-edit)">god (${file.callers || 0} callers)</span>` : ''}
          ${!file.is_hot && !file.is_conflict && !file.is_god_node ? '<span style="color:var(--muted)">none</span>' : ''}
        </span></div>
      </div>
      ${(deltas.added || deltas.removed) ? `
        <div class="rd-section">
          <h3>code changes</h3>
          <div class="delta-summary">
            <span class="delta-add big">+${deltas.added}</span>
            <span class="delta-sep">/</span>
            <span class="delta-rem big">−${deltas.removed}</span>
            <span class="delta-label">lines (cumulative)</span>
          </div>
        </div>
      ` : ''}
      ${renderFileOps(file.path || file.rel_path, agentPane)}
    `;
    open();
  }

  function renderRecentOps(paneId, max = 12) {
    const events = (DATA.activity || []).filter(e => e.pane_id === paneId).slice(0, max);
    if (!events.length) return '<div class="rd-section"><h3>recent ops</h3><div style="color:var(--muted);font-size:11px">no recent ops</div></div>';
    return `
      <div class="rd-section">
        <h3>recent operations</h3>
        <div class="rd-op-log">
          ${events.map(e => renderOpRow(e)).join('')}
        </div>
      </div>
    `;
  }

  function renderFileOps(path, paneId) {
    // v4.2 — fuzzy match: accept any event whose file_path equals or is a
    // suffix/prefix of the file's path or rel_path
    const events = (DATA.activity || []).filter(e => {
      const p = e.args && e.args.file_path;
      if (!p) return false;
      if (paneId && e.pane_id !== paneId) return false;
      if (p === path) return true;
      if (path.endsWith('/' + p)) return true;
      if (p.endsWith('/' + path)) return true;
      return false;
    }).slice(0, 20);
    if (!events.length) return '';
    return `
      <div class="rd-section">
        <h3>operation log on this file</h3>
        <div class="rd-op-log">
          ${events.map(e => renderOpRow(e)).join('')}
        </div>
      </div>
    `;
  }

  function renderOpRow(e) {
    if (e.kind !== 'tool_start' && e.kind !== 'tool_end') {
      return `<div class="rd-op-row">
        <span class="ts">${esc(fmtTime(e.ts))}</span>
        <span class="op" style="background:rgba(255,255,255,0.05);color:var(--text-dim)">${esc(e.kind)}</span>
        <span class="det">${esc(JSON.stringify(e.args || {}))}</span>
      </div>`;
    }
    const opCls = (e.tool || '').toLowerCase();
    // v3.6.4 — show the FULL absolute file path verbatim. Commands / patterns
    // continue to render as-is. Tooltip carries the same value for hover.
    let path = '';
    let pathTitle = '';
    if (e.args) {
      if (e.args.file_path) {
        pathTitle = e.args.file_path;
        path = e.args.file_path;
      } else if (e.args.command) {
        path = e.args.command;
      } else if (e.args.pattern) {
        path = e.args.pattern;
      }
    }
    const dur  = e.duration_ms != null ? fmtDur(e.duration_ms) : (e.kind === 'tool_start' ? '…' : '');
    // v4.3 — show +N/-M code deltas if present
    const deltaHtml = renderDelta(e);
    return `<div class="rd-op-row" ${pathTitle ? `title="${esc(pathTitle)}"` : ''}>
      <span class="ts">${esc(fmtTime(e.ts))}</span>
      <span class="op ${esc(opCls)}">${esc(e.tool || '')}</span>
      <span class="det" style="word-break:break-all;">${esc(path)} ${dur ? `<span style="color:var(--accent)">${esc(dur)}</span>` : ''}${deltaHtml}</span>
    </div>`;
  }

  function renderDelta(e) {
    const add = e.lines_added;
    const rem = e.lines_removed;
    if (add == null && rem == null) return '';
    const parts = [];
    if (add) parts.push(`<span class="delta-add">+${add}</span>`);
    if (rem) parts.push(`<span class="delta-rem">−${rem}</span>`);
    if (!parts.length) return '';
    return ` <span class="delta-pair">${parts.join(' ')}</span>`;
  }

  /** v4.3 — sum lines_added / lines_removed across all events for this file */
  function fileChangeDeltas(file, pane) {
    const matches = window.PATH_MATCHES || ((p, f) => p === (f.path || f.rel_path));
    let added = 0, removed = 0;
    (DATA.activity || []).forEach(e => {
      if (pane && e.pane_id !== pane) return;
      if (!e.args || !matches(e.args.file_path, file)) return;
      if (e.kind !== 'tool_end') return;
      if (e.lines_added)   added   += e.lines_added;
      if (e.lines_removed) removed += e.lines_removed;
    });
    return { added, removed };
  }

  function agentName(p) {
    const a = (DATA.agents || {})[p];
    return a ? a.window_name : (p || '');
  }

  function formatAge(s) {
    if (!s) return '?';
    if (s < 60) return s + 's';
    if (s < 3600) return Math.floor(s / 60) + 'm';
    return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
  }

  return { init, showAgent, showFolder, showFile, close };
})();
