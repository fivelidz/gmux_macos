// ═══════════════════════════════════════════════════════════
// AGENT AVATAR — mini crab from aquarium system
// ═══════════════════════════════════════════════════════════
const AVA_COLORS = {
  working:   '#4ade80',
  waiting:   '#f87171',
  permission:'#fb923c',
  done:      '#a78bfa',
  error:     '#ef4444',
  idle:      '#94a3b8',
  not_started:'#64748b',
};
const AVA_LABELS = {
  working:   'WORKING',
  waiting:   'WAITING',
  permission:'NEEDS YOU',
  done:      'DONE',
  error:     'ERROR',
  idle:      'IDLE',
  not_started:'STARTING',
};

function _blend(hex, target, t) {
  const a = [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
  const b = target === '#ffffff' ? [255,255,255] : [0,0,0];
  return '#' + a.map((v,i) => Math.round(v + (b[i]-v)*t).toString(16).padStart(2,'0')).join('');
}

function makeCrabSVG(color, size=52) {
  const hi = _blend(color,'#ffffff',.38), dk = _blend(color,'#000000',.38);
  const id = color.replace('#','');
  return `<svg width="${size}" height="${size}" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <line x1="14" y1="37" x2="4"  y2="51" stroke="${dk}" stroke-width="3.2" stroke-linecap="round"/>
  <line x1="21" y1="41" x2="8"  y2="53" stroke="${dk}" stroke-width="3"   stroke-linecap="round"/>
  <line x1="44" y1="37" x2="60" y2="51" stroke="${dk}" stroke-width="3.2" stroke-linecap="round"/>
  <line x1="49" y1="41" x2="56" y2="53" stroke="${dk}" stroke-width="3"   stroke-linecap="round"/>
  <line x1="16" y1="33" x2="5"  y2="43" stroke="${color}" stroke-width="3.2" stroke-linecap="round"/>
  <line x1="48" y1="33" x2="59" y2="43" stroke="${color}" stroke-width="3.2" stroke-linecap="round"/>
  <ellipse cx="8"  cy="24" rx="7" ry="5" fill="${dk}"/>
  <ellipse cx="56" cy="24" rx="7" ry="5" fill="${dk}"/>
  <line x1="14" y1="28" x2="8"  y2="25" stroke="${color}" stroke-width="3.8" stroke-linecap="round"/>
  <line x1="50" y1="28" x2="56" y2="25" stroke="${color}" stroke-width="3.8" stroke-linecap="round"/>
  <ellipse cx="32" cy="34" rx="20" ry="15" fill="${color}"/>
  <ellipse cx="26" cy="27" rx="9"  ry="5"  fill="${hi}" opacity=".3"/>
  <path d="M18 30 Q32 22 46 30" fill="none" stroke="${hi}" stroke-width="1" opacity=".35"/>
  <line x1="26" y1="22" x2="23" y2="15" stroke="${dk}" stroke-width="2.2" stroke-linecap="round"/>
  <line x1="38" y1="22" x2="41" y2="15" stroke="${dk}" stroke-width="2.2" stroke-linecap="round"/>
  <circle cx="22" cy="14" r="4"   fill="#080808"/>
  <circle cx="42" cy="14" r="4"   fill="#080808"/>
  <circle cx="21" cy="13" r="1.5" fill="#fff" opacity=".85"/>
  <circle cx="41" cy="13" r="1.5" fill="#fff" opacity=".85"/>
  <line x1="18" y1="43" x2="10" y2="56" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
  <line x1="46" y1="43" x2="54" y2="56" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
  <defs>
    <radialGradient id="sg${id}" cx="40%" cy="35%" r="60%">
      <stop offset="0%"   stop-color="#fff" stop-opacity=".28"/>
      <stop offset="100%" stop-color="#000" stop-opacity=".2"/>
    </radialGradient>
  </defs>
</svg>`;
}

// ASCII cat avatar — qalcode2-style face that changes with state.
function makeCatAscii(color, state, size=52) {
  const cats = {
    working:    ['  /\\_/\\  ', ' ( o.o ) ', '  > ^ <  '],
    waiting:    ['  /\\_/\\  ', ' ( -.- ) ', '  ( = )  '],
    permission: ['  /\\_/\\  ', ' ( @.@ ) ', '  > ! <  '],
    done:       ['  /\\_/\\  ', ' ( ^.^ ) ', '  ( ~ )  '],
    error:      ['  /\\_/\\  ', ' ( x.x ) ', '  > ~ <  '],
    idle:       ['  /\\_/\\  ', ' ( =.= ) ', '  ~~~~~  '],
  };
  const lines  = cats[state] || cats.idle;
  const fontPx = Math.max(8, Math.floor(size / 4));
  return `<pre style="margin:0;padding:0;color:${color};font-size:${fontPx}px;line-height:1.05;text-shadow:0 0 ${size/8}px ${color}88;font-family:monospace;text-align:center;">${lines.join('\n')}</pre>`;
}

function updateAvatar(pane) {
  if (!pane) return;
  const state = pane.state || 'idle';
  const color = AVA_COLORS[state] || '#94a3b8';
  const label = AVA_LABELS[state] || state.toUpperCase();
  const mode  = localStorage.getItem('gmux.avatarMode') || 'crab';

  function avatarHtml(size) {
    switch (mode) {
      case 'off':  return '';
      case 'cat':  return makeCatAscii(color, state, size);
      case 'dot':  return `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};box-shadow:0 0 ${size/3}px ${color}88;display:flex;align-items:center;justify-content:center;font-size:${size/3}px;color:white;font-weight:700">${pane.window_index||''}</div>`;
      case 'crab':
      default:     return makeCrabSVG(color, size);
    }
  }

  // Chat panel mini avatar
  const craEl   = document.getElementById('cp-avatar-crab');
  const badgeEl = document.getElementById('cp-avatar-badge');
  const wrapEl  = document.getElementById('cp-avatar');
  if (wrapEl) wrapEl.style.display = (mode === 'off') ? 'none' : '';
  if (craEl) {
    craEl.innerHTML  = avatarHtml(48);
    craEl.className  = state;
    craEl.style.color = color;
  }
  if (badgeEl) {
    badgeEl.textContent       = label;
    badgeEl.style.background  = color + '22';
    badgeEl.style.color       = color;
    badgeEl.style.border      = `1px solid ${color}44`;
  }

  // Fullscreen avatar (bottom-right corner during chat-fullscreen or pane fullscreen)
  const fsEl    = document.getElementById('fs-avatar');
  const fsCrab  = document.getElementById('fs-avatar-crab');
  const fsLabel = document.getElementById('fs-avatar-label');
  if (fsEl) {
    const isFs = document.getElementById('app')?.classList.contains('chat-fullscreen') ||
                 (fullscreenId !== null);
    fsEl.classList.toggle('visible', !!isFs && mode !== 'off');
    if (fsCrab)  { fsCrab.innerHTML = avatarHtml(80); fsCrab.style.color = color; }
    if (fsLabel) fsLabel.textContent = `${pane.window_name} · ${label}`;
  }
}

window.setAvatarMode = function(mode) {
  localStorage.setItem('gmux.avatarMode', mode);
  toast(`Avatar: ${mode}`);
  if (chatOpen && panes[selectedId]) updateAvatar(panes[selectedId]);
};
