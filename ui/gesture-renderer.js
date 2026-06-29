/**
 * GestureRenderer — Visual overlay for hand tracking
 *
 * VISUAL MODES (set config.landmarkStyle / config.skeletonStyle):
 *
 *   landmarkStyle: 'circle' | 'square' | 'diamond' | 'crosshair' | 'none'
 *   skeletonStyle: 'line' | 'gradient' | 'dashed' | 'none'
 *
 * OVERLAY LAYERS (each independently toggled):
 *   showSkeleton        — bone connections
 *   showLandmarks       — joint markers
 *   showLabels          — gesture name pill
 *   showTrails          — wrist motion trail
 *   showPinchCircle     — thumb-index distance indicator
 *   showCursor          — index-tip cursor ring
 *   showDistanceLines   — lines between all fingertips with distance readout
 *   showOrientation     — palm normal arrow + roll/pitch/yaw readout
 *   showFingerAngles    — per-finger angle arc + °readout at each joint
 *   showMesh            — filled hand mesh (palm polygon + finger quads)
 *   showCoords          — XYZ coordinate readout at each landmark
 *
 * BACKGROUND MODE:
 *   config.background: 'video' | 'black' | 'dark' | 'grid'
 *   When not 'video', the renderer fills its own background
 *   so the video element can be hidden.
 *
 * MESH ONLY MODE:
 *   When background !== 'video' and showMesh is true, produces the
 *   classic "hand wireframe on dark background" look.
 */

class GestureRenderer {
  constructor(canvas, config = {}) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext('2d');

    this.config = {
      mirror: true,

      // ── Visual style ──
      landmarkStyle: config.landmarkStyle || 'circle',   // circle|square|diamond|crosshair|none
      skeletonStyle: config.skeletonStyle || 'line',     // line|gradient|dashed|none
      background:    config.background    || 'video',    // video|black|dark|grid

      // ── Layer toggles ──
      showSkeleton:      config.showSkeleton      ?? true,
      showLandmarks:     config.showLandmarks      ?? true,
      showLabels:        config.showLabels         ?? true,
      showTrails:        config.showTrails         ?? true,
      showPinchCircle:   config.showPinchCircle    ?? true,
      showCursor:        config.showCursor         ?? true,
      showDistanceLines: config.showDistanceLines  ?? false,
      showOrientation:   config.showOrientation    ?? false,
      showFingerAngles:  config.showFingerAngles   ?? false,
      showMesh:          config.showMesh           ?? false,
      showCoords:        config.showCoords         ?? false,
      showTwoHandShape:  config.showTwoHandShape   ?? true,
      pinchThreshold:    config.pinchThreshold     ?? 0.075,

      // ── Sizing ──
      trailLength:    config.trailLength    || 24,
      landmarkSize:   config.landmarkSize   || 6,     // base radius / half-width

      // ── Colors ──
      handColors: {
        Left:  { primary: '#00d4ff', secondary: '#0088aa', glow: 'rgba(0,212,255,0.4)',   mesh: 'rgba(0,212,255,0.08)' },
        Right: { primary: '#ff6b35', secondary: '#cc4a1a', glow: 'rgba(255,107,53,0.4)', mesh: 'rgba(255,107,53,0.08)' },
        ...(config.handColors || {}),
      },
      gestureLabelColors: {
        PINCH: '#ff6b35', OPEN_PALM: '#00ff88', FIST: '#ff4466',
        POINT: '#ffdd00', PEACE: '#aa88ff', THUMBS_UP: '#00ff88',
        THREE: '#aa88ff', FOUR: '#aa88ff', ROCK: '#ff4466', UNKNOWN: '#555',
        ...(config.gestureLabelColors || {}),
      },
    };

    this.trails          = { Left: [], Right: [] };
    this.pinchAnimations = [];
    this._pinchWasActive = false;
    this._controls       = null;

    // ── MediaPipe hand skeleton connections ──
    this.HAND_CONNECTIONS = [
      [0,1],[1,2],[2,3],[3,4],          // Thumb
      [0,5],[5,6],[6,7],[7,8],          // Index
      [0,9],[9,10],[10,11],[11,12],     // Middle
      [0,13],[13,14],[14,15],[15,16],   // Ring
      [0,17],[17,18],[18,19],[19,20],   // Pinky
      [5,9],[9,13],[13,17],             // Palm knuckles
    ];

    // Finger tip indices
    this.TIPS     = [4, 8, 12, 16, 20];
    this.KNUCKLES = [5, 9, 13, 17];   // MCP row

    // Palm face polygon (for mesh fill)
    this.PALM_POLY = [0, 1, 5, 9, 13, 17];

    // Finger quads: [mcp, pip, dip, tip] per finger
    this.FINGER_CHAINS = [
      [1,2,3,4],    // Thumb
      [5,6,7,8],    // Index
      [9,10,11,12], // Middle
      [13,14,15,16],// Ring
      [17,18,19,20],// Pinky
    ];

