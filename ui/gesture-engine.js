/**
 * GestureEngine - Core hand gesture detection and classification
 * 
 * Uses MediaPipe Hands landmarks to classify gestures and provide
 * normalized coordinates for UI interaction.
 * 
 * MediaPipe Hand Landmark Map:
 *   0  = WRIST
 *   1-4  = THUMB  (1=CMC, 2=MCP, 3=IP, 4=TIP)
 *   5-8  = INDEX  (5=MCP, 6=PIP, 7=DIP, 8=TIP)
 *   9-12 = MIDDLE (9=MCP, 10=PIP, 11=DIP, 12=TIP)
 *  13-16 = RING   (13=MCP, 14=PIP, 15=DIP, 16=TIP)
 *  17-20 = PINKY  (17=MCP, 18=PIP, 19=DIP, 20=TIP)
 */

class GestureEngine {
  constructor(config = {}) {
    this.config = {
      pinchThreshold: config.pinchThreshold || 0.06,       // Normalized distance
      grabThreshold: config.grabThreshold || 0.08,
      swipeVelocityThreshold: config.swipeVelocityThreshold || 0.02,
      swipeHistoryLength: config.swipeHistoryLength || 8,
      pointExtendThreshold: config.pointExtendThreshold || 0.12,
      gestureConfirmFrames: config.gestureConfirmFrames || 3, // Frames to confirm gesture
      smoothingFactor: config.smoothingFactor || 0.7,        // 0=raw, 1=max smoothing
      ...config
    };

    // Per-hand state
    this.hands = { Left: this._newHandState(), Right: this._newHandState() };

    // Two-hand combined state
    this.twoHand = null;

    // Global gesture events (callbacks)
    this.listeners = {};

    // Frame counter
    this.frameCount = 0;
  }

  _newHandState() {
    return {
      landmarks: null,
      smoothedLandmarks: null,
      positionHistory: [],      // [{x, y, t}] wrist position history
      currentGesture: null,
      previousGesture: null,
      gestureConfirmCount: 0,
      pinchState: { active: false, startX: 0, startY: 0, x: 0, y: 0 },
      metrics: {}
    };
  }

  // ─── Main Update ────────────────────────────────────────────────────────────

  update(handsData) {
    this.frameCount++;
    const detectedHandedness = new Set();

    if (handsData && handsData.multiHandLandmarks) {
      for (let i = 0; i < handsData.multiHandLandmarks.length; i++) {
        const landmarks = handsData.multiHandLandmarks[i];
        const rawLabel = handsData.multiHandedness?.[i]?.label || 'Right';
        // MediaPipe reports handedness from the CAMERA's perspective, not the user's.
        // With facingMode:'user' (front camera), your right hand appears on the left
        // of the frame, so MediaPipe labels it "Left". We flip to match the user.
        const label = rawLabel === 'Left' ? 'Right' : 'Left';

        detectedHandedness.add(label);

        const state = this.hands[label] || this._newHandState();
        this.hands[label] = state;

        // Smooth landmarks
        state.smoothedLandmarks = this._smoothLandmarks(
          landmarks,
          state.smoothedLandmarks
        );
        state.landmarks = landmarks;

        // Calculate metrics
        state.metrics = this._calculateMetrics(state.smoothedLandmarks);

        // Track wrist position history
        const wrist = state.smoothedLandmarks[0];
        state.positionHistory.push({ x: wrist.x, y: wrist.y, t: Date.now() });
        if (state.positionHistory.length > this.config.swipeHistoryLength * 2) {
          state.positionHistory.shift();
        }

        // Classify gesture
        const rawGesture = this._classifyGesture(state);
        this._updateGestureState(state, rawGesture, label);
      }
    }

    // Clear hands that disappeared
    for (const label of ['Left', 'Right']) {
      if (!detectedHandedness.has(label) && this.hands[label]?.currentGesture) {
        this._emitEvent('gestureEnd', { hand: label, gesture: this.hands[label].currentGesture });
        this.hands[label] = this._newHandState();
      }
    }

    // ── Two-hand combined metrics ──
    this._updateTwoHandMetrics();
  }

