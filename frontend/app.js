const statusEl = document.getElementById('status');
const transcriptEl = document.getElementById('transcript');
const micBtn = document.getElementById('micBtn');
const textInput = document.getElementById('textInput');
const sendBtn = document.getElementById('sendBtn');
const gestureBtn = document.getElementById('gestureBtn');
const continuousBtn = document.getElementById('continuousBtn');
const gestureLabelEl = document.getElementById('gestureLabel');
const camFeed = document.getElementById('camFeed');
const handCanvas = document.getElementById('handCanvas');
const handCtx = handCanvas.getContext('2d');
const ttsAudio = document.getElementById('ttsAudio');
const waveformEl = document.getElementById('waveform');
const waveformBars = waveformEl.querySelectorAll('span');
const core = document.getElementById('core');

const STATUS_LABELS = {
  idle: 'ONLINE',
  listening: 'LISTENING',
  thinking: 'THINKING',
  acting: 'WORKING',
  speaking: 'SPEAKING',
  error: 'CONNECTION LOST',
};

let ws;
let continuousMode = false;
let conversationStarted = false;
let lastAutoListenAt = 0;

continuousBtn.addEventListener('click', () => {
  continuousMode = !continuousMode;
  continuousBtn.classList.toggle('active', continuousMode);
  continuousBtn.title = continuousMode
    ? 'Hands-free mode ON — click to turn off'
    : 'Toggle hands-free conversation (auto-relisten after each reply)';
});

function maybeAutoRelisten() {
  if (!continuousMode || !conversationStarted) return;
  const now = Date.now();
  if (now - lastAutoListenAt < 1000) return; // debounce rapid duplicate idle signals
  lastAutoListenAt = now;
  setTimeout(() => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'listen' }));
  }, 400);
}

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = 'blob';

  ws.onopen = () => setState('idle');

  ws.onmessage = (event) => {
    if (event.data instanceof Blob) {
      playAudioBlob(event.data);
      return;
    }
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case 'state':
        setState(msg.state, msg.detail);
        if (msg.state === 'idle') maybeAutoRelisten();
        break;
      case 'heard':
        if (msg.text) addLine('you', msg.text);
        break;
      case 'response':
        addLine('edith', msg.text);
        break;
      case 'volume_ack':
        // Live feedback for the pinch gesture below — deliberately not
        // added to the transcript, since a continuous gesture firing
        // several times a second would spam it.
        gestureLabelEl.textContent = `VOLUME ${msg.level}%`;
        break;
      case 'error':
        setState('error');
        addLine('edith', msg.text);
        break;
    }
  };

  ws.onclose = () => {
    setState('error');
    setTimeout(connect, 1500);
  };
}

function setState(state, detail) {
  document.body.className = document.body.className.replace(/\bstate-\S+/g, '').trim();
  document.body.classList.add(`state-${state}`);
  const label = STATUS_LABELS[state] || state.toUpperCase();
  statusEl.textContent = (state === 'acting' && detail)
    ? `${label}: ${detail.replace(/_/g, ' ').toUpperCase()}`
    : label;
}

function addLine(who, text) {
  const div = document.createElement('div');
  div.className = `line ${who}`;
  const tag = document.createElement('span');
  tag.className = 'who';
  tag.textContent = who === 'you' ? 'YOU' : 'EDITH';
  div.appendChild(tag);
  div.appendChild(document.createTextNode(text));
  transcriptEl.appendChild(div);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function sendText() {
  const text = textInput.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  conversationStarted = true;
  addLine('you', text);
  ws.send(JSON.stringify({ type: 'text', text }));
  textInput.value = '';
}

sendBtn.addEventListener('click', sendText);
textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendText();
});

micBtn.addEventListener('click', () => {
  if (document.body.classList.contains('state-speaking')) {
    stopPlayback();
    return;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  conversationStarted = true;
  ws.send(JSON.stringify({ type: 'listen' }));
});

// ---------------------------------------------------------------------------
// Audio playback + real-time, audio-reactive waveform (Web Audio API)
// ---------------------------------------------------------------------------

let audioCtx = null;
let analyser = null;
let waveformRAF = null;

function ensureAudioGraph() {
  if (audioCtx) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const sourceNode = audioCtx.createMediaElementSource(ttsAudio);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 64;
  sourceNode.connect(analyser);
  analyser.connect(audioCtx.destination);
}

async function playAudioBlob(blob) {
  ensureAudioGraph();
  if (audioCtx.state === 'suspended') {
    try { await audioCtx.resume(); } catch (err) { /* resumed on next user gesture */ }
  }
  ttsAudio.src = URL.createObjectURL(blob);
  try {
    await ttsAudio.play();
    startWaveformLoop();
  } catch (err) {
    // Browser blocked autoplay — wait for the next click anywhere to retry once.
    statusEl.textContent = 'TAP TO HEAR REPLY';
    const retry = async () => {
      try { await ttsAudio.play(); startWaveformLoop(); } catch (e) { /* give up quietly */ }
      document.removeEventListener('click', retry);
    };
    document.addEventListener('click', retry, { once: true });
  }
}

ttsAudio.addEventListener('ended', () => {
  stopWaveformLoop();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'playback_done' }));
  }
  // Trigger directly instead of solely waiting on the server's echoed
  // state — don't make hands-free mode depend on a round trip succeeding.
  maybeAutoRelisten();
});

