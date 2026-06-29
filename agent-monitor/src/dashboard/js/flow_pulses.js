/* =====================================================================
   flow_pulses.js v3 — directional pulse particles on active edges.

   v3: supports both ortho and curved bezier paths.
   ===================================================================== */

window.PULSES = (function () {

  let group;
  let edgeStates = new Map();
  const SPEED = 0.45;
  const PULSES_PER_EDGE = 2;

  function init() {
    group = document.getElementById('layer-pulses');
    requestAnimationFrame(loop);
  }

  function colorFor(op) {
    return getComputedStyle(document.documentElement).getPropertyValue(`--op-${op}`).trim() || '#fff';
  }

  function loop() {
    const edges = FLOW.getActiveEdges();
    const dt = 1 / 60;

    // v4.3 — always refresh from/to with the LIVE node references from the
    // active edge map (which is rebuilt on each FLOW.render). This ensures
    // that after a re-layout (e.g. spacing changes, theme switch), pulses
    // ride the new path positions, not stale ones.
    edges.forEach((info, id) => {
      if (!edgeStates.has(id)) {
        edgeStates.set(id, {
          edge: info.edge,
          from: info.from, to: info.to,
          pulses: Array.from({ length: PULSES_PER_EDGE }, (_, i) => ({ t: i / PULSES_PER_EDGE })),
        });
      } else {
        const s = edgeStates.get(id);
        s.from = info.from; s.to = info.to; s.edge = info.edge;
      }
    });
    [...edgeStates.keys()].forEach(id => { if (!edges.has(id)) edgeStates.delete(id); });

    const style = (getComputedStyle(document.documentElement).getPropertyValue('--edge-style') || 'curve').trim();

    let html = '';
    edgeStates.forEach((state) => {
      const e = state.edge;
      const reverse = e.kind === 'read';
      const from = reverse ? state.to : state.from;
      const to   = reverse ? state.from : state.to;
      const color = colorFor(e.kind);
      const pointAt = (t) => style === 'ortho'
        ? pointOnOrthogonalPath(from, to, t)
        : pointOnCurve(from, to, t, style);

      // v4.4 — pulse size driven by --pulse-r CSS var (style options)
      const pr = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--pulse-r')) || 4.5;
      state.pulses.forEach(p => {
        p.t += SPEED * dt;
        if (p.t >= 1) p.t -= 1;
        const pos = pointAt(p.t);
        html += `<circle class="pulse-dot" cx="${pos.x}" cy="${pos.y}" r="${pr}" fill="${color}"/>`;
        const tt1 = p.t - 0.06; if (tt1 >= 0) {
          const tp = pointAt(tt1);
          html += `<circle cx="${tp.x}" cy="${tp.y}" r="${(pr * 0.65).toFixed(1)}" fill="${color}" opacity="0.55"/>`;
        }
        const tt2 = p.t - 0.12; if (tt2 >= 0) {
          const tp = pointAt(tt2);
          html += `<circle cx="${tp.x}" cy="${tp.y}" r="${(pr * 0.33).toFixed(1)}" fill="${color}" opacity="0.3"/>`;
        }
      });
    });
    group.innerHTML = html;

    requestAnimationFrame(loop);
  }

  // v4: use the shared anchor helpers from flow_render — pulses now match paths exactly
  function exitPoint(n) {
    return (window._EDGE_ANCHORS && window._EDGE_ANCHORS.exitPoint)
      ? window._EDGE_ANCHORS.exitPoint(n)
      : { x: n.x, y: n.y + n.h / 2 };
  }
  function entryPoint(n) {
    return (window._EDGE_ANCHORS && window._EDGE_ANCHORS.entryPoint)
      ? window._EDGE_ANCHORS.entryPoint(n)
      : { x: n.x, y: n.y - n.h / 2 };
  }

  function pointOnOrthogonalPath(from, to, t) {
    const p1 = exitPoint(from);
    const p2 = entryPoint(to);
    const midY = p1.y + (p2.y - p1.y) / 2;

    const seg1 = Math.abs(midY - p1.y);
    const seg2 = Math.abs(p2.x - p1.x);
    const seg3 = Math.abs(p2.y - midY);
    const total = seg1 + seg2 + seg3;
    if (total === 0) return { x: p1.x, y: p1.y };

    let d = t * total;
    if (d <= seg1) return { x: p1.x, y: p1.y + (midY - p1.y) * (seg1 ? d / seg1 : 0) };
    d -= seg1;
    if (d <= seg2) return { x: p1.x + (p2.x - p1.x) * (seg2 ? d / seg2 : 0), y: midY };
    d -= seg2;
    return { x: p2.x, y: midY + (p2.y - midY) * (seg3 ? d / seg3 : 0) };
  }

  function pointOnCurve(from, to, t, style) {
    // Cubic bezier: MUST match curvedPath() in flow_render.js exactly
    const p1 = exitPoint(from);
    const p2 = entryPoint(to);
    const dy = Math.abs(p2.y - p1.y);
    // 'arc' = tighter curve; 'curve' = standard; matches flow_render
    const cy = style === 'arc' ? Math.max(20, dy * 0.28) : Math.max(40, dy * 0.55);
    const cp1x = p1.x, cp1y = p1.y + cy;
    const cp2x = p2.x, cp2y = p2.y - cy;
    const u = 1 - t;
    const x = u*u*u*p1.x + 3*u*u*t*cp1x + 3*u*t*t*cp2x + t*t*t*p2.x;
    const y = u*u*u*p1.y + 3*u*u*t*cp1y + 3*u*t*t*cp2y + t*t*t*p2.y;
    return { x, y };
  }

  return { init };
})();