  _updateTwoHandMetrics() {
    const L = this.hands.Left;
    const R = this.hands.Right;
    if (!L?.smoothedLandmarks || !R?.smoothedLandmarks) {
      this.twoHand = null;
      return;
    }

    const lm_L = L.smoothedLandmarks;
    const lm_R = R.smoothedLandmarks;
    const lWrist = lm_L[0];
    const rWrist = lm_R[0];
    const lPalm  = L.metrics.palmCenter;
    const rPalm  = R.metrics.palmCenter;

    const dist2d  = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
    const angle2d = (a, b) => Math.atan2(b.y - a.y, b.x - a.x) * (180 / Math.PI);
    const mid2d   = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    const clamp01 = v => Math.max(0, Math.min(1, v));

    // ── Index tips (existing) ──
    const lIndex = lm_L[8];
    const rIndex = lm_R[8];
    const indexDist  = dist2d(lIndex, rIndex);
    const palmDist   = dist2d(lPalm,  rPalm);
    const wristDist  = dist2d(lWrist, rWrist);
    const midpoint   = mid2d(lIndex, rIndex);
    const angle      = angle2d(lIndex, rIndex);

    const prev = this.twoHand;
    const indexDistDelta = prev ? indexDist - prev.indexDist : 0;

    // ── Cross-hand pinch points: L pinch position vs R pinch position ──
    // For each finger, compute the midpoint where that finger meets thumb on each hand.
    // Then measure distance + angle between the two hands' same-finger pinch points.
    //
    // "Cross pinch" = distance between R.pinchPointX and L.pinchPointX
    // This lets you control things by bringing your two pinch points together/apart.

    const FINGER_TIP = { index: 8, middle: 12, ring: 16, pinky: 20 };
    const THUMB_TIP  = 4;

    const crossPinch = {};
    for (const [finger, tipIdx] of Object.entries(FINGER_TIP)) {
      // Pinch point on each hand = midpoint of thumb tip + finger tip
      const rPinchPt = {
        x: (lm_R[THUMB_TIP].x + lm_R[tipIdx].x) / 2,
        y: (lm_R[THUMB_TIP].y + lm_R[tipIdx].y) / 2,
      };
      const lPinchPt = {
        x: (lm_L[THUMB_TIP].x + lm_L[tipIdx].x) / 2,
        y: (lm_L[THUMB_TIP].y + lm_L[tipIdx].y) / 2,
      };
      const dist  = dist2d(rPinchPt, lPinchPt);
      const ang   = angle2d(lPinchPt, rPinchPt);  // degrees, -180..180
      const angN  = (ang + 180) / 360;             // normalised 0..1
      const distN = clamp01(dist / 0.8);           // normalised: 0=same point, 1=full width apart
      const midpt = mid2d(rPinchPt, lPinchPt);

      // Delta from previous frame
      const prevDist = prev?.crossPinch?.[finger]?.dist ?? dist;
      const delta = dist - prevDist;              // + = moving apart, - = converging

      crossPinch[finger] = { rPinchPt, lPinchPt, dist, distN, ang, angN, midpt, delta };
    }

    // ── Also expose raw angle between wrists (useful for tilt gestures) ──
    const wristAngle  = angle2d(lWrist, rWrist);
    const wristAngleN = (wristAngle + 180) / 360;

    this.twoHand = {
      wristDist,
      indexDist,
      palmDist,
      midpoint,
      midX: midpoint.x,
      midY: midpoint.y,
      angle,
      indexDistDelta,
      spreadNorm:    clamp01(indexDist / 0.8),
      distance:      indexDist,
      // New
      crossPinch,       // { index, middle, ring, pinky } — see above
      wristAngle,
      wristAngleN,
    };

    this._emitEvent('twoHand', this.twoHand);
  }

  // ─── Landmark Smoothing ──────────────────────────────────────────────────────

  _smoothLandmarks(raw, prev) {
    if (!prev) return raw.map(l => ({ ...l }));
    const f = this.config.smoothingFactor;
    return raw.map((l, i) => ({
      x: prev[i].x * f + l.x * (1 - f),
      y: prev[i].y * f + l.y * (1 - f),
      z: prev[i].z * f + l.z * (1 - f),
    }));
  }

  // ─── Metrics Calculation ─────────────────────────────────────────────────────

