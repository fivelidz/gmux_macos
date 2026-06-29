/* =====================================================================
   flow_layout.js — builds a tree:
       agent → folder → folder → ... → file
   from the data, then computes (x, y) for every node using a top-down
   tidy-tree layout. Pure functions.

   Output:
     {
       nodes: [{id, kind, label, parent, x, y, w, h, data, depth, ...}],
       edges: [{id, from, to, kind, op, ts, dur, opDetail}],
     }

   `kind` ∈ "agent" | "subagent" | "folder" | "file"
   Edges are routed orthogonally by flow_render.
   ===================================================================== */

window.LAYOUT = (function () {

  // v4.3 — bumped spacing across the board so the chart breathes
  const NODE_W = {
    agent:    180,
    subagent: 140,
    folder:   150,    // 140 → 150
    file:     110,    // 90  → 110 (file labels need room)
  };
  const NODE_H = {
    agent:    80,     // 3-line: name + pane + todo count
    subagent: 60,
    folder:   44,     // 38 → 44
    file:     64,     // 58 → 64
  };
  const LEVEL_GAP   = 130;    // 90 → 130 — more vertical breathing room
  const SIBLING_GAP = 44;     // 28 → 44 — wider gaps between siblings
  const SUB_GAP     = 80;     // 60 → 80

  /** Build single-agent flowchart for `paneId`.
   *  `subPaneIds` is the list of sub-agent panes (rendered nested under).
   *  `showHistory` includes inactive folders/files in grey if true.
   */
  function buildSingleAgent(paneId, subPaneIds, opts = {}) {
    const showHistory = !!opts.showHistory;

    const agents = DATA.agents || {};
    const files  = DATA.files  || {};
    const events = DATA.activity || [];

    const agent = agents[paneId];
    if (!agent) return { nodes: [], edges: [] };

    // Resolve which files belong to this agent (and optionally its subs)
    const ownerPanes = new Set([paneId, ...subPaneIds]);

    // Build per-pane list of files touched
    const panesToFiles = {}; // pane -> [file]
    Object.values(files).forEach(f => {
      (f.agents || []).forEach(p => {
        if (!ownerPanes.has(p)) return;
        (panesToFiles[p] = panesToFiles[p] || []).push(f);
      });
    });

    // Build folder tree per agent. We unify under a virtual root.
    // tree node: { name, fullPath, children: {seg: subnode}, files: [file] }
    function newFolder(name, fullPath) { return { name, fullPath, children: {}, files: [] }; }

    function buildTreeFor(pane) {
      const root = newFolder('', '');
      (panesToFiles[pane] || []).forEach(f => {
        const rel = f.rel_path || f.path || '';
        const parts = rel.split('/').filter(Boolean);
        if (!parts.length) return;
        let cur = root, accPath = '';
        for (let i = 0; i < parts.length - 1; i++) {
          const seg = parts[i];
          accPath = accPath ? accPath + '/' + seg : seg;
          if (!cur.children[seg]) cur.children[seg] = newFolder(seg, accPath);
          cur = cur.children[seg];
        }
        cur.files.push(f);
      });
      return root;
    }

    // Build the abstract node + edge list (no positions yet)
    const nodes = [];
    const edges = [];
    let nextId = 0;
    const id = (prefix) => `${prefix}_${++nextId}`;

    // Root agent node
    const agentId = `agent_${paneId}`;
    nodes.push({
      id: agentId,
      kind: 'agent',
      label: agent.window_name || paneId,
      sublabel: paneId,
      depth: 0,
      data: agent,
      pane: paneId,
      w: NODE_W.agent, h: NODE_H.agent,
    });

    // Sub-agents
    const subRootIds = {};
    subPaneIds.forEach((sp, i) => {
      const sa = agents[sp];
      if (!sa) return;
      const sid = `subagent_${sp}`;
      subRootIds[sp] = sid;
      nodes.push({
        id: sid, kind: 'subagent',
        label: sa.window_name || sp, sublabel: sp,
        depth: 0,
        data: sa, pane: sp,
        w: NODE_W.subagent, h: NODE_H.subagent,
      });
      edges.push({
        id: `sub_${sp}`,
        from: agentId, to: sid,
        kind: 'sub', op: 'sub',
      });
    });

    // For each pane (parent and subs), recurse its folder tree
    function attachTree(pane, rootNodeId) {
      const tree = buildTreeFor(pane);
      walk(tree, rootNodeId, 1, pane);
    }

    function walk(folderNode, parentId, depth, pane) {
      const folderKeys = Object.keys(folderNode.children);
      folderKeys.forEach(seg => {
        const sub = folderNode.children[seg];
        const fid = id('folder');
        nodes.push({
          id: fid, kind: 'folder',
          label: seg + '/', fullPath: sub.fullPath,
          depth, pane,
          data: { path: sub.fullPath },
          w: NODE_W.folder, h: NODE_H.folder,
        });
        // start every folder→folder edge as plain history; gets upgraded below
        edges.push({ id: id('e'), from: parentId, to: fid, kind: 'folder-link', _fileEdge: false });
        walk(sub, fid, depth + 1, pane);
      });
      folderNode.files.forEach(f => {
        const fid = id('file');
        const latestOp = latestOperation(f, pane, events);
        const breakdown = operationBreakdown(f, pane, events);
        nodes.push({
          id: fid, kind: 'file',
          label: (f.rel_path || '').split('/').pop(),
          fullPath: f.path || f.rel_path,
          depth, pane,
          data: { ...f, breakdown },
          w: NODE_W.file, h: NODE_H.file,
          isActive: latestOp.kind !== 'history',
          opKind: latestOp.kind,
          opTs: latestOp.ts,
        });
        edges.push({
          id: id('e'),
          from: parentId, to: fid,
          kind: latestOp.kind,
          op: latestOp.kind,
          ts: latestOp.ts,
          dur: latestOp.dur,
          opDetail: latestOp.detail,
          _fileEdge: true,
        });
      });
    }

    attachTree(paneId, agentId);
    subPaneIds.forEach(sp => attachTree(sp, subRootIds[sp]));

    // v4 — propagate activity up through folder chain
    propagateActivityUp(nodes, edges);

    // Now compute positions with a tidy-tree algorithm
    layoutTidyTree(nodes, edges);

    return { nodes, edges };
  }

  /** v4.1 — for every file edge, walk UP through parent folder edges and
   *  paint them with the SAME kind as the file edge. Active file → active
   *  parent edges (bright + pulsing). History file → history-tinted parent
   *  edges. The most-recent (by ts) op wins when multiple files share an
   *  ancestor; active beats history regardless of ts.
   *
   *  This is the fix for P1+P3: the default flowchart now shows the full
   *  coloured chain from agent → folder → folder → file at full brightness
   *  when there's an active op anywhere below. */
  function propagateActivityUp(nodes, edges) {
    const byTo = new Map();                // child -> incoming edge
    const byId = new Map(nodes.map(n => [n.id, n]));
    edges.forEach(e => { if (!byTo.has(e.to)) byTo.set(e.to, e); });

    const ACTIVE_KINDS  = ['write','edit','read','bash','perm','block'];
    const HISTORY_KINDS = ['h-write','h-edit','h-read','h-bash','h-perm','h-block'];
    function pri(kind) {
      if (ACTIVE_KINDS.includes(kind))  return 10;
      if (HISTORY_KINDS.includes(kind)) return 4;
      if (kind === 'history')           return 2;
      return 0;
    }

    edges.forEach(fileEdge => {
      if (!fileEdge._fileEdge) return;
      let propKind;
      const isActiveLeaf = ACTIVE_KINDS.includes(fileEdge.kind);
      if (isActiveLeaf) {
        propKind = fileEdge.kind;
      } else {
        const baseOp = ['write','edit','read','bash','perm','block'].includes(fileEdge.kind)
          ? fileEdge.kind
          : (fileEdge.op || 'read');
        propKind = 'h-' + baseOp;
      }
      const ts = fileEdge.ts || 0;
      const propPri = pri(propKind);

      // v4.3 — tag the leaf file node + walk upward, tagging every node we
      // pass with the same activeOpKind so CSS can tint their background
      if (isActiveLeaf) {
        const leafNode = byId.get(fileEdge.to);
        if (leafNode) leafNode.activeOpKind = propKind;
      }

      let cursor = fileEdge.from;
      let safety = 50;
      while (cursor && safety-- > 0) {
        const incoming = byTo.get(cursor);
        if (!incoming) break;
        const curPri = pri(incoming.kind);
        if (propPri > curPri || (propPri === curPri && ts > (incoming.ts || 0))) {
          incoming.kind = propKind;
          incoming.ts   = ts;
          incoming.op   = propKind.replace('h-', '');
          incoming._propagated = true;
          // v4.3 — tag the parent node too (only for active, not history)
          if (isActiveLeaf) {
            const parentNode = byId.get(incoming.from);
            if (parentNode && !parentNode.activeOpKind) {
              parentNode.activeOpKind = propKind;
            }
          }
        }
        cursor = incoming.from;
      }
    });
  }

  function opKindFromHistoryEdge(e) {
    // history edge to file — try to recover op kind from the file's recent activity
    // (already encoded in e.kind if it's a 'history' edge from latestOperation)
    // For 'history' edges with no clear op, return null so we don't tint the chain.
    if (['write','edit','read','bash','perm','block'].includes(e.kind)) return e.kind;
    return 'read';   // default tint for history-only files
  }

  /** v4.2 — path match is fuzzy: events store relative paths, files often
   *  store absolute. Match if any of these is true:
   *    eventPath === file.path           (absolute exact)
   *    eventPath === file.rel_path       (relative exact)
   *    file.path.endsWith('/' + eventPath)
   *    file.rel_path.endsWith('/' + eventPath)
   *  This single helper is THE FIX for the recurring "default-view lines
   *  not coloured" bug. The mismatch above caused every file's latestOp
   *  to be null → all edges defaulted to 'history' kind → propagation
   *  produced tinted h-* kinds, never bright active kinds.
   */
  function pathMatches(eventPath, file) {
    if (!eventPath || !file) return false;
    const p  = file.path || '';
    const rp = file.rel_path || '';
    if (eventPath === p)  return true;
    if (eventPath === rp) return true;
    if (p  && p.endsWith('/' + eventPath))  return true;
    if (rp && rp.endsWith('/' + eventPath)) return true;
    // also reverse: event might be absolute, file relative-only
    if (rp && eventPath.endsWith('/' + rp)) return true;
    return false;
  }
  // expose for use by detail_panel.js
  window.PATH_MATCHES = pathMatches;

  /** Count operations per kind on this file from this pane in recent history. */
  function operationBreakdown(file, pane, events) {
    const counts = { read: 0, write: 0, edit: 0, bash: 0, perm: 0 };
    events.forEach(e => {
      if (e.pane_id !== pane) return;
      if (!e.args || !pathMatches(e.args.file_path, file)) return;
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

  /** Sum of touches_30m for all files inside this folder subtree. */
  function countSubtreeTouches(folderNode) {
    let n = (folderNode.files || []).reduce((acc, f) => acc + (f.touches_30m || 0), 0);
    Object.values(folderNode.children || {}).forEach(c => n += countSubtreeTouches(c));
    return n;
  }

  /** Determine what the latest interesting op on this file from this pane is. */
  function latestOperation(file, pane, events) {
    let recent = null;
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      if (e.pane_id !== pane) continue;
      if (!e.args || !pathMatches(e.args.file_path, file)) continue;
      if (e.kind === 'tool_start' || e.kind === 'tool_end') {
        recent = e; break;
      }
      if (e.kind === 'permission_request') {
        recent = e; break;
      }
    }
    if (!recent) return { kind: 'history', ts: file.last_touch_ts, dur: null, detail: null };

    if (recent.kind === 'permission_request') {
      const blocked = recent.result === 'denied' || recent.result === 'error';
      return { kind: blocked ? 'block' : 'perm', ts: recent.ts, dur: null, detail: recent.tool };
    }
    const tool = (recent.tool || '').toLowerCase();
    let kind = 'history';
    if (tool === 'write') kind = 'write';
    else if (tool === 'edit') kind = 'edit';
    else if (tool === 'read' || tool === 'glob' || tool === 'grep') kind = 'read';
    else if (tool === 'bash' || tool === 'task') kind = 'bash';
    return {
      kind,
      ts: recent.ts,
      dur: recent.duration_ms,
      detail: recent.tool,
    };
  }

  /** Tidy-tree layout: build child arrays from edges, then walk top-down,
   *  centering parents over their children.
   *  v4.5 — children of each node are sorted: folders first (left), files
   *  after (right). Within each group, original order is preserved. */
  function layoutTidyTree(nodes, edges) {
    const byId = new Map(nodes.map(n => [n.id, n]));
    const childrenOf = new Map();
    nodes.forEach(n => childrenOf.set(n.id, []));
    edges.forEach(e => {
      if (e.kind === 'sub') {
        // sub-agents are placed beside, not below — handled separately
        return;
      }
      childrenOf.get(e.from).push(e.to);
    });

    // v4.5 — sort children of every node: folders before files
    const kindRank = { folder: 0, file: 1, subagent: 2 };
    childrenOf.forEach((kids) => {
      kids.sort((a, b) => {
        const ka = byId.get(a)?.kind || 'file';
        const kb = byId.get(b)?.kind || 'file';
        const ra = kindRank[ka] ?? 9;
        const rb = kindRank[kb] ?? 9;
        if (ra !== rb) return ra - rb;
        // within same kind, alphabetical for stability
        const la = byId.get(a)?.label || '';
        const lb = byId.get(b)?.label || '';
        return la.localeCompare(lb);
      });
    });

    // Roots: nodes with no incoming non-sub edge
    const incoming = new Set();
    edges.forEach(e => { if (e.kind !== 'sub') incoming.add(e.to); });
    const roots = nodes.filter(n => !incoming.has(n.id) && n.kind === 'agent');

    // Position each root and its subtree
    let cursorX = 0;
    roots.forEach(root => {
      const w = computeSubtreeWidth(root.id, byId, childrenOf);
      placeSubtree(root.id, byId, childrenOf, cursorX + w / 2, 0);
      cursorX += w + SIBLING_GAP * 2;
    });

    // Place sub-agents to the right of the parent agent at the same y level
    edges.forEach(e => {
      if (e.kind !== 'sub') return;
      const parent = byId.get(e.from);
      const sub    = byId.get(e.to);
      if (!parent || !sub) return;
      // Stack subs to the right of parent
      const existingSubs = edges.filter(x => x.kind === 'sub' && x.from === e.from).map(x => x.to);
      const idx = existingSubs.indexOf(e.to);
      sub.x = parent.x + parent.w / 2 + SUB_GAP + idx * (NODE_W.subagent + 20) + NODE_W.subagent / 2;
      sub.y = parent.y;
      // Now also lay out the sub's subtree starting from sub
      const subW = computeSubtreeWidth(sub.id, byId, childrenOf);
      placeSubtree(sub.id, byId, childrenOf, sub.x, sub.y, /*skipSelf*/ true);
    });
  }

  function computeSubtreeWidth(id, byId, childrenOf) {
    const node = byId.get(id);
    if (!node) return 0;
    const kids = childrenOf.get(id) || [];
    if (!kids.length) return node.w;
    const childrenWidth = kids
      .map(k => computeSubtreeWidth(k, byId, childrenOf))
      .reduce((a, b) => a + b, 0)
      + (kids.length - 1) * SIBLING_GAP;
    return Math.max(node.w, childrenWidth);
  }

  function placeSubtree(id, byId, childrenOf, centerX, depthY, skipSelf = false) {
    const node = byId.get(id);
    if (!node) return;
    if (!skipSelf) {
      // v3.5.3 — snap to integer pixels. Strokes and text on subpixel
      // boundaries render fuzzy under WebKitGTK; we round here so the
      // entire downstream pipeline (node placement, edge endpoints,
      // labels) inherits integer coordinates.
      node.x = Math.round(centerX);
      node.y = Math.round(depthY);
    }
    const kids = childrenOf.get(id) || [];
    if (!kids.length) return;

    const widths = kids.map(k => computeSubtreeWidth(k, byId, childrenOf));
    const totalW = widths.reduce((a, b) => a + b, 0) + (kids.length - 1) * SIBLING_GAP;
    let x = centerX - totalW / 2;
    kids.forEach((k, i) => {
      const w = widths[i];
      placeSubtree(k, byId, childrenOf, x + w / 2, depthY + LEVEL_GAP);
      x += w + SIBLING_GAP;
    });
  }

  /** v4.4 — ORGANIC WEB overview.
   *
   *  Agents are placed in a ring. Files are scattered around their agent
   *  with gentle jitter so shared files drift between their agents. Edges
   *  are organic curved beziers. The result looks like a mycelium web
   *  rather than a strict flowchart grid.
   *
   *  Territory data (per-agent bounding hull) is returned in `territories`
   *  so flow_render can draw the dotted enclosure borders.
   */
  function buildOverview(visiblePanes) {
    const agents = DATA.agents || {};
    const files  = DATA.files  || {};
    const events = DATA.activity || [];

    const nodes = [];
    const edges = [];
    const territories = [];   // [{pane, cx, cy, rx, ry, colour}]
    let nextId = 0;
    const uid = p => `${p}_${++nextId}`;

    visiblePanes = visiblePanes.filter(p => agents[p]);
    if (!visiblePanes.length) return { nodes, edges, territories };

    // --- 1. Place agents in a ring ----------------------------------------
    const N = visiblePanes.length;
    const RING_R = Math.max(240, N * 80);   // ring radius scales with count
    const agentPos = {};
    visiblePanes.forEach((p, i) => {
      const angle = (2 * Math.PI * i / N) - Math.PI / 2;
      const cx = Math.round(Math.cos(angle) * RING_R);
      const cy = Math.round(Math.sin(angle) * RING_R);
      agentPos[p] = { x: cx, y: cy };
      const a = agents[p];
      nodes.push({
        id: `agent_${p}`, kind: 'agent',
        label: a.window_name || p, sublabel: p,
        x: cx, y: cy,
        w: NODE_W.agent, h: NODE_H.agent,
        data: a, pane: p,
      });
    });

    // --- 2. Find recent ops per pane (≤4 files each) ----------------------
    const ACTIVE_TOOLS = { write:'write', edit:'edit', read:'read', glob:'read', grep:'read', bash:'bash', task:'bash' };
    const paneFiles = new Map();
    visiblePanes.forEach(p => {
      const seen = new Set();
      const out  = [];
      for (const e of events) {
        if (e.pane_id !== p) continue;
        if (!e.args || !e.args.file_path) continue;
        if (e.kind !== 'tool_start' && e.kind !== 'tool_end') continue;
        const fp = e.args.file_path;
        if (seen.has(fp)) continue;
        seen.add(fp);
        const kind = ACTIVE_TOOLS[(e.tool || '').toLowerCase()] || 'history';
        // look up the file record
        let fileRec = files[fp];
        if (!fileRec) {
          // try rel_path match
          fileRec = Object.values(files).find(f => pathMatches(fp, f));
        }
        if (!fileRec) fileRec = { path: fp, rel_path: fp, agents: [p] };
        out.push({ file: fileRec, kind, ts: e.ts, dur: e.duration_ms });
        if (out.length >= 4) break;
      }
      paneFiles.set(p, out);
    });

    // --- 3. Place file nodes near their agent with jitter -----------------
    const FILE_ORBIT = 180;    // average distance from agent centre
    visiblePanes.forEach((p, ai) => {
      const aPos = agentPos[p];
      const fps  = paneFiles.get(p) || [];
      const seenFids = new Set();

      // territory bounding box
      let minX = aPos.x, maxX = aPos.x, minY = aPos.y, maxY = aPos.y;

      fps.forEach((ep, fi) => {
        // Angle biased away from ring centre (outward spread)
        const spreadAngle = (2 * Math.PI * (ai + 0.5) / N) - Math.PI / 2;
        const jitter = ((fi - fps.length / 2) * 0.4);
        const ang = spreadAngle + jitter;
        const dist = FILE_ORBIT + (fi % 2 === 0 ? -20 : 30);
        const fx = Math.round(aPos.x + Math.cos(ang) * dist);
        const fy = Math.round(aPos.y + Math.sin(ang) * dist);

        const fid = `file_${p}_${fi}`;
        nodes.push({
          id: fid, kind: 'file',
          label: (ep.file.rel_path || ep.file.path || '').split('/').pop(),
          fullPath: ep.file.path || ep.file.rel_path,
          x: fx, y: fy,
          w: NODE_W.file, h: NODE_H.file,
          data: ep.file, pane: p,
          isActive: ep.kind !== 'history',
          opKind: ep.kind,
        });
        edges.push({
          id: uid('e'),
          from: `agent_${p}`, to: fid,
          kind: ep.kind, op: ep.kind,
          ts: ep.ts, dur: ep.dur,
        });

        // expand territory
        minX = Math.min(minX, fx - NODE_W.file / 2);
        maxX = Math.max(maxX, fx + NODE_W.file / 2);
        minY = Math.min(minY, fy - NODE_H.file);
        maxY = Math.max(maxY, fy + NODE_H.file);
      });

      // territory ellipse centred on the cluster, padded
      const PAD = 36;
      const a = agents[p];
      territories.push({
        pane: p,
        agentLabel: (a.window_name || p) + ' ' + p,
        cx: (minX + maxX) / 2,
        cy: (minY + maxY) / 2,
        rx: Math.max(80, (maxX - minX) / 2 + PAD),
        ry: Math.max(60, (maxY - minY) / 2 + PAD),
      });
    });

    return { nodes, edges, territories };
  }

  return { buildSingleAgent, buildOverview };
})();