function startWaveformLoop() {
  waveformEl.classList.add('audio-driven');
  const data = new Uint8Array(analyser.frequencyBinCount);
  const step = Math.max(1, Math.floor(data.length / waveformBars.length));
  const tick = () => {
    analyser.getByteFrequencyData(data);
    waveformBars.forEach((bar, i) => {
      const value = data[i * step] || 0;
      bar.style.height = `${8 + (value / 255) * 34}px`;
    });
    waveformRAF = requestAnimationFrame(tick);
  };
  tick();
}

function stopWaveformLoop() {
  if (waveformRAF) cancelAnimationFrame(waveformRAF);
  waveformRAF = null;
  waveformEl.classList.remove('audio-driven');
  waveformBars.forEach((bar) => { bar.style.height = ''; });
}

function stopPlayback() {
  ttsAudio.pause();
  ttsAudio.currentTime = 0;
  stopWaveformLoop();
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'stop' }));
  setState('idle');
}

// ---------------------------------------------------------------------------
// Hand gesture control (MediaPipe Hand Landmarker — runs entirely on-device
// in the browser; no camera frame is ever sent to the server or the LLM).
// ---------------------------------------------------------------------------

let handLandmarker = null;
let camStream = null;
let gestureRAF = null;
let consecutiveTrackErrors = 0;
const gestureState = { current: 'none', since: 0, lastFired: null, lastFiredAt: 0 };
const HOLD_MS = 550;
const COOLDOWN_MS = 1400;

// Pinch-to-adjust-volume — a continuous gesture, handled separately from
// the discrete hold-to-fire ones above. Thresholds are normalized against
// the hand's own on-screen size (thumb-to-index distance divided by
// wrist-to-middle-knuckle distance) so it works at different distances
// from the camera, but the exact numbers are a starting point — tune
// PINCH_CLOSED/PINCH_OPEN against your own webcam and hand if it feels
// off, since this wasn't tunable against a live camera from here.
const PINCH_CLOSED = 0.15;
const PINCH_OPEN = 1.1;
const PINCH_ENGAGE_MAX = 0.85; // above this ratio, treat the hand as "not pinching" (relaxed/open)
let lastVolumeSent = -1;
let lastVolumeSentAt = 0;

const HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [0, 9], [9, 10], [10, 11], [11, 12],
  [0, 13], [13, 14], [14, 15], [15, 16],
  [0, 17], [17, 18], [18, 19], [19, 20],
  [5, 9], [9, 13], [13, 17],
];

gestureBtn.addEventListener('click', () => {
  if (document.body.classList.contains('gesture-active')) {
    disableGestureControl();
  } else {
    enableGestureControl();
  }
});

async function enableGestureControl() {
  gestureBtn.disabled = true;
  gestureBtn.title = 'Loading hand tracking...';
  gestureLabelEl.textContent = 'STARTING CAMERA...';
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 360 }, audio: false });
    camFeed.srcObject = camStream;
    await camFeed.play();

    if (!handLandmarker) {
      gestureLabelEl.textContent = 'LOADING HAND MODEL...';
      const visionModule = await import('https://esm.sh/@mediapipe/tasks-vision@0.10.3');
      const { FilesetResolver, HandLandmarker } = visionModule;
      const filesetResolver = await FilesetResolver.forVisionTasks(
        'https://esm.sh/@mediapipe/tasks-vision@0.10.3/wasm'
      );
      handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
        baseOptions: {
          modelAssetPath:
            'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
          delegate: 'GPU',
        },
        runningMode: 'VIDEO',
        numHands: 1,
      });
    }

    document.body.classList.add('gesture-active');
    gestureBtn.classList.add('active');
    gestureBtn.disabled = false;
    gestureBtn.title = 'Open palm = listen, fist = stop, thumbs up = confirm, pinch = adjust volume. Click to disable.';
    gestureLabelEl.textContent = 'GESTURES READY';
    consecutiveTrackErrors = 0;
    trackHands();
  } catch (err) {
    console.error('Gesture control failed to start:', err);
    gestureBtn.title = 'Gesture control unavailable — click to retry.';
    gestureBtn.disabled = false;
    // Visible in the UI, not just the browser console — a name/message so
    // it can actually be diagnosed instead of silently doing nothing.
    gestureLabelEl.textContent = `GESTURE ERROR: ${err.name || 'FAILED'}`;
    disableGestureControl();
  }
}