  _calculateMetrics(lm) {
    // Tip indices
    const tips = { thumb: 4, index: 8, middle: 12, ring: 16, pinky: 20 };
    // MCP (knuckle) indices
    const mcps = { index: 5, middle: 9, ring: 13, pinky: 17 };
    // PIP (second joint)
    const pips = { index: 6, middle: 10, ring: 14, pinky: 18 };
    // DIP (third joint)
    const dips = { index: 7, middle: 11, ring: 15, pinky: 19 };

    const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, (a.z - b.z) * 0.5);
    const dist2d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
    const clamp01 = v => Math.max(0, Math.min(1, v));

    // ── Pinch distances (all fingers vs thumb) ──
    const pinchIndexThumb  = dist(lm[tips.thumb], lm[tips.index]);
    const pinchMiddleThumb = dist(lm[tips.thumb], lm[tips.middle]);
    const pinchRingThumb   = dist(lm[tips.thumb], lm[tips.ring]);
    const pinchPinkyThumb  = dist(lm[tips.thumb], lm[tips.pinky]);

    // ── Palm size (used to normalise distances) ──
    // Distance wrist → middle MCP as a stable reference
    const palmSize = dist(lm[0], lm[mcps.middle]) || 0.15;

    // ── Per-finger curl  [0 = fully open, 1 = fully curled] ──
    // Measured as ratio: (tip-to-MCP dist) vs (pip-to-MCP dist * expected open ratio)
    const fingerCurl = (tipIdx, pipIdx, dipIdx, mcpIdx) => {
      const tipToMcp = dist(lm[tipIdx], lm[mcpIdx]);
      const pipToMcp = dist(lm[pipIdx], lm[mcpIdx]);
      // When fully open, tip is ~2x pip distance from MCP
      const openRatio = tipToMcp / (pipToMcp * 2.0 + 0.001);
      return clamp01(1 - openRatio);
    };

    const curl = {
      index:  fingerCurl(tips.index,  pips.index,  dips.index,  mcps.index),
      middle: fingerCurl(tips.middle, pips.middle, dips.middle, mcps.middle),
      ring:   fingerCurl(tips.ring,   pips.ring,   dips.ring,   mcps.ring),
      pinky:  fingerCurl(tips.pinky,  pips.pinky,  dips.pinky,  mcps.pinky),
      // Thumb: use distance to index MCP
      thumb: clamp01(1 - dist(lm[tips.thumb], lm[mcps.index]) / 0.15),
    };

    // ── Per-finger spread angle (adjacent tip distance, normalized by palm) ──
    const spread = {
      indexMiddle:  dist2d(lm[tips.index],  lm[tips.middle]) / palmSize,
      middleRing:   dist2d(lm[tips.middle], lm[tips.ring])   / palmSize,
      ringPinky:    dist2d(lm[tips.ring],   lm[tips.pinky])  / palmSize,
      // Total spread: index tip to pinky tip
      total:        dist2d(lm[tips.index],  lm[tips.pinky])  / palmSize,
      // Thumb to index (the primary "pinch aperture" span, 0=closed 1=max open)
      thumbIndex:   clamp01(dist(lm[tips.thumb], lm[tips.index]) / (palmSize * 1.5)),
      thumbMiddle:  clamp01(dist(lm[tips.thumb], lm[tips.middle]) / (palmSize * 1.5)),
    };

    // ── Pinch aperture: continuous 0→1 per finger vs thumb ──
    // 0=fully pinched/closed, 1=fully open
    const PINCH_MAX = 0.18; // approx max thumb-index distance (normalized)
    const pinchAperture        = clamp01(pinchIndexThumb  / PINCH_MAX);
    const pinchApertureMiddle  = clamp01(pinchMiddleThumb / PINCH_MAX);
    const pinchApertureRing    = clamp01(pinchRingThumb   / PINCH_MAX);
    const pinchAperturePinky   = clamp01(pinchPinkyThumb  / PINCH_MAX);

    // ── Per-finger pinch points (midpoint between thumb tip and each finger tip) ──
    const pinchPointIndex  = { x: (lm[tips.thumb].x + lm[tips.index].x)  / 2, y: (lm[tips.thumb].y + lm[tips.index].y)  / 2 };
    const pinchPointMiddle = { x: (lm[tips.thumb].x + lm[tips.middle].x) / 2, y: (lm[tips.thumb].y + lm[tips.middle].y) / 2 };
    const pinchPointRing   = { x: (lm[tips.thumb].x + lm[tips.ring].x)   / 2, y: (lm[tips.thumb].y + lm[tips.ring].y)   / 2 };
    const pinchPointPinky  = { x: (lm[tips.thumb].x + lm[tips.pinky].x)  / 2, y: (lm[tips.thumb].y + lm[tips.pinky].y)  / 2 };

