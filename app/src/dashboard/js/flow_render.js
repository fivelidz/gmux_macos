/* =====================================================================
   flow_render.js v3 — SVG flowchart renderer.

   v3 changes:
   - Active edges drawn on separate layer ABOVE history edges (point #2)
   - "1%/2%" labels replaced with "#N ops" format (point #7)
   - Curved bezier edges when --edge-style: curve (theme-coupled, point #4)
   - Auto-fit smoothly on watching change (point #6, app.js triggers)
   ===================================================================== */

window.FLOW = (function () {
  const { esc, fmtTime, fmtDur } = UTIL;

  let svg, gPan, gNodes, gEdgesH, gEdgesA, gLabels, gTerritories, hint, emptyEl;
  let cam = { x: 0, y: 0, k: 0.9 };
  let camTarget = null;        // for smooth auto-fit
  let dragging = false, dragLast = null;
  let model = { nodes: [], edges: [] };
  let selectedId = null;
  let activeEdgesById = new Map();
  let onNodeClick = () => {};

  function init() {
    svg          = document.getElementById('flow');
    gPan         = document.getElementById('flow-pan');
    gNodes       = document.getElementById('layer-nodes');
    gEdgesH      = document.getElementById('layer-edges-history');
    gEdgesA      = document.getElementById('layer-edges-active');
    gLabels      = document.getElementById('layer-edge-labels');
    gTerritories = document.getElementById('layer-territories');
    hint    = document.getElementById('canvas-hint');
    emptyEl = document.getElementById('canvas-empty');

    svg.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
    svg.addEventListener('wheel',        onWheel, { passive: false });
    svg.addEventListener('click',        onCanvasClick);

    requestAnimationFrame(animLoop);
  }

  function setOnNodeClick(fn) { onNodeClick = fn; }
  function setEmpty(yes) { emptyEl.classList.toggle('hidden', !yes); }

  function render(newModel, opts = {}) {
    model = newModel;
    if (!model.nodes.length) {
      gNodes.innerHTML = ''; gEdgesH.innerHTML = ''; gEdgesA.innerHTML = ''; gLabels.innerHTML = '';
      if (gTerritories) gTerritories.innerHTML = '';
      activeEdgesById.clear();
      setEmpty(true);
      return;
    }
    setEmpty(false);
    if (opts.autofit) requestFit();
    drawTerritories();    // v4.4 — must render before edges/nodes so it sits behind
    drawEdges();
    drawNodes();
    drawEdgeLabels();
    applyTransform();
  }

  /** v4.4 — dotted territory borders for the organic overview.
   *  Renders only when model.territories is provided (overview mode). */
  function drawTerritories() {
    if (!gTerritories) return;
    if (!model.territories || !model.territories.length) {
      gTerritories.innerHTML = '';
      return;
    }
    let html = '';
    model.territories.forEach((t, i) => {
      const label = (t.agentLabel || t.pane || '').toString();
      html += `
        <g class="territory" data-pane="${esc(t.pane)}">
          <ellipse cx="${t.cx}" cy="${t.cy}" rx="${t.rx}" ry="${t.ry}"
                   class="territory-shape" />
          <text class="territory-label" x="${t.cx}" y="${t.cy - t.ry - 6}"
                text-anchor="middle">${esc(label)}</text>
        </g>
      `;
    });
    gTerritories.innerHTML = html;
  }

  function drawEdges() {
    activeEdgesById.clear();
    const byId = new Map(model.nodes.map(n => [n.id, n]));
    let historyHtml = '';
    let activeHtml  = '';
    model.edges.forEach(e => {
      const a = byId.get(e.from);
      const b = byId.get(e.to);
      if (!a || !b) return;
      const path = computePath(a, b);
      const cls = edgeCls(e);
      const marker = arrowMarker(e);
      const html = `<path class="edge ${cls}" d="${path}" data-edge-id="${esc(e.id)}" ${marker ? `marker-end="url(#${marker})"` : ''}/>`;
      if (isActive(e.kind)) {
        activeHtml += html;
        activeEdgesById.set(e.id, { edge: e, path, from: a, to: b });
      } else {
        historyHtml += html;
      }
    });
    gEdgesH.innerHTML = historyHtml;
    gEdgesA.innerHTML = activeHtml;
  }

  function drawNodes() {
    let html = '';
    // v4.1 — no more dimming non-neighbours. Selection ring is enough.
    // v4.3 — tint nodes touched by the active chain with op-<kind>
    model.nodes.forEach(n => {
      const sel = (n.id === selectedId) ? 'selected' : '';
      const opTint = n.activeOpKind ? `op-${esc(n.activeOpKind)}` : '';
      if (n.kind === 'agent' || n.kind === 'subagent') {
        const stateCls = `s-${esc(n.data?.state || 'idle')}`;
        // v4.2 — show N/M todos on the canvas agent node
        const td  = n.data?.todo_done  || 0;
        const tt  = n.data?.todo_total || 0;
        const todoStr = tt ? `${td}/${tt} todos` : '';
        const todoCls = (tt && td >= tt) ? 'todo-line done' : 'todo-line';
        // v4.4: tint rect injected inline — no color-mix(), works in all browsers
        const tintRect = opTint ? `<rect class="tint-rect" width="${n.w}" height="${n.h}" rx="${n.kind === 'agent' ? 26 : 20}"/>` : '';
        html += `
          <g class="node node-${n.kind} ${stateCls} ${sel} ${opTint}" data-node-id="${esc(n.id)}" transform="translate(${n.x - n.w / 2},${n.y - n.h / 2})">
            <rect width="${n.w}" height="${n.h}"/>
            ${tintRect}
            <text class="label"     x="${n.w / 2}" y="${n.h / 2 - 14}">${esc(n.label)}</text>
            <text class="sublabel"  x="${n.w / 2}" y="${n.h / 2 + 3}">${esc(n.sublabel || '')}</text>
            ${todoStr ? `<text class="${todoCls}" x="${n.w / 2}" y="${n.h / 2 + 20}">${esc(todoStr)}</text>` : ''}
            ${sel ? `<rect class="ring" x="-6" y="-6" width="${n.w + 12}" height="${n.h + 12}" rx="${n.kind === 'agent' ? 32 : 26}"/>` : ''}
          </g>
        `;
      } else if (n.kind === 'folder') {
        const tintRectF = opTint ? `<rect class="tint-rect" width="${n.w}" height="${n.h}" rx="8"/>` : '';
        html += `
          <g class="node node-folder ${sel} ${opTint}" data-node-id="${esc(n.id)}" transform="translate(${n.x - n.w / 2},${n.y - n.h / 2})">
            <rect width="${n.w}" height="${n.h}"/>
            ${tintRectF}
            <text x="${n.w / 2}" y="${n.h / 2}">${esc(n.label)}</text>
            ${sel ? `<rect class="ring" x="-6" y="-6" width="${n.w + 12}" height="${n.h + 12}" rx="14"/>` : ''}
          </g>
        `;
      } else if (n.kind === 'file') {
        const r = 14;
        const opLabel = n.opKind && n.opKind !== 'history' ? n.opKind.toUpperCase() : '';
        const activeCls = n.isActive ? 'is-active' : '';
        html += `
          <g class="node node-file ${activeCls} ${sel} ${opTint}" data-node-id="${esc(n.id)}" transform="translate(${n.x},${n.y - n.h / 2 + r})">
            <circle r="${r}" cx="0" cy="0"/>
            <text class="label" y="${r + 14}">${esc(n.label)}</text>
            ${opLabel ? `<text class="op" y="${r + 26}" style="fill:var(--op-${esc(n.opKind)})">${esc(opLabel)}</text>` : ''}
            ${sel ? `<circle class="ring" r="${r + 6}" cx="0" cy="0"/>` : ''}
          </g>
        `;
      }
    });
    gNodes.innerHTML = html;

    gNodes.querySelectorAll('.node').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = el.dataset.nodeId;
        const node = model.nodes.find(n => n.id === id);
        if (!node) return;
        selectedId = id;
        drawNodes();
        drawEdgeLabels();
        onNodeClick(node);
      });
    });
  }

  // v4.4 — style options: showLabels can be disabled via the style panel
  let showLabels = true;
  function setShowLabels(v) { showLabels = v; gLabels.innerHTML = ''; }

  function drawEdgeLabels() {
    if (!showLabels) { gLabels.innerHTML = ''; return; }

    // In default mode: one label per chain, on the leaf (file-terminal) edge.
    // In overview: label on every edge (each edge is already a direct pair).
    let html = '';
    const byId = new Map(model.nodes.map(n => [n.id, n]));
    const overview = document.body.classList.contains('overview-mode');
    model.edges.forEach(e => {
      if (!isActive(e.kind)) return;
      const a = byId.get(e.from);
      const b = byId.get(e.to);
      if (!a || !b) return;
      if (!overview && b.kind !== 'file') return;

      // v4.4 — label positioned to the RIGHT of the midpoint of the edge,
      // offset perpendicular to the path so it never covers the line itself.
      // For a roughly vertical bezier: perpendicular ≈ horizontal.
      // We use the midpoint of the bezier (t=0.5) plus a 48px rightward nudge.
      const mid = labelMidpoint(a, b);
      const lx = mid.x + 48;   // offset to the right
      const ly = mid.y;

      // v4.4 — timer-only label: just the elapsed / fixed duration. Compact.
      const dur = e.dur != null ? fmtDur(e.dur) : '';
      const cls = e.kind;
      const boxW = 56, boxH = 22;
      html += `
        <g class="edge-label ${cls}" data-edge-id="${esc(e.id)}" data-ts="${esc(e.ts || '')}" data-dur="${e.dur != null ? e.dur : ''}" transform="translate(${lx - boxW / 2},${ly - boxH / 2})" pointer-events="none">
          <rect class="edge-label-bg" width="${boxW}" height="${boxH}" rx="4"/>
          <text class="op-dur" x="${boxW / 2}" y="${boxH / 2 + 4}" text-anchor="middle">${esc(dur || '…')}</text>
        </g>
      `;
    });
    gLabels.innerHTML = html;
  }

  /** Get the visual midpoint of a bezier/ortho edge between two nodes */
  function labelMidpoint(a, b) {
    const style = (getComputedStyle(document.documentElement).getPropertyValue('--edge-style') || 'curve').trim();
    if (style === 'ortho') {
      const p1 = exitPoint(a);
      const p2 = entryPoint(b);
      return { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
    }
    // bezier t=0.5
    const { exitPoint: ep, entryPoint: enp } = window._EDGE_ANCHORS || { exitPoint: n => ({x:n.x,y:n.y+n.h/2}), entryPoint: n => ({x:n.x,y:n.y-n.h/2}) };
    const p1 = ep(a), p2 = enp(b);
    const dy = Math.abs(p2.y - p1.y);
    const cy = Math.max(40, dy * 0.55);
    const cp1y = p1.y + cy, cp2y = p2.y - cy;
    const t = 0.5, u = 0.5;
    const x = u*u*u*p1.x + 3*u*u*t*p1.x + 3*u*t*t*p2.x + t*t*t*p2.x;
    const y = u*u*u*p1.y + 3*u*u*t*cp1y + 3*u*t*t*cp2y + t*t*t*p2.y;
    return { x, y };
  }

  /** v4.4 — tick the running timer on in-flight op labels every rAF frame.
   *  Shows ONLY elapsed time — no op name, no timestamp-of-day. */
  function tickRunningTimers() {
    if (!gLabels || !showLabels) return;
    const groups = gLabels.querySelectorAll('.edge-label');
    if (!groups.length) return;
    const now = Date.now();
    groups.forEach(g => {
      const tsStr = g.dataset.ts;
      if (!tsStr) return;
      const tsMs = new Date(tsStr).getTime();
      const fixedDur = g.dataset.dur;
      let txt;
      if (fixedDur !== '' && fixedDur !== undefined && fixedDur !== 'null') {
        // completed — show the final duration, don't tick
        txt = fmtDur(+fixedDur);
      } else {
        // in-flight — show live elapsed
        const ms = Math.max(0, now - tsMs);
        txt = formatRunningMs(ms);
      }
      const durEl = g.querySelector('.op-dur');
      if (durEl && durEl.textContent !== txt) durEl.textContent = txt;
    });
  }
  function formatRunningMs(ms) {
    if (ms < 1000) return ms + 'ms';
    if (ms < 60_000) return (ms / 1000).toFixed(1) + 's';
    if (ms < 3_600_000) return Math.floor(ms / 60_000) + 'm ' + Math.floor((ms % 60_000) / 1000) + 's';
    return '>1h';
  }

  function runningDuration(ts) {
    if (!ts) return '';
    const ms = Date.now() - new Date(ts).getTime();
    if (ms < 0 || ms > 60_000) return '';
    return fmtDur(ms);
  }

  /** Select edge style: 'ortho' or 'curve' from CSS theme variable. */
  function computePath(a, b) {
    const style = (getComputedStyle(document.documentElement).getPropertyValue('--edge-style') || 'curve').trim();
    return style === 'ortho' ? orthogonalPath(a, b) : curvedPath(a, b);
  }

  /** v4: anchor a node-position for edge endpoints. Files are circles
   *  rendered offset within their bbox; use circle centre for those. */
  function exitPoint(n) {
    // bottom of node (for outgoing)
    if (n.kind === 'file') {
      // file circle centre + radius
      const r = 14;
      const cy = n.y - n.h / 2 + r;
      return { x: n.x, y: cy + r };
    }
    return { x: n.x, y: n.y + n.h / 2 };
  }
  function entryPoint(n) {
    // top of node (for incoming)
    if (n.kind === 'file') {
      const r = 14;
      const cy = n.y - n.h / 2 + r;
      return { x: n.x, y: cy - r };
    }
    return { x: n.x, y: n.y - n.h / 2 };
  }

  /** v4.5.1 — deterministic per-edge nudge (so it doesn't jitter on re-render).
   *  Hashes the from→to ids to a small ±2..±3 offset. Only applied when
   *  the edge would otherwise be perfectly vertical (which would give it
   *  a zero-width bbox and make the glow filter output nothing). */
  function edgeNudge(a, b) {
    const s = (a.id || '') + '→' + (b.id || '');
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    const sign = (h % 2 === 0) ? 1 : -1;
    const mag  = 2 + (Math.abs(h) % 2);   // 2 or 3 px
    return sign * mag;
  }

  function orthogonalPath(a, b) {
    const p1 = exitPoint(a);
    const p2 = entryPoint(b);
    const midY = p1.y + (p2.y - p1.y) / 2;
    // v4.5.1 — if vertical, shift the mid-segment sideways so bbox > 0
    if (Math.abs(p1.x - p2.x) < 0.5) {
      const midX = p1.x + edgeNudge(a, b);
      return `M ${p1.x} ${p1.y} L ${p1.x} ${midY - 6} Q ${p1.x} ${midY}, ${midX} ${midY} Q ${p2.x} ${midY}, ${p2.x} ${midY + 6} L ${p2.x} ${p2.y}`;
    }
    return `M ${p1.x} ${p1.y} L ${p1.x} ${midY} L ${p2.x} ${midY} L ${p2.x} ${p2.y}`;
  }

  /** Curved bezier — control points pulled vertically for a flowy "river" feel.
   *  'arc' mode = tighter; must match pointOnCurve() in flow_pulses.js. */
  function curvedPath(a, b) {
    const style = (getComputedStyle(document.documentElement).getPropertyValue('--edge-style') || 'curve').trim();
    const p1 = exitPoint(a);
    const p2 = entryPoint(b);
    const dy = Math.abs(p2.y - p1.y);
    const cy = style === 'arc' ? Math.max(20, dy * 0.28) : Math.max(40, dy * 0.55);
    // v4.5.1 — nudge control points sideways when path would be vertical,
    // for the same reason: keep the bbox width > 0 so the glow filter region
    // actually has area. The nudge is deterministic per-edge so it doesn't
    // animate, and small enough (±2..3px) to look subtly organic.
    const verticalish = Math.abs(p1.x - p2.x) < 0.5;
    const nudge = verticalish ? edgeNudge(a, b) : 0;
    const cx1 = p1.x + nudge;
    const cx2 = p2.x - nudge * 0.6;
    return `M ${p1.x} ${p1.y} C ${cx1} ${p1.y + cy}, ${cx2} ${p2.y - cy}, ${p2.x} ${p2.y}`;
  }

  // export for pulses.js
  window._EDGE_ANCHORS = { exitPoint, entryPoint };

  function edgeCls(e) {
    if (e.kind === 'sub')          return 'sub-link';
    if (e.kind === 'folder-link')  return 'history';
    if (['write','edit','read','bash','perm','block'].includes(e.kind)) return e.kind;
    // v4: history edges keep their op-tinted colour
    if (['h-write','h-edit','h-read','h-bash','h-perm','h-block'].includes(e.kind)) return e.kind;
    return 'history';
  }
  function arrowMarker(e) {
    if (['write','edit','read','bash','perm','block'].includes(e.kind)) return 'ah-' + e.kind;
    return null;
  }
  function isActive(kind) {
    return ['write','edit','read','bash','perm','block'].includes(kind);
  }
  function isNeighbour(id) {
    if (id === selectedId) return true;
    return model.edges.some(e =>
      (e.from === selectedId && e.to === id) ||
      (e.to === selectedId   && e.from === id));
  }

  function deselect() {
    selectedId = null;
    drawNodes();
    drawEdgeLabels();
  }

  /* ---------------- camera / autofit / smooth animation ---------------- */
  function applyTransform() {
    // v3.5.3 — snap pan offset to integer pixels so node strokes and text
    // don't fall on half-pixel boundaries (which is what makes them look
    // fuzzy on WebKitGTK). Scale is kept full-precision because rounding
    // it would jitter on smooth zooms. Internal node coordinates are
    // already integers from the layout pass.
    const tx = Math.round(cam.x);
    const ty = Math.round(cam.y);
    gPan.setAttribute('transform', `translate(${tx},${ty}) scale(${cam.k})`);
  }

  function requestFit() {
    if (!model.nodes.length) return;
    const xs = model.nodes.map(n => n.x);
    const ys = model.nodes.map(n => n.y);
    const minX = Math.min(...xs) - 100;
    const maxX = Math.max(...xs) + 100;
    const minY = Math.min(...ys) - 80;
    const maxY = Math.max(...ys) + 100;
    const w = maxX - minX;
    const h = maxY - minY;
    const r = svg.getBoundingClientRect();
    const k = Math.min(0.95, Math.min(r.width / w, r.height / h));
    const targetK = Math.max(0.3, Math.min(1.5, k));
    camTarget = {
      k: targetK,
      x: r.width  / 2 - ((minX + maxX) / 2) * targetK,
      y: r.height / 2 - ((minY + maxY) / 2) * targetK,
    };
  }

  function animLoop() {
    if (camTarget) {
      const ease = 0.18;
      cam.x += (camTarget.x - cam.x) * ease;
      cam.y += (camTarget.y - cam.y) * ease;
      cam.k += (camTarget.k - cam.k) * ease;
      if (Math.abs(camTarget.x - cam.x) < 0.5 && Math.abs(camTarget.y - cam.y) < 0.5 && Math.abs(camTarget.k - cam.k) < 0.005) {
        cam.x = camTarget.x; cam.y = camTarget.y; cam.k = camTarget.k;
        camTarget = null;
      }
      applyTransform();
    }

    // v4.1 — overview mode time-decay
    if (document.body.classList.contains('overview-mode')) {
      applyTimeDecay();
    }

    // v4.3 — running-timer tick on in-flight op labels
    tickRunningTimers();

    requestAnimationFrame(animLoop);
  }

  /** v4.1 — recompute per-edge opacity from age. Cheap (under ~20 edges
   *  in overview mode) and avoids DOM rebuild. */
  function applyTimeDecay() {
    const now = Date.now();
    activeEdgesById.forEach((info, id) => {
      const e = info.edge;
      const tsMs = e.ts ? new Date(e.ts).getTime() : now;
      const ageSec = Math.max(0, (now - tsMs) / 1000);
      let opacity = 1;
      let stale = false;
      if (ageSec < 5) {
        opacity = 1;
      } else if (ageSec < 30) {
        // linear ramp from 1 to 0.3
        opacity = 1 - ((ageSec - 5) / 25) * 0.7;
      } else {
        opacity = 0.15;
        stale = true;
      }
      const node = gEdgesA.querySelector(`[data-edge-id="${cssEscape(id)}"]`);
      if (node) {
        node.style.opacity = opacity.toFixed(2);
        node.classList.toggle('stale', stale);
      }
    });
  }
  function cssEscape(s) { return (s || '').replace(/"/g, '\\"'); }

  function autoFit() { requestFit(); }

  // Pan / zoom
  function onDown(e) {
    if (e.target.closest('.node')) return;     // don't pan when starting drag on a node
    dragging = true; dragLast = { x: e.clientX, y: e.clientY };
    camTarget = null;
  }
  function onUp() { dragging = false; }
  function onMove(e) {
    if (!dragging) return;
    cam.x += e.clientX - dragLast.x;
    cam.y += e.clientY - dragLast.y;
    dragLast = { x: e.clientX, y: e.clientY };
    applyTransform();
  }
  function onWheel(e) {
    e.preventDefault();
    camTarget = null;
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    const r = svg.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const newK = Math.max(0.3, Math.min(2.5, cam.k * factor));
    cam.x = mx - (mx - cam.x) * (newK / cam.k);
    cam.y = my - (my - cam.y) * (newK / cam.k);
    cam.k = newK;
    applyTransform();
  }
  function onCanvasClick(e) {
    if (e.target === svg || e.target === gPan ||
        e.target.id === 'layer-edges-history' || e.target.id === 'layer-edges-active') {
      deselect();
      onNodeClick(null);
    }
  }

  function getActiveEdges() { return activeEdgesById; }

  return { init, render, deselect, setOnNodeClick, getActiveEdges, autoFit, setShowLabels };
})();