function disableGestureControl() {
  if (gestureRAF) cancelAnimationFrame(gestureRAF);
  gestureRAF = null;
  if (camStream) {
    camStream.getTracks().forEach((t) => t.stop());
    camStream = null;
  }
  handCtx.clearRect(0, 0, handCanvas.width, handCanvas.height);
  gestureLabelEl.textContent = '';
  resetOrbTransform();
  document.body.classList.remove('gesture-active');
  gestureBtn.classList.remove('active');
  gestureBtn.title = 'Toggle hand gesture control';
}

function trackHands() {
  if (!handLandmarker || !camFeed.videoWidth) {
    gestureRAF = requestAnimationFrame(trackHands);
    return;
  }
  handCanvas.width = camFeed.videoWidth;
  handCanvas.height = camFeed.videoHeight;

  try {
    const results = handLandmarker.detectForVideo(camFeed, performance.now());
    handCtx.clearRect(0, 0, handCanvas.width, handCanvas.height);

    if (results.landmarks && results.landmarks.length > 0) {
      const landmarks = results.landmarks[0];
      drawSkeleton(landmarks);
      updateGestureState(classifyGesture(landmarks));
      updateOrbTransform(landmarks);
      handlePinchVolume(landmarks);
    } else {
      updateGestureState('none');
      resetOrbTransform();
    }
    consecutiveTrackErrors = 0;
  } catch (err) {
    consecutiveTrackErrors += 1;
    console.error('Hand tracking frame failed:', err);
    if (consecutiveTrackErrors > 20) {
      gestureLabelEl.textContent = `TRACKING FAILED: ${err.name || 'ERROR'}`;
      disableGestureControl();
      return; // stop the loop instead of erroring forever
    }
  }

  gestureRAF = requestAnimationFrame(trackHands);
}

function drawSkeleton(landmarks) {
  const w = handCanvas.width, h = handCanvas.height;
  handCtx.strokeStyle = 'rgba(79, 216, 255, 0.85)';
  handCtx.lineWidth = 2;
  HAND_CONNECTIONS.forEach(([a, b]) => {
    handCtx.beginPath();
    handCtx.moveTo((1 - landmarks[a].x) * w, landmarks[a].y * h);
    handCtx.lineTo((1 - landmarks[b].x) * w, landmarks[b].y * h);
    handCtx.stroke();
  });
  handCtx.fillStyle = '#4fd8ff';
  landmarks.forEach((lm) => {
    handCtx.beginPath();
    handCtx.arc((1 - lm.x) * w, lm.y * h, 3, 0, Math.PI * 2);
    handCtx.fill();
  });
}

// The orb (the existing SVG ring core, #core) drifts toward your hand's
// on-screen position — the same "the interface responds to your hand"
// feel as a reactive 3D orb, done with a CSS transform on the existing 2D
// HUD instead of introducing a Three.js/WebGL rewrite. That's a deliberate
// tradeoff: a real WebGL orb would look closer to the reels that inspired
// this, but it's a materially bigger dependency and rebuild than a
// transform on what's already here — worth doing as a dedicated follow-up
// if the look matters more than the lightweight, build-step-free frontend.
function updateOrbTransform(landmarks) {
  const avgX = landmarks.reduce((s, l) => s + l.x, 0) / landmarks.length;
  const avgY = landmarks.reduce((s, l) => s + l.y, 0) / landmarks.length;
  // Mirrored the same way drawSkeleton mirrors the skeleton overlay, so the
  // orb drifts the same direction your hand visually appears to move.
  const mirroredX = 1 - avgX;
  const offsetX = (mirroredX - 0.5) * 70;
  const offsetY = (avgY - 0.5) * 70;
  core.style.transform = `translate(${offsetX.toFixed(1)}px, ${offsetY.toFixed(1)}px)`;
}

function resetOrbTransform() {
  core.style.transform = 'translate(0px, 0px)';
}

function pinchRatio(landmarks) {
  const pinchDist = Math.hypot(landmarks[4].x - landmarks[8].x, landmarks[4].y - landmarks[8].y);
  const palmScale = Math.hypot(landmarks[0].x - landmarks[9].x, landmarks[0].y - landmarks[9].y) || 1;
  return pinchDist / palmScale;
}