    // ── Finger extension (boolean) ──
    const isExtended = (tipIdx, pipIdx, mcpIdx) => {
      const wrist = lm[0];
      const tipDist = dist(lm[tipIdx], wrist);
      const mcpDist = dist(lm[mcpIdx], wrist);
      return tipDist > mcpDist * 1.4;
    };
    const thumbExtended = dist(lm[tips.thumb], lm[mcps.index]) > 0.08;
    const fingers = {
      thumb:  thumbExtended,
      index:  isExtended(tips.index,  pips.index,  mcps.index),
      middle: isExtended(tips.middle, pips.middle, mcps.middle),
      ring:   isExtended(tips.ring,   pips.ring,   mcps.ring),
      pinky:  isExtended(tips.pinky,  pips.pinky,  mcps.pinky),
    };
    const extendedCount = Object.values(fingers).filter(Boolean).length;

    // ── Palm center ──
    const palmCenter = {
      x: (lm[0].x + lm[5].x + lm[9].x + lm[13].x + lm[17].x) / 5,
      y: (lm[0].y + lm[5].y + lm[9].y + lm[13].y + lm[17].y) / 5,
    };

    // ── Palm spread (index tip → pinky tip absolute) ──
    const palmSpread = dist(lm[tips.index], lm[tips.pinky]);

    // ── Palm normal / tilt ──
    // Approximate wrist-to-index-MCP and wrist-to-pinky-MCP cross product for roll
    const palmRoll = Math.atan2(
      lm[mcps.index].y - lm[mcps.pinky].y,
      lm[mcps.index].x - lm[mcps.pinky].x
    ) * (180 / Math.PI);

    // ── Index finger direction ──
    const indexDirection = {
      x: lm[tips.index].x - lm[mcps.index].x,
      y: lm[tips.index].y - lm[mcps.index].y,
    };
    const indexAngle = Math.atan2(-indexDirection.y, indexDirection.x) * (180 / Math.PI);

    // ── Knuckle center (better grab anchor point) ──
    const knuckleCenter = {
      x: (lm[mcps.index].x + lm[mcps.middle].x + lm[mcps.ring].x + lm[mcps.pinky].x) / 4,
      y: (lm[mcps.index].y + lm[mcps.middle].y + lm[mcps.ring].y + lm[mcps.pinky].y) / 4,
    };

