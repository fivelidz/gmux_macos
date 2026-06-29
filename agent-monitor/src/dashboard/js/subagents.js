/* =====================================================================
   subagents.js — manages sub-agent groupings.

   v3.7: Two sources of sub-agent relationships are merged:

   1. localStorage (manual user groupings, pre-v3.7):
      Persisted as { childPaneId: parentPaneId } in the browser.
      Allows the user to manually group any pane under any other.

   2. Backend-driven (gmux-spawned sub-agents, v3.7+):
      When a sub-agent is spawned via spawn_sub_agent (Rust), monitor.py
      merges `parent_pane_id` and `is_child_pane` into the pane's state
      dict. These are read from DATA.agents and take precedence over manual
      groupings for panes where is_child_pane is set.

   childrenOf(pane) returns the union of both sources filtered to panes
   that are currently alive in DATA.agents.
   ===================================================================== */

window.SUBAGENTS = (function () {
  const STORAGE_KEY = 'gmux-dashboard-subagents';
  let map = {};

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) map = JSON.parse(raw);
    } catch (_) { map = {}; }
  }

  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(map)); } catch (_) {}
  }

  function setSub(childPane, parentPane) {
    if (childPane === parentPane) return;
    map[childPane] = parentPane;
    save();
  }
  function unsetSub(childPane) {
    delete map[childPane];
    save();
  }

  /** Return the parent pane_id for a given child pane_id.
   *  Checks backend-driven parent_pane_id first (v3.7), then localStorage. */
  function parentOf(pane) {
    const agents = (typeof DATA !== 'undefined' && DATA.agents) ? DATA.agents : {};
    const a = agents[pane];
    if (a && a.is_child_pane && a.parent_pane_id) return a.parent_pane_id;
    return map[pane] || null;
  }

  /** Return all child pane_ids for a given parent pane_id.
   *  Merges backend-driven children (panes with parent_pane_id) and
   *  localStorage children. Only returns panes present in DATA.agents
   *  (i.e. currently alive in tmux). */
  function childrenOf(pane) {
    const agents = (typeof DATA !== 'undefined' && DATA.agents) ? DATA.agents : {};

    // 1. Backend-driven: scan all agent panes for parent_pane_id === pane
    const backendChildren = Object.entries(agents)
      .filter(([pid, a]) => a && a.is_child_pane && a.parent_pane_id === pane)
      .map(([pid]) => pid);

    // 2. localStorage manual groupings (pre-v3.7 compat)
    const manualChildren = Object.keys(map).filter(k => map[k] === pane);

    // Union, preserving order: backend first, then manual (if not already included)
    const seen = new Set(backendChildren);
    manualChildren.forEach(p => { if (!seen.has(p)) seen.add(p); });
    return [...seen];
  }

  /** Returns true if this pane is a child of any parent (either source). */
  function isSub(pane) { return !!parentOf(pane); }

  function clearAll() { map = {}; save(); }
  function snapshot() { return { ...map }; }

  load();

  return { setSub, unsetSub, parentOf, childrenOf, isSub, clearAll, snapshot };
})();
