/* util.js — shared helpers (formatting, escape, color picks) */

window.UTIL = (function () {

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toTimeString().slice(0, 8);
  }

  function fmtRelTime(iso) {
    if (!iso) return '';
    const ms = Date.now() - new Date(iso).getTime();
    if (isNaN(ms)) return '';
    if (ms < 5000)    return 'just now';
    if (ms < 60000)   return Math.floor(ms / 1000) + 's ago';
    if (ms < 3600000) return Math.floor(ms / 60000) + 'm ago';
    if (ms < 86400000) return Math.floor(ms / 3600000) + 'h ago';
    return Math.floor(ms / 86400000) + 'd ago';
  }

  function fmtDur(ms) {
    if (ms == null) return '';
    if (ms < 1000) return ms + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
    return Math.floor(ms / 60000) + 'm' + Math.floor((ms % 60000) / 1000) + 's';
  }

  // Deterministic colour from a string (for agent dots in the tree)
  const PALETTE = [
    '#818cf8', '#a78bfa', '#67e8f9', '#34d399',
    '#fb923c', '#f472b6', '#fbbf24', '#60a5fa',
    '#c084fc', '#22d3ee', '#fde047', '#f87171',
  ];
  function colorFor(str) {
    let h = 0;
    const s = String(str || '');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return PALETTE[Math.abs(h) % PALETTE.length];
  }

  function shortPath(p, maxLen = 60) {
    if (!p) return '';
    if (p.length <= maxLen) return p;
    return '…' + p.slice(p.length - maxLen + 1);
  }

  return { esc, fmtTime, fmtRelTime, fmtDur, colorFor, shortPath };
})();