    return {
      tips,
      mcps,
      pips,
      dips,
      // Raw pinch distances (thumb vs each finger tip)
      pinchIndexThumb,
      pinchMiddleThumb,
      pinchRingThumb,
      pinchPinkyThumb,
      // Continuous aperture [0=pinched, 1=open] per finger vs thumb
      pinchAperture,        // index (primary)
      pinchApertureMiddle,
      pinchApertureRing,
      pinchAperturePinky,
      // Pinch midpoints (where each finger meets thumb)
      pinchPointIndex,
      pinchPointMiddle,
      pinchPointRing,
      pinchPointPinky,
      // Per-finger curl & spread
      curl,
      spread,
      palmSize,
      palmRoll,
      // Boolean extension
      fingers,
      extendedCount,
      // Positions
      palmCenter,
      knuckleCenter,
      palmSpread,
      indexDirection,
      indexAngle,
      // Tip shorthand
      indexTip:  lm[tips.index],
      thumbTip:  lm[tips.thumb],
      middleTip: lm[tips.middle],
      ringTip:   lm[tips.ring],
      pinkyTip:  lm[tips.pinky],
      wrist:     lm[0],
    };
  }

  // ─── Gesture Classification ───────────────────────────────────────────────────

  _classifyGesture(state) {
    const m = state.metrics;
    const f = m.fingers;
    const pt = this.config.pinchThreshold;

    // ── PINCH (index + thumb close) ──
    if (m.pinchIndexThumb < pt) {
      return {
        name: 'PINCH',
        subtype: 'index',
        x: (m.indexTip.x + m.thumbTip.x) / 2,
        y: (m.indexTip.y + m.thumbTip.y) / 2,
        strength: 1 - (m.pinchIndexThumb / pt),
        data: { distance: m.pinchIndexThumb }
      };
    }

    // ── TWO-FINGER PINCH (middle + thumb close) ──
    if (m.pinchMiddleThumb < pt) {
      return {
        name: 'PINCH',
        subtype: 'middle',
        x: (m.middleTip.x + m.thumbTip.x) / 2,
        y: (m.middleTip.y + m.thumbTip.y) / 2,
        strength: 1 - (m.pinchMiddleThumb / pt),
        data: { distance: m.pinchMiddleThumb }
      };
    }

    // ── OPEN PALM (all fingers extended) ──
    if (m.extendedCount >= 5) {
      return {
        name: 'OPEN_PALM',
        x: m.palmCenter.x,
        y: m.palmCenter.y,
        strength: m.palmSpread / 0.4,
        data: { spread: m.palmSpread }
      };
    }

    // ── FIST (no fingers extended) ──
    if (m.extendedCount === 0) {
      return {
        name: 'FIST',
        x: m.palmCenter.x,
        y: m.palmCenter.y,
        strength: 1,
        data: {}
      };
    }

    // ── POINT (only index extended) ──
    if (f.index && !f.middle && !f.ring && !f.pinky) {
      return {
        name: 'POINT',
        x: m.indexTip.x,
        y: m.indexTip.y,
        strength: 1,
        data: {
          angle: m.indexAngle,
          direction: m.indexDirection
        }
      };
    }

    // ── PEACE / SCISSORS (index + middle extended) ──
    if (f.index && f.middle && !f.ring && !f.pinky) {
      return {
        name: 'PEACE',
        x: m.palmCenter.x,
        y: m.palmCenter.y,
        strength: 1,
        data: {}
      };
    }

    // ── THUMBS UP ──
    if (f.thumb && !f.index && !f.middle && !f.ring && !f.pinky) {
      return {
        name: 'THUMBS_UP',
        x: m.thumbTip.x,
        y: m.thumbTip.y,
        strength: 1,
        data: {}
      };
    }

    // ── THREE FINGERS (index + middle + ring) ──
    if (f.index && f.middle && f.ring && !f.pinky) {
      return {
        name: 'THREE',
        x: m.palmCenter.x,
        y: m.palmCenter.y,
        strength: 1,
        data: {}
      };
    }

    // ── FOUR FINGERS ──
    if (f.index && f.middle && f.ring && f.pinky && !f.thumb) {
      return {
        name: 'FOUR',
        x: m.palmCenter.x,
        y: m.palmCenter.y,
        strength: 1,
        data: {}
      };
    }

    // ── ROCK (index + pinky extended - devil horns) ──
    if (f.index && !f.middle && !f.ring && f.pinky) {
      return {
        name: 'ROCK',
        x: m.palmCenter.x,
        y: m.palmCenter.y,
        strength: 1,
        data: {}
      };
    }

    return {
      name: 'UNKNOWN',
      x: m.palmCenter.x,
      y: m.palmCenter.y,
      strength: 0,
      data: {}
    };
  }

  // ─── Swipe Detection ──────────────────────────────────────────────────────────

  _detectSwipe(state) {
    const history = state.positionHistory;
    if (history.length < this.config.swipeHistoryLength) return null;

    const recent = history.slice(-this.config.swipeHistoryLength);
    const first = recent[0];
    const last = recent[recent.length - 1];
    const dt = (last.t - first.t) / 1000;
    if (dt === 0) return null;

    const dx = last.x - first.x;
    const dy = last.y - first.y;
    const speed = Math.hypot(dx, dy) / dt;

    if (speed < this.config.swipeVelocityThreshold) return null;

    // Determine dominant direction
    if (Math.abs(dx) > Math.abs(dy)) {
      return { direction: dx > 0 ? 'RIGHT' : 'LEFT', speed, dx, dy };
    } else {
      return { direction: dy > 0 ? 'DOWN' : 'UP', speed, dx, dy };
    }
  }

  // ─── Gesture State Machine ────────────────────────────────────────────────────

  _updateGestureState(state, rawGesture, label) {
    const prevName = state.currentGesture?.name;
    const currName = rawGesture.name;

    if (currName === prevName) {
      state.gestureConfirmCount++;
    } else {
      state.gestureConfirmCount = 1;
      state.previousGesture = state.currentGesture;
    }

    // Detect swipes when hand is open or pointing
    if (currName === 'OPEN_PALM' || currName === 'POINT' || currName === 'FIST') {
      const swipe = this._detectSwipe(state);
      if (swipe && state.gestureConfirmCount > 2) {
        this._emitEvent('swipe', { hand: label, ...swipe, gesture: rawGesture });
      }
    }

    // Pinch press/release events + drag delta
    if (currName === 'PINCH' && prevName !== 'PINCH') {
      state.pinchState = {
        active: true,
        startX: rawGesture.x,
        startY: rawGesture.y,
        x: rawGesture.x,
        y: rawGesture.y,
        dx: 0,
        dy: 0,
      };
      this._emitEvent('pinchStart', { hand: label, gesture: rawGesture, ...state.pinchState });
    } else if (currName === 'PINCH' && prevName === 'PINCH') {
      const dx = rawGesture.x - state.pinchState.x;
      const dy = rawGesture.y - state.pinchState.y;
      state.pinchState.dx = dx;
      state.pinchState.dy = dy;
      state.pinchState.x = rawGesture.x;
      state.pinchState.y = rawGesture.y;
      this._emitEvent('pinchMove', { hand: label, gesture: rawGesture, ...state.pinchState });
    } else if (currName !== 'PINCH' && prevName === 'PINCH') {
      this._emitEvent('pinchEnd', { hand: label, gesture: rawGesture, pinch: state.pinchState });
      state.pinchState.active = false;
    }

    // ── Finger aperture drag (open palm hovering — aperture controls value) ──
    // Emits continuously when NOT pinching, for "air knob" style control
    const m = state.metrics;
    if (m && currName !== 'PINCH' && currName !== 'FIST') {
      this._emitEvent('aperture', {
        hand: label,
        value: m.pinchAperture,   // 0=closed, 1=open
        curl: m.curl,
        spread: m.spread,
        x: m.indexTip?.x ?? m.palmCenter.x,
        y: m.indexTip?.y ?? m.palmCenter.y,
      });
    }

    // Gesture change events (confirmed)
    if (currName !== prevName && state.gestureConfirmCount >= this.config.gestureConfirmFrames) {
      if (state.previousGesture) {
        this._emitEvent('gestureEnd', { hand: label, gesture: state.previousGesture });
      }
      state.currentGesture = { ...rawGesture };
      this._emitEvent('gestureStart', { hand: label, gesture: state.currentGesture });
    }

    // Always keep currentGesture up to date once confirmed — so getCurrentGesture()
    // always reflects the live state, not just the last transition.
    if (state.gestureConfirmCount >= this.config.gestureConfirmFrames) {
      if (!state.currentGesture || state.currentGesture.name !== currName) {
        state.currentGesture = { ...rawGesture };
      }
    }

    // Always emit current frame data
    this._emitEvent('frame', { hand: label, gesture: rawGesture, metrics: state.metrics });
  }

  // ─── Event System ─────────────────────────────────────────────────────────────

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
    return this;
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }
    return this;
  }

  _emitEvent(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => cb(data));
    }
    // Wildcard listener
    if (this.listeners['*']) {
      this.listeners['*'].forEach(cb => cb(event, data));
    }
  }

  // ─── Utility Methods ──────────────────────────────────────────────────────────

  /** Get normalized [0,1] position of a specific landmark for a hand */
  getLandmarkPosition(handLabel, landmarkIndex) {
    const state = this.hands[handLabel];
    if (!state?.smoothedLandmarks) return null;
    return state.smoothedLandmarks[landmarkIndex];
  }

  /** Get current gesture name for a hand */
  getCurrentGesture(handLabel) {
    return this.hands[handLabel]?.currentGesture?.name || null;
  }

  /** Get all current metrics for a hand */
  getMetrics(handLabel) {
    return this.hands[handLabel]?.metrics || null;
  }

  /** Map a normalized position [0,1] to screen/canvas coordinates */
  static toScreenCoords(normalizedX, normalizedY, width, height, mirror = true) {
    return {
      x: mirror ? (1 - normalizedX) * width : normalizedX * width,
      y: normalizedY * height
    };
  }

  /** Calculate distance between two landmarks (normalized) */
  static landmarkDistance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y, (a.z - b.z) * 0.3);
  }
}

// Export for both module and browser
if (typeof module !== 'undefined' && module.exports) {
  module.exports = GestureEngine;
} else if (typeof window !== 'undefined') {
  window.GestureEngine = GestureEngine;
}

export { GestureEngine };