    // Tip-pairs for distance lines
    this.TIP_PAIRS = [
      [4,8],[4,12],[4,16],[4,20],
      [8,12],[8,16],[8,20],
      [12,16],[12,20],
      [16,20],
    ];
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MAIN DRAW
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * @param {object}          handsData       MediaPipe results
   * @param {GestureEngine}   gestureEngine
   * @param {GestureControls} [controls]
   */
  draw(handsData, gestureEngine, controls = null) {
    const ctx = this.ctx;
    const w   = this.canvas.width;
    const h   = this.canvas.height;

    this._controls = controls;

    // ── Background ──
    this._drawBackground(ctx, w, h);

    // ── Pinch ripple animations (before hands) ──
    this._drawPinchAnimations(ctx);

    if (!handsData?.multiHandLandmarks?.length) return;

    for (let i = 0; i < handsData.multiHandLandmarks.length; i++) {
      const rawLm   = handsData.multiHandLandmarks[i];
      const rawLabel = handsData.multiHandedness?.[i]?.label || 'Right';
      // Flip label — MediaPipe reports from camera POV, engine stores from user POV
      const label   = rawLabel === 'Left' ? 'Right' : 'Left';
      const colors  = this.config.handColors[label] || this.config.handColors.Right;
      const smoothed= gestureEngine?.hands[label]?.smoothedLandmarks || rawLm;
      const metrics = gestureEngine?.hands[label]?.metrics;
      const gesture = gestureEngine?.hands[label]?.currentGesture;
      const isGrab  = this._isGrabbing(label);
      const isHover = this._isHovering(label);

      // ── Screen-space points ──
      const pts = smoothed.map(lm => this._toScreen(lm.x, lm.y, w, h));
      // Raw normalised (for metric readouts)
      const nlm = smoothed;

      // ── Trail (under everything) ──
      if (this.config.showTrails) {
        this.trails[label].push({ x: pts[0].x, y: pts[0].y });
        if (this.trails[label].length > this.config.trailLength) this.trails[label].shift();
        this._drawTrail(ctx, this.trails[label], colors);
      }

      // ── Mesh (filled surface — goes under skeleton) ──
      if (this.config.showMesh) {
        this._drawMesh(ctx, pts, colors, metrics);
      }

      // ── Skeleton bones ──
      if (this.config.showSkeleton) {
        this._drawSkeleton(ctx, pts, colors);
      }

      // ── Distance lines between fingertips ──
      if (this.config.showDistanceLines) {
        this._drawDistanceLines(ctx, pts, nlm, colors, w, h);
      }

      // ── Orientation arrows ──
      if (this.config.showOrientation) {
        this._drawOrientation(ctx, pts, nlm, metrics, colors, w, h);
      }

      // ── Per-finger angle arcs ──
      if (this.config.showFingerAngles) {
        this._drawFingerAngles(ctx, pts, nlm, colors);
      }

      // ── Landmarks (joint markers) ──
      if (this.config.showLandmarks) {
        this._drawLandmarks(ctx, pts, colors, metrics, label, isGrab, isHover);
      }

      // ── Coordinate readouts ──
      if (this.config.showCoords) {
        this._drawCoords(ctx, pts, nlm, colors);
      }

      // ── Pinch indicator ──
      if (this.config.showPinchCircle && metrics) {
        // Pass struggle pressure (0=green, 1=red) from gestureInput if available
        const strugglePressure = this._controls?.getStrugglePressure?.(label) ?? 0;
        const middleRatio = (metrics.pinchMiddleThumb || 1) / (metrics.palmSize || 0.15);
        this._drawPinchIndicator(ctx, pts, metrics, colors, strugglePressure, middleRatio);
      }

      // ── Gesture label ──
      if (this.config.showLabels && gesture) {
        this._drawGestureLabel(ctx, pts, gesture, label, colors);
      }

      // ── Index tip cursor ──
      if (this.config.showCursor && metrics) {
        this._drawCursor(ctx, pts[8], colors, gesture);
      }
    }

    // Clear trails for absent hands
    for (const label of ['Left', 'Right']) {
      if (!handsData.multiHandedness?.some(h => h.label === label)) {
        this.trails[label] = [];
      }
    }

    // ── Two-hand shape lines (drawn after both hands so it sits on top) ──
    if (this.config.showTwoHandShape && gestureEngine) {
      this._drawTwoHandShape(ctx, w, h, gestureEngine);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // BACKGROUND
  // ═══════════════════════════════════════════════════════════════════════════

  _drawBackground(ctx, w, h) {
    const bg = this.config.background;
    if (bg === 'video') {
      ctx.clearRect(0, 0, w, h);
      return;
    }

    if (bg === 'black') {
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, w, h);
    } else if (bg === 'dark') {
      ctx.fillStyle = '#05060d';
      ctx.fillRect(0, 0, w, h);
    } else if (bg === 'grid') {
      ctx.fillStyle = '#05060d';
      ctx.fillRect(0, 0, w, h);
      // Grid lines
      ctx.save();
      ctx.strokeStyle = 'rgba(0,212,255,0.07)';
      ctx.lineWidth = 1;
      const step = Math.min(w, h) / 12;
      for (let x = 0; x <= w; x += step) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y <= h; y += step) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }
      // Perspective-ish centre point
      ctx.strokeStyle = 'rgba(0,212,255,0.04)';
      ctx.lineWidth = 0.5;
      for (let x = 0; x <= w; x += step * 2) {
        ctx.beginPath(); ctx.moveTo(w/2, h/2); ctx.lineTo(x, 0); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(w/2, h/2); ctx.lineTo(x, h); ctx.stroke();
      }
      ctx.restore();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // MESH
  // ═══════════════════════════════════════════════════════════════════════════

  _drawMesh(ctx, pts, colors, metrics) {
    ctx.save();

    // ── Palm polygon fill ──
    ctx.beginPath();
    const palmPts = [pts[0], pts[1], pts[5], pts[9], pts[13], pts[17]];
    ctx.moveTo(palmPts[0].x, palmPts[0].y);
    for (let i = 1; i < palmPts.length; i++) ctx.lineTo(palmPts[i].x, palmPts[i].y);
    ctx.closePath();
    ctx.fillStyle = colors.mesh;
    ctx.shadowColor = colors.primary;
    ctx.shadowBlur  = 20;
    ctx.fill();
    ctx.strokeStyle = colors.primary + '55';
    ctx.lineWidth   = 1;
    ctx.stroke();

    // ── Finger quad fills ──
    for (const [a, b, c, d] of this.FINGER_CHAINS) {
      const pa = pts[a], pb = pts[b], pc = pts[c], pd = pts[d];
      ctx.beginPath();
      ctx.moveTo(pa.x - 5, pa.y);
      ctx.lineTo(pb.x - 4, pb.y);
      ctx.lineTo(pc.x - 3, pc.y);
      ctx.lineTo(pd.x - 2, pd.y);
      ctx.lineTo(pd.x + 2, pd.y);
      ctx.lineTo(pc.x + 3, pc.y);
      ctx.lineTo(pb.x + 4, pb.y);
      ctx.lineTo(pa.x + 5, pa.y);
      ctx.closePath();
      ctx.fillStyle = colors.mesh;
      ctx.fill();
      ctx.strokeStyle = colors.primary + '44';
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SKELETON
  // ═══════════════════════════════════════════════════════════════════════════

  _drawSkeleton(ctx, pts, colors) {
    const style = this.config.skeletonStyle;
    if (style === 'none') return;

    ctx.save();
    ctx.lineCap = 'round';

    for (const [a, b] of this.HAND_CONNECTIONS) {
      const pa = pts[a], pb = pts[b];

      if (style === 'gradient') {
        const grad = ctx.createLinearGradient(pa.x, pa.y, pb.x, pb.y);
        grad.addColorStop(0, colors.secondary + 'cc');
        grad.addColorStop(1, colors.primary   + 'ff');
        ctx.strokeStyle = grad;
        ctx.shadowColor = colors.glow;
        ctx.shadowBlur  = 10;
        ctx.lineWidth   = 2.5;
        ctx.setLineDash([]);
      } else if (style === 'dashed') {
        ctx.strokeStyle = colors.primary;
        ctx.shadowColor = colors.glow;
        ctx.shadowBlur  = 6;
        ctx.lineWidth   = 1.5;
        ctx.setLineDash([5, 4]);
      } else {
        // 'line' default
        ctx.strokeStyle = colors.primary;
        ctx.shadowColor = colors.glow;
        ctx.shadowBlur  = 8;
        ctx.lineWidth   = 2.5;
        ctx.setLineDash([]);
      }

      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }

    ctx.setLineDash([]);
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LANDMARKS
  // ═══════════════════════════════════════════════════════════════════════════

  _drawLandmarks(ctx, pts, colors, metrics, label, isGrab, isHover) {
    const style = this.config.landmarkStyle;
    if (style === 'none') return;

    ctx.save();

    pts.forEach((pt, i) => {
      const isTip   = this.TIPS.includes(i);
      const isWrist = i === 0;

      let size  = isTip ? this.config.landmarkSize + 1 : isWrist ? this.config.landmarkSize + 2 : this.config.landmarkSize - 2;
      let fill  = isTip ? '#ffffff' : isWrist ? colors.primary : colors.secondary;
      let stroke= colors.primary;
      let glow  = colors.glow;

      // ── INDEX + THUMB pinch highlight only ──────────────────────────────────
      // Palm-normalised ratio (mirrors input.js logic)
      if (metrics && (i === 8 || i === 4)) {
        const pSize = metrics.palmSize || 0.15;
        const pRatio = metrics.pinchIndexThumb / pSize;
        if (pRatio < 0.22) {
          // Fully pinched → bright orange
          fill = '#ff6b35'; size += 4; glow = 'rgba(255,107,53,0.95)';
        } else if (pRatio < 0.38) {
          // Near-pinch zone → yellow warning
          const t = 1 - (pRatio - 0.22) / (0.38 - 0.22);
          fill = `rgb(255,${Math.floor(107 + t * 130)},53)`;
          size += Math.floor(t * 3);
          glow = `rgba(255,180,53,${0.5 + t * 0.4})`;
        }
      }
      // Grab state
      if (isGrab && (i === 8 || i === 4 || i === 0)) {
        fill = colors.primary;
        size += 3;
      }
      // Hover — enlarge index tip
      if (isHover && i === 8) {
        size = 11;
        fill = '#ffffff';
      }

      ctx.shadowColor = glow;
      ctx.shadowBlur  = isTip ? 14 : 7;

      if (style === 'circle') {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, size, 0, Math.PI * 2);
        ctx.fillStyle   = fill;
        ctx.strokeStyle = stroke;
        ctx.lineWidth   = isTip ? 2 : 1.5;
        ctx.fill();
        ctx.stroke();

      } else if (style === 'square') {
        const s = size * 1.6;
        ctx.fillStyle   = fill;
        ctx.strokeStyle = stroke;
        ctx.lineWidth   = isTip ? 2 : 1.5;
        ctx.fillRect(pt.x - s/2, pt.y - s/2, s, s);
        ctx.strokeRect(pt.x - s/2, pt.y - s/2, s, s);

      } else if (style === 'diamond') {
        const s = size * 1.6;
        ctx.beginPath();
        ctx.moveTo(pt.x,     pt.y - s);
        ctx.lineTo(pt.x + s, pt.y);
        ctx.lineTo(pt.x,     pt.y + s);
        ctx.lineTo(pt.x - s, pt.y);
        ctx.closePath();
        ctx.fillStyle   = fill;
        ctx.strokeStyle = stroke;
        ctx.lineWidth   = 1.5;
        ctx.fill();
        ctx.stroke();

      } else if (style === 'crosshair') {
        const arm = size * 2;
        ctx.strokeStyle = fill;
        ctx.lineWidth   = isTip ? 2.5 : 1.5;
        // Horizontal
        ctx.beginPath();
        ctx.moveTo(pt.x - arm, pt.y);
        ctx.lineTo(pt.x + arm, pt.y);
        ctx.stroke();
        // Vertical
        ctx.beginPath();
        ctx.moveTo(pt.x, pt.y - arm);
        ctx.lineTo(pt.x, pt.y + arm);
        ctx.stroke();
        // Centre dot
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, size * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = fill;
        ctx.fill();
      }
    });

    // Grab pulsing ring
    if (isGrab && pts[0]) {
      const wrist = pts[0];
      const t = Date.now() / 400;
      const pulse = 1 + Math.sin(t * Math.PI * 2) * 0.18;
      ctx.beginPath();
      ctx.arc(wrist.x, wrist.y, 24 * pulse, 0, Math.PI * 2);
      ctx.strokeStyle = colors.primary;
      ctx.lineWidth   = 2;
      ctx.globalAlpha = 0.35;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DISTANCE LINES (fingertip-to-fingertip with readout)
  // ═══════════════════════════════════════════════════════════════════════════

  _drawDistanceLines(ctx, pts, nlm, colors, w, h) {
    ctx.save();

    for (const [a, b] of this.TIP_PAIRS) {
      const pa  = pts[a], pb = pts[b];
      const na  = nlm[a], nb = nlm[b];
      // Euclidean distance in normalised space
      const dist= Math.hypot(na.x - nb.x, na.y - nb.y);
      // Closer = more opaque / brighter
      const alpha = Math.max(0.08, 0.75 - dist * 2.5);

      ctx.globalAlpha = alpha;
      ctx.strokeStyle = colors.primary;
      ctx.lineWidth   = 1;
      ctx.setLineDash([3, 5]);
      ctx.shadowColor = colors.glow;
      ctx.shadowBlur  = 6;

      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Midpoint distance label (only draw if not too small on screen)
      const screenDist = Math.hypot(pa.x - pb.x, pa.y - pb.y);
      if (screenDist > 28) {
        const mx = (pa.x + pb.x) / 2;
        const my = (pa.y + pb.y) / 2;

        // Tiny pill background
        const label = (dist * 100).toFixed(1);
        ctx.font = '9px monospace';
        const tw = ctx.measureText(label).width;
        ctx.globalAlpha = alpha * 0.85;
        ctx.fillStyle   = 'rgba(0,0,0,0.65)';
        ctx.beginPath();
        this._rrect(ctx, mx - tw/2 - 3, my - 7, tw + 6, 13, 3);
        ctx.fill();
        ctx.fillStyle   = colors.primary;
        ctx.globalAlpha = alpha;
        ctx.textAlign   = 'center';
        ctx.textBaseline= 'middle';
        ctx.fillText(label, mx, my);
      }
    }

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ORIENTATION (palm normal + roll readout)
  // ═══════════════════════════════════════════════════════════════════════════

  _drawOrientation(ctx, pts, nlm, metrics, colors, w, h) {
    if (!metrics) return;
    ctx.save();

    const palm  = pts[9]; // middle MCP as palm anchor
    const wrist = pts[0];
    const midMCP= pts[9];
    const idxMCP= pts[5];
    const pnkMCP= pts[17];

    // ── Palm normal arrow (using wrist → middle MCP vector) ──
    const dx = midMCP.x - wrist.x;
    const dy = midMCP.y - wrist.y;
    const len = Math.hypot(dx, dy);
    const nx  = dx / len;
    const ny  = dy / len;
    const arrowLen = 50;

    // Palm up direction arrow
    const ax = palm.x - nx * arrowLen;
    const ay = palm.y - ny * arrowLen;

    ctx.shadowColor = colors.primary;
    ctx.shadowBlur  = 14;
    ctx.strokeStyle = colors.primary;
    ctx.lineWidth   = 2.5;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(palm.x, palm.y);
    ctx.lineTo(ax, ay);
    ctx.stroke();
    // Arrow head
    this._arrowHead(ctx, palm.x, palm.y, ax, ay, 10, colors.primary);

    // ── Palm roll axis (wrist → pinky MCP → index MCP cross line) ──
    const rollDx = idxMCP.x - pnkMCP.x;
    const rollDy = idxMCP.y - pnkMCP.y;
    const rollLen = Math.hypot(rollDx, rollDy);
    const rnx = rollDx / rollLen;
    const rny = rollDy / rollLen;
    const halfRoll = 40;

    ctx.strokeStyle = '#aa88ff';
    ctx.shadowColor = '#aa88ff';
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(palm.x - rnx * halfRoll, palm.y - rny * halfRoll);
    ctx.lineTo(palm.x + rnx * halfRoll, palm.y + rny * halfRoll);
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Angle/roll label ──
    const rollAngle = metrics.palmRoll;
    const normAngle = Math.atan2(ny, nx) * (180 / Math.PI);

    const lx = ax - 8;
    const ly = ay - 18;
    ctx.font = 'bold 10px monospace';
    ctx.textAlign   = 'center';
    ctx.textBaseline= 'middle';
    ctx.globalAlpha = 0.9;

    // Background pill
    const labelText = `↑${normAngle.toFixed(0)}° ⟳${rollAngle.toFixed(0)}°`;
    const tw = ctx.measureText(labelText).width;
    ctx.fillStyle = 'rgba(0,0,0,0.75)';
    ctx.beginPath();
    this._rrect(ctx, lx - tw/2 - 6, ly - 8, tw + 12, 16, 4);
    ctx.fill();
    ctx.fillStyle   = colors.primary;
    ctx.fillText(labelText, lx, ly);

    // ── Orientation arc (showing roll visually around palm centre) ──
    const arcR = 32;
    const rollRad = (rollAngle * Math.PI) / 180;
    ctx.strokeStyle = '#aa88ff';
    ctx.shadowColor = 'rgba(170,136,255,0.5)';
    ctx.shadowBlur  = 8;
    ctx.lineWidth   = 2;
    ctx.globalAlpha = 0.6;
    ctx.beginPath();
    ctx.arc(palm.x, palm.y, arcR, -Math.PI/2, -Math.PI/2 + rollRad);
    ctx.stroke();
    // Tick at current roll
    const tickAng = -Math.PI/2 + rollRad;
    ctx.beginPath();
    ctx.moveTo(palm.x + Math.cos(tickAng) * (arcR - 6), palm.y + Math.sin(tickAng) * (arcR - 6));
    ctx.lineTo(palm.x + Math.cos(tickAng) * (arcR + 6), palm.y + Math.sin(tickAng) * (arcR + 6));
    ctx.strokeStyle = '#ffdd00';
    ctx.lineWidth   = 2.5;
    ctx.stroke();

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // FINGER ANGLES (arc at each joint, °readout)
  // ═══════════════════════════════════════════════════════════════════════════

  _drawFingerAngles(ctx, pts, nlm, colors) {
    ctx.save();

    // For each finger, draw the bend angle at PIP joint
    const fingerPIPs = [
      { mcp: 1,  pip: 2,  dip: 3 },   // thumb
      { mcp: 5,  pip: 6,  dip: 7 },   // index
      { mcp: 9,  pip: 10, dip: 11 },  // middle
      { mcp: 13, pip: 14, dip: 15 },  // ring
      { mcp: 17, pip: 18, dip: 19 },  // pinky
    ];

    for (const { mcp, pip, dip } of fingerPIPs) {
      const pMCP = pts[mcp], pPIP = pts[pip], pDIP = pts[dip];
      const nMCP = nlm[mcp], nPIP = nlm[pip], nDIP = nlm[dip];

      // Vectors at PIP joint
      const v1x = nMCP.x - nPIP.x, v1y = nMCP.y - nPIP.y;
      const v2x = nDIP.x - nPIP.x, v2y = nDIP.y - nPIP.y;
      const len1 = Math.hypot(v1x, v1y), len2 = Math.hypot(v2x, v2y);
      if (len1 < 0.001 || len2 < 0.001) continue;

      const dot   = (v1x * v2x + v1y * v2y) / (len1 * len2);
      const angle = Math.acos(Math.max(-1, Math.min(1, dot)));
      const deg   = angle * (180 / Math.PI);

      // Only draw if meaningfully bent (>15°)
      if (deg < 15) continue;

      // Arc angles
      const ang1 = Math.atan2(v1y, v1x);
      const ang2 = Math.atan2(v2y, v2x);

      const arcR = 12;
      ctx.strokeStyle = '#ffdd00';
      ctx.shadowColor = 'rgba(255,221,0,0.5)';
      ctx.shadowBlur  = 6;
      ctx.lineWidth   = 1.5;
      ctx.globalAlpha = 0.75;
      ctx.beginPath();
      ctx.arc(pPIP.x, pPIP.y, arcR, ang1, ang2, false);
      ctx.stroke();

      // Degree label
      if (arcR > 5) {
        const midAng = (ang1 + ang2) / 2;
        const lx = pPIP.x + Math.cos(midAng) * (arcR + 12);
        const ly = pPIP.y + Math.sin(midAng) * (arcR + 12);
        ctx.font         = '8px monospace';
        ctx.fillStyle    = '#ffdd00';
        ctx.globalAlpha  = 0.85;
        ctx.textAlign    = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(deg.toFixed(0) + '°', lx, ly);
      }
    }

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // COORDINATE READOUTS
  // ═══════════════════════════════════════════════════════════════════════════

  _drawCoords(ctx, pts, nlm, colors) {
    // Only show for tips + wrist to keep it readable
    const SHOW = [0, 4, 8, 12, 16, 20];
    ctx.save();
    ctx.font         = '8px monospace';
    ctx.textAlign    = 'left';
    ctx.textBaseline = 'top';

    for (const i of SHOW) {
      const pt = pts[i], lm = nlm[i];
      const label = `${lm.x.toFixed(2)},${lm.y.toFixed(2)},${lm.z.toFixed(2)}`;
      const tw = ctx.measureText(label).width;

      // Offset to avoid overlapping the marker
      const ox = pt.x + 10;
      const oy = pt.y - 6;

      ctx.globalAlpha = 0.8;
      ctx.fillStyle   = 'rgba(0,0,0,0.65)';
      this._rrect(ctx, ox - 2, oy - 1, tw + 4, 11, 2);
      ctx.fill();

      ctx.fillStyle   = colors.primary;
      ctx.globalAlpha = 0.9;
      ctx.fillText(label, ox, oy);
    }

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // PINCH INDICATOR
  // ═══════════════════════════════════════════════════════════════════════════

  _drawPinchIndicator(ctx, pts, metrics, colors, strugglePressure = 0, middleRatio = 1) {
    // Palm-normalised ratio for index and middle
    const palmSize    = metrics.palmSize || 0.15;
    const indexRatio  = (metrics.pinchIndexThumb  || 1) / palmSize;
    const PINCH_VIS   = 0.22;
    const OPEN_VIS    = 0.55;

    const thumbTip  = pts[4];
    const indexTip  = pts[8];
    const middleTip = pts[12];

    // Index pinch strength
    const idxStrength = Math.max(0, Math.min(1, 1 - (indexRatio  - PINCH_VIS) / (OPEN_VIS - PINCH_VIS)));
    const midStrength = Math.max(0, Math.min(1, 1 - (middleRatio - PINCH_VIS) / (OPEN_VIS - PINCH_VIS)));

    // Active finger = whichever is more closed
    const useMiddle  = midStrength > idxStrength && midStrength > 0.1;
    const activeTip  = useMiddle ? middleTip : indexTip;
    const strength   = useMiddle ? midStrength : idxStrength;
    const isPinched  = strength > 0.7;

    // ── COLOR: green (just grabbed) → orange (normal) → red (struggling) ──
    // strugglePressure 0..1 drives green→red
    let pinchColor;
    if (isPinched) {
      if (strugglePressure <= 0) {
        // Just grabbed: bright green
        pinchColor = '#00ff88';
      } else if (strugglePressure < 0.5) {
        // Struggling a bit: orange
        const t = strugglePressure * 2;
        const r = Math.floor(0 + t * 255);
        const g = Math.floor(255 - t * (255 - 107));
        pinchColor = `rgb(${r},${g},53)`;
      } else {
        // Struggling hard: deep red
        const t = (strugglePressure - 0.5) * 2;
        const r = 255;
        const g = Math.floor(107 - t * 107);
        pinchColor = `rgb(${r},${g},0)`;
      }
    } else {
      pinchColor = '#ffdd00';
    }

    ctx.save();

    // ── Middle finger dim indicator (always show, dimly) ──
    if (midStrength > 0.05 && !useMiddle) {
      ctx.globalAlpha = midStrength * 0.3;
      ctx.strokeStyle = '#cc88ff';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 5]);
      ctx.beginPath();
      ctx.moveTo(thumbTip.x, thumbTip.y);
      ctx.lineTo(middleTip.x, middleTip.y);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // ── Active pinch line (thumb → active finger) ──
    const lineAlpha = 0.25 + strength * 0.75;
    ctx.globalAlpha = lineAlpha;
    ctx.strokeStyle = pinchColor;
    ctx.shadowColor = pinchColor;
    ctx.shadowBlur  = isPinched ? 18 : 6;
    ctx.lineWidth   = 1.5 + strength * 2.5;
    ctx.setLineDash(isPinched ? [] : [4, 4]);
    ctx.beginPath();
    ctx.moveTo(thumbTip.x, thumbTip.y);
    ctx.lineTo(activeTip.x, activeTip.y);
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Central circle at pinch midpoint ──
    const midX    = (thumbTip.x + activeTip.x) / 2;
    const midY    = (thumbTip.y + activeTip.y) / 2;
    const circleR = 6 + strength * 22;
    ctx.globalAlpha = 0.12 + strength * 0.5;
    ctx.beginPath();
    ctx.arc(midX, midY, circleR, 0, Math.PI * 2);
    ctx.strokeStyle = pinchColor;
    ctx.shadowColor = pinchColor;
    ctx.shadowBlur  = 16;
    ctx.lineWidth   = 2.5;
    ctx.stroke();
    if (isPinched && strength > 0.6) {
      ctx.globalAlpha = strength * 0.18;
      ctx.fillStyle   = pinchColor;
      ctx.fill();
    }

    // ── Struggle pulse ring (red warning when holding too long) ──
    if (strugglePressure > 0.5 && isPinched) {
      const pulse = 0.4 + 0.6 * Math.sin(Date.now() * 0.015);
      ctx.globalAlpha = pulse * 0.6;
      ctx.beginPath();
      ctx.arc(midX, midY, circleR + 8 + pulse * 6, 0, Math.PI * 2);
      ctx.strokeStyle = '#ff0000';
      ctx.shadowColor = '#ff0000';
      ctx.shadowBlur  = 20;
      ctx.lineWidth   = 2;
      ctx.stroke();
    }

    // ── Thumb + active finger glow dots ──
    ctx.globalAlpha = 0.6 + strength * 0.4;
    ctx.fillStyle   = pinchColor;
    ctx.shadowColor = pinchColor;
    ctx.shadowBlur  = isPinched ? 18 : 8;
    ctx.beginPath();
    ctx.arc(thumbTip.x, thumbTip.y, 5 + strength * 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(activeTip.x, activeTip.y, 5 + strength * 5, 0, Math.PI * 2);
    ctx.fill();

    // ── Finger label when middle is active ──
    if (useMiddle && strength > 0.5) {
      ctx.globalAlpha = 0.7;
      ctx.fillStyle = '#cc88ff';
      ctx.font = 'bold 9px monospace';
      ctx.textAlign = 'center';
      ctx.shadowBlur = 6;
      ctx.fillText('MID', midX, midY - circleR - 6);
    }

    // Trigger animation on fresh pinch
    if (strength > 0.88 && !this._pinchWas0) {
      this.triggerPinchAnimation(midX, midY, pinchColor);
    }
    this._pinchWas0 = strength > 0.88;

    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TWO-HAND SHAPE LINES
  // Index tip ↔ Index tip  (blue)
  // R Index tip → R Thumb tip (orange, already per-hand)
  // L Thumb tip ↔ R Thumb tip (white)
  // Forms a dynamic shape / triangle / quad between the hands
  // ═══════════════════════════════════════════════════════════════════════════

  _drawTwoHandShape(ctx, w, h, gestureEngine) {
    const Lh = gestureEngine.hands.Left;
    const Rh = gestureEngine.hands.Right;
    if (!Lh?.smoothedLandmarks || !Rh?.smoothedLandmarks) return;

    const toLm = (lm) => this._toScreen(lm.x, lm.y, w, h);

    const Llm = Lh.smoothedLandmarks;
    const Rlm = Rh.smoothedLandmarks;

    const lIndex  = toLm(Llm[8]);   // L index tip
    const rIndex  = toLm(Rlm[8]);   // R index tip
    const lThumb  = toLm(Llm[4]);   // L thumb tip
    const rThumb  = toLm(Rlm[4]);   // R thumb tip
    const lMiddle = toLm(Llm[12]);  // L middle tip
    const rMiddle = toLm(Rlm[12]);  // R middle tip

    ctx.save();
    ctx.lineCap = 'round';

    // Helper: glowing line
    const gline = (ax, ay, bx, by, color, glow, width = 2) => {
      ctx.strokeStyle = color;
      ctx.shadowColor = glow;
      ctx.shadowBlur  = 14;
      ctx.lineWidth   = width;
      ctx.globalAlpha = 0.75;
      ctx.beginPath();
      ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
      ctx.stroke();
    };

    // ── Index tip ↔ Index tip (cyan/blue) ──
    gline(lIndex.x, lIndex.y, rIndex.x, rIndex.y, '#3d9bff', 'rgba(61,155,255,0.5)', 2);

    // ── Thumb ↔ Thumb (white) ──
    gline(lThumb.x, lThumb.y, rThumb.x, rThumb.y, 'rgba(255,255,255,0.9)', 'rgba(255,255,255,0.4)', 1.5);

    // ── L Index → L Thumb / R Index → R Thumb already drawn in pinch indicator ──
    // ── Extra: L Index → R Thumb diagonal (warm glow) ──
    gline(lIndex.x, lIndex.y, rThumb.x, rThumb.y, 'rgba(255,160,50,0.5)', 'rgba(255,160,50,0.3)', 1);

    // ── R Index → L Thumb diagonal (cool glow) ──
    gline(rIndex.x, rIndex.y, lThumb.x, lThumb.y, 'rgba(100,200,255,0.5)', 'rgba(100,200,255,0.3)', 1);

    // ── Fill the quad (L Index → R Index → R Thumb → L Thumb) ──
    ctx.globalAlpha = 0.04;
    ctx.fillStyle   = '#00d4ff';
    ctx.shadowBlur  = 0;
    ctx.beginPath();
    ctx.moveTo(lIndex.x, lIndex.y);
    ctx.lineTo(rIndex.x, rIndex.y);
    ctx.lineTo(rThumb.x, rThumb.y);
    ctx.lineTo(lThumb.x, lThumb.y);
    ctx.closePath();
    ctx.fill();

    // ── Mid-line labels: distance + angle ──
    const midX = (lIndex.x + rIndex.x) / 2;
    const midY = (lIndex.y + rIndex.y) / 2;
    const distN = Math.hypot(
      Llm[8].x - Rlm[8].x,
      Llm[8].y - Rlm[8].y
    );
    const ang = Math.atan2(rIndex.y - lIndex.y, rIndex.x - lIndex.x) * 180 / Math.PI;

    ctx.globalAlpha = 0.8;
    ctx.font        = 'bold 9px monospace';
    ctx.textAlign   = 'center';
    ctx.fillStyle   = '#3d9bff';
    ctx.shadowColor = 'rgba(61,155,255,0.6)';
    ctx.shadowBlur  = 6;
    ctx.fillText(
      `${Math.round(distN * 100)}%  ${Math.round(ang)}°`,
      midX, midY - 10
    );

    // Thumb-thumb mid label
    const tmx = (lThumb.x + rThumb.x) / 2;
    const tmy = (lThumb.y + rThumb.y) / 2;
    const tDist = Math.hypot(Llm[4].x - Rlm[4].x, Llm[4].y - Rlm[4].y);
    ctx.fillStyle   = 'rgba(255,255,255,0.7)';
    ctx.shadowColor = 'rgba(255,255,255,0.4)';
    ctx.fillText(`T↔T ${Math.round(tDist * 100)}%`, tmx, tmy - 10);

    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // PINCH RIPPLE ANIMATION
  // ═══════════════════════════════════════════════════════════════════════════

  triggerPinchAnimation(x, y, color = '#ff6b35') {
    this.pinchAnimations.push({ x, y, color, maxRadius: 60, alpha: 1, t: Date.now() });
  }

  _drawPinchAnimations(ctx) {
    this.pinchAnimations = this.pinchAnimations.filter(a => a.alpha > 0.01);
    for (const anim of this.pinchAnimations) {
      const elapsed = (Date.now() - anim.t) / 500;
      const r = 10 + elapsed * anim.maxRadius;
      anim.alpha = Math.max(0, 1 - elapsed);
      ctx.save();
      ctx.globalAlpha = anim.alpha * 0.6;
      ctx.strokeStyle = anim.color;
      ctx.lineWidth   = 2;
      ctx.shadowColor = anim.color;
      ctx.shadowBlur  = 15;
      ctx.beginPath();
      ctx.arc(anim.x, anim.y, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GESTURE LABEL
  // ═══════════════════════════════════════════════════════════════════════════

  _drawGestureLabel(ctx, pts, gesture, hand, colors) {
    const wrist    = pts[0];
    const labelCol = this.config.gestureLabelColors[gesture.name] || '#fff';
    const emoji    = this._gestureEmoji(gesture.name);
    const text     = `${emoji} ${gesture.name.replace(/_/g, ' ')}`;

    ctx.save();
    ctx.font = 'bold 13px "SF Mono", monospace';
    const tw = ctx.measureText(text).width;
    const pad = 10;
    const lx = wrist.x - tw / 2 - pad;
    const ly = wrist.y + 28;

    ctx.fillStyle = 'rgba(0,0,0,0.72)';
    ctx.beginPath();
    this._rrect(ctx, lx, ly, tw + pad * 2, 24, 6);
    ctx.fill();
    ctx.strokeStyle = labelCol;
    ctx.lineWidth   = 1.5;
    ctx.stroke();

    ctx.fillStyle   = labelCol;
    ctx.textAlign   = 'center';
    ctx.textBaseline= 'alphabetic';
    ctx.fillText(text, wrist.x, ly + 17);

    ctx.font      = 'bold 10px monospace';
    ctx.fillStyle = colors.primary;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(hand[0], wrist.x, wrist.y + 15);

    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CURSOR
  // ═══════════════════════════════════════════════════════════════════════════

  _drawCursor(ctx, pt, colors, gesture) {
    if (!pt) return;
    const isPinch = gesture?.name === 'PINCH';
    const r       = isPinch ? 4 : 9;

    ctx.save();
    ctx.shadowColor = isPinch ? '#ff6b35' : colors.primary;
    ctx.shadowBlur  = 16;
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2);
    ctx.strokeStyle = isPinch ? '#ff6b35' : colors.primary;
    ctx.lineWidth   = 2;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, isPinch ? 2 : 3, 0, Math.PI * 2);
    ctx.fillStyle = isPinch ? '#ff6b35' : '#fff';
    ctx.fill();
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TRAIL
  // ═══════════════════════════════════════════════════════════════════════════

  _drawTrail(ctx, trail, colors) {
    if (trail.length < 2) return;
    ctx.save();
    for (let i = 1; i < trail.length; i++) {
      const a = i / trail.length;
      ctx.beginPath();
      ctx.moveTo(trail[i-1].x, trail[i-1].y);
      ctx.lineTo(trail[i].x,   trail[i].y);
      ctx.strokeStyle = colors.primary;
      ctx.globalAlpha = a * 0.5;
      ctx.lineWidth   = a * 3;
      ctx.lineCap     = 'round';
      ctx.stroke();
    }
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════════════════

  _toScreen(normX, normY, w, h) {
    // Apply object-fit:cover crop compensation if cover params are set.
    // cover = { scale, offsetX, offsetY, videoW, videoH }
    const cov = this.config.cover;
    if (cov && cov.scale) {
      let x = normX * cov.scale * cov.videoW + cov.offsetX;
      let y = normY * cov.scale * cov.videoH + cov.offsetY;
      if (this.config.mirror) x = w - x;
      return { x, y };
    }
    // Fallback: raw mapping (no cover data yet)
    return {
      x: this.config.mirror ? (1 - normX) * w : normX * w,
      y: normY * h,
    };
  }

  _rrect(ctx, x, y, w, h, r) {
    r = Math.min(r, w/2, h/2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y,     x + w, y + r,     r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x,     y + h, x,     y + h - r, r);
    ctx.lineTo(x,     y + r);
    ctx.arcTo(x,     y,     x + r, y,         r);
    ctx.closePath();
  }

  // Alias used by external callers (GestureControls)
  _roundRect(ctx, x, y, w, h, r) { this._rrect(ctx, x, y, w, h, r); }

  _arrowHead(ctx, fromX, fromY, toX, toY, size, color) {
    const angle = Math.atan2(toY - fromY, toX - fromX);
    ctx.save();
    ctx.fillStyle   = color;
    ctx.shadowColor = color;
    ctx.shadowBlur  = 8;
    ctx.translate(toX, toY);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-size, -size * 0.5);
    ctx.lineTo(-size,  size * 0.5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  _isGrabbing(label) {
    return this._controls
      ? [...(this._controls?.elements?.values?.() || [])].some(el => el.active && el.grabbedBy === label)
      : false;
  }

  _isHovering(label) {
    return this._controls
      ? [...(this._controls?.elements?.values?.() || [])].some(el => el.hovered && el.hoveredBy === label)
      : false;
  }

  _gestureEmoji(name) {
    const m = { PINCH:'🤏', OPEN_PALM:'🖐️', FIST:'✊', POINT:'☝️',
                PEACE:'✌️', THUMBS_UP:'👍', THREE:'🤟', FOUR:'🖖',
                ROCK:'🤘', UNKNOWN:'❓' };
    return m[name] || '✋';
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  toggle(key) {
    this.config[key] = !this.config[key];
    return this.config[key];
  }

  setBackground(mode) { this.config.background = mode; }
  setLandmarkStyle(s) { this.config.landmarkStyle = s; }
  setSkeletonStyle(s) { this.config.skeletonStyle = s; }

  setSize(w, h) {
    this.canvas.width  = w;
    this.canvas.height = h;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = GestureRenderer;
} else if (typeof window !== 'undefined') {
  window.GestureRenderer = GestureRenderer;
}

export { GestureRenderer };