// A clenched fist also brings the thumb and index tip close together (they
// converge near the palm as all the fingers curl in) - pinchRatio alone
// can't tell that apart from a deliberate pinch. What does: a real pinch
// is held forward, away from the palm; a fist's convergence point sits
// right on top of the palm center. Tested against synthetic landmark data
// for both poses before relying on it - see the 0.5 threshold below.
function pinchDistanceFromPalm(landmarks) {
  const midX = (landmarks[4].x + landmarks[8].x) / 2;
  const midY = (landmarks[4].y + landmarks[8].y) / 2;
  const palmX = (landmarks[0].x + landmarks[5].x + landmarks[9].x + landmarks[13].x + landmarks[17].x) / 5;
  const palmY = (landmarks[0].y + landmarks[5].y + landmarks[9].y + landmarks[13].y + landmarks[17].y) / 5;
  const palmScale = Math.hypot(landmarks[0].x - landmarks[9].x, landmarks[0].y - landmarks[9].y) || 1;
  return Math.hypot(midX - palmX, midY - palmY) / palmScale;
}

function handlePinchVolume(landmarks) {
  const ratio = pinchRatio(landmarks);
  if (ratio > PINCH_ENGAGE_MAX) return; // hand is open/relaxed, not deliberately pinching
  if (pinchDistanceFromPalm(landmarks) < 0.5) return; // that's a closing fist, not a pinch held forward
  const clamped = Math.min(1, Math.max(0, (ratio - PINCH_CLOSED) / (PINCH_OPEN - PINCH_CLOSED)));
  const level = Math.round(clamped * 100);
  const now = performance.now();
  if (Math.abs(level - lastVolumeSent) < 3 || now - lastVolumeSentAt < 150) return;
  lastVolumeSent = level;
  lastVolumeSentAt = now;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'set_volume', level }));
  }
}

function isExtended(landmarks, tipIdx, pipIdx) {
  return landmarks[tipIdx].y < landmarks[pipIdx].y;
}

function classifyGesture(landmarks) {
  const indexUp = isExtended(landmarks, 8, 6);
  const middleUp = isExtended(landmarks, 12, 10);
  const ringUp = isExtended(landmarks, 16, 14);
  const pinkyUp = isExtended(landmarks, 20, 18);
  const fingersUp = [indexUp, middleUp, ringUp, pinkyUp].filter(Boolean).length;
  const thumbUp = landmarks[4].y < landmarks[3].y && landmarks[4].y < landmarks[2].y;

  // A pinch (thumb + index close, other fingers not all extended) is
  // handled continuously above for volume, not as a discrete hold-to-fire
  // gesture — checked first, and gated on fingersUp <= 2, so it never
  // collides with open_palm (fingersUp >= 3) or gets misread as "fist"
  // (which would wrongly fire stopPlayback mid-adjustment).
  if (fingersUp <= 2 && pinchRatio(landmarks) < 0.55 && pinchDistanceFromPalm(landmarks) > 0.5) return 'pinch';
  if (fingersUp >= 3) return 'open_palm';
  if (fingersUp === 0 && thumbUp) return 'thumbs_up';
  if (fingersUp === 0 && !thumbUp) return 'fist';
  return 'none';
}

function updateGestureState(gesture) {
  const now = performance.now();
  if (gesture !== gestureState.current) {
    gestureState.current = gesture;
    gestureState.since = now;
  }
  // 'pinch' gets its own live "VOLUME xx%" label from handlePinchVolume
  // instead of the generic gesture-name label.
  if (gesture !== 'pinch') {
    gestureLabelEl.textContent = gesture === 'none' ? '' : gesture.replace('_', ' ').toUpperCase();
  }

  const held = now - gestureState.since;
  if (gesture === 'none' || gesture === 'pinch' || held < HOLD_MS) return;
  if (gestureState.lastFired === gesture && now - gestureState.lastFiredAt < COOLDOWN_MS) return;

  gestureState.lastFired = gesture;
  gestureState.lastFiredAt = now;
  fireGesture(gesture);
}

function fireGesture(gesture) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  if (gesture === 'open_palm') {
    conversationStarted = true;
    ws.send(JSON.stringify({ type: 'listen' }));
  } else if (gesture === 'fist') {
    stopPlayback();
  } else if (gesture === 'thumbs_up') {
    conversationStarted = true;
    addLine('you', 'yes');
    ws.send(JSON.stringify({ type: 'text', text: 'yes' }));
  }
}

connect();