// ═══════════════════════════════════════════════════════════════
// Voice Shopping Assistant — app.ts
// Voice-reactive soft glow orb + live caption + always-visible transcript
// ═══════════════════════════════════════════════════════════════

// ─── Constants ───
const REALTIME_MODEL = "gpt-realtime-mini";
const REALTIME_URL = `https://api.openai.com/v1/realtime?model=${REALTIME_MODEL}`;

// gpt-realtime-mini pricing (USD per token)
// https://openai.com/api/pricing/
const PRICING = {
  textInput: 0.60 / 1_000_000,
  textCached: 0.30 / 1_000_000,
  textOutput: 2.40 / 1_000_000,
  audioInput: 10.00 / 1_000_000,
  audioCached: 0.30 / 1_000_000,
  audioOutput: 20.00 / 1_000_000,
};

// Orb colors — two states only
const STATE_COLORS: Record<string, number[]> = {
  active: [0.29, 0.56, 0.96],  // blue
  disconnected: [0.35, 0.38, 0.50],  // muted gray
};

// ─── State ───
interface OrbGL {
  gl: WebGLRenderingContext;
  program: WebGLProgram;
  posBuf: WebGLBuffer;
  uvBuf: WebGLBuffer;
  aPosition: number;
  aUv: number;
  uTime: WebGLUniformLocation | null;
  uColor: WebGLUniformLocation | null;
  uResolution: WebGLUniformLocation | null;
  uAmplitude: WebGLUniformLocation | null;
  uSpeed: WebGLUniformLocation | null;
  uBreath: WebGLUniformLocation | null;
}

interface AppState {
  pc: RTCPeerConnection | null;
  dc: RTCDataChannel | null;
  audioEl: HTMLAudioElement | null;
  localStream: MediaStream | null;
  cart_id: string | null;
  store_id: string | null;
  banner: string | null;
  cart_url: string | null;
  currentAssistantMsg: string;
  currentResponseId: string | null;
  productNames: Record<string, string>;
  productSizes: Record<string, string>;
  // Audio analysis
  audioCtx: AudioContext | null;
  analyser: AnalyserNode | null;
  analyserData: Uint8Array | null;
  smoothedAudioLevel: number;
  remoteSource: AudioNode | null;
  awaitingAudioDrain: boolean;
  // Orb
  currentStatus: string;
  orbColor: number[];
  orbAnimId: number | null;
  orbGL: OrbGL | null;
  spinAngle: number;
  spinSpeed: number;
  breathMix: number;
  // Caption
  captionTimeout: ReturnType<typeof setTimeout> | null;
  // Inactivity auto-shutdown (30s)
  inactivityTimer: ReturnType<typeof setTimeout> | null;
  // Max session duration timer
  sessionTimer: ReturnType<typeof setTimeout> | null;
  // Transcript
  hasTranscriptContent: boolean;
  // Cost tracking
  sessionCost: number;
}

const state: AppState = {
  pc: null,
  dc: null,
  audioEl: null,
  localStream: null,
  cart_id: null,
  store_id: null,
  banner: null,
  cart_url: null,
  currentAssistantMsg: "",
  currentResponseId: null,
  productNames: {},
  productSizes: {},
  // Audio analysis
  audioCtx: null,
  analyser: null,
  analyserData: null,
  smoothedAudioLevel: 0,
  remoteSource: null,
  awaitingAudioDrain: false,
  // Orb
  currentStatus: "disconnected",
  orbColor: [0.35, 0.38, 0.50],
  orbAnimId: null,
  orbGL: null,
  spinAngle: 0,
  spinSpeed: 0,
  breathMix: 1,
  // Caption
  captionTimeout: null,
  // Inactivity auto-shutdown
  inactivityTimer: null,
  // Max session duration
  sessionTimer: null,
  // Transcript
  hasTranscriptContent: false,
  // Cost tracking
  sessionCost: 0,
};

// ─── DOM References ───
const startBtn = document.getElementById("start-btn") as HTMLButtonElement;
const startSection = document.getElementById("start-section")!;
const sessionSection = document.getElementById("session-section")!;
const orbGlow = document.getElementById("orb-glow")!;
const orbClip = document.getElementById("orb-clip")!;
const liveCaption = document.getElementById("live-caption")!;
const cartSection = document.getElementById("cart-section")!;
const cartItems = document.getElementById("cart-items")!;
const cartLink = document.getElementById("cart-link")!;
const transcriptToggle = document.getElementById("transcript-toggle")!;
const transcriptPanel = document.getElementById("transcript-panel")!;
const transcript = document.getElementById("transcript")!;
const stopBtn = document.getElementById("stop-btn") as HTMLButtonElement;
const costToggle = document.getElementById("cost-toggle")!;
const costValueEl = costToggle.querySelector(".cost-value") as HTMLSpanElement;

// ─── Event Listeners ───
startBtn.addEventListener("click", startSession);
stopBtn.addEventListener("click", endSession);
transcriptToggle.addEventListener("click", toggleTranscript);
costToggle.addEventListener("click", () => costToggle.classList.toggle("expanded"));
cartItems.addEventListener("scroll", () => {
  cartItems.classList.toggle("scrolled", cartItems.scrollTop > 0);
});

// ═══════════════════════════════════════════════════════════════
// WebGL Nebula Bloom Orb (FBM noise cloud)
// ═══════════════════════════════════════════════════════════════

const VERT_SRC = `
attribute vec2 position;
attribute vec2 uv;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0, 1);
}`;

const FRAG_SRC = `
precision highp float;
uniform float uTime;
uniform vec3 uColor;
uniform vec3 uResolution;
uniform float uAmplitude;
uniform float uSpeed;
uniform float uBreath;
varying vec2 vUv;

// --- Simplex-style gradient noise (2D) ---
vec3 mod289(vec3 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
vec2 mod289v2(vec2 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
vec3 permute(vec3 x) { return mod289((x * 34.0 + 1.0) * x); }

float snoise(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439,
                      -0.577350269189626, 0.024390243902439);
  vec2 i  = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0,0.0) : vec2(0.0,1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod289v2(i);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0))
                            + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy),
                           dot(x12.zw,x12.zw)), 0.0);
  m = m * m; m = m * m;
  vec3 x_ = 2.0 * fract(p * C.www) - 1.0;
  vec3 h  = abs(x_) - 0.5;
  vec3 ox = floor(x_ + 0.5);
  vec3 a0 = x_ - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0*a0 + h*h);
  vec3 g;
  g.x = a0.x * x0.x   + h.x * x0.y;
  g.y = a0.y * x12.x  + h.y * x12.y;
  g.z = a0.z * x12.z  + h.z * x12.w;
  return 130.0 * dot(m, g);
}

// --- 3D simplex noise (time-varying surfaces) ---
vec4 mod289v4(vec4 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
vec4 permute4(vec4 x) { return mod289v4((x * 34.0 + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise3(vec3 v) {
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g2 = step(x0.yzx, x0.xyz);
  vec3 g3 = 1.0 - g2;
  vec3 i1 = min(g2, g3.zxy);
  vec3 i2 = max(g2, g3.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - 0.5;
  i = mod289(i);
  vec4 p = permute4(permute4(permute4(
    i.z + vec4(0.0, i1.z, i2.z, 1.0))
  + i.y + vec4(0.0, i1.y, i2.y, 1.0))
  + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  vec4 j = p - 49.0 * floor(p * (1.0/49.0));
  vec4 x_ = floor(j * (1.0/7.0));
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 xx = (x_ * 2.0 + 0.5) / 7.0 - 1.0;
  vec4 yy = (y_ * 2.0 + 0.5) / 7.0 - 1.0;
  vec4 h  = 1.0 - abs(xx) - abs(yy);
  vec4 b0 = vec4(xx.xy, yy.xy);
  vec4 b1 = vec4(xx.zw, yy.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 g0 = vec3(a0.xy, h.x);
  vec3 g1 = vec3(a0.zw, h.y);
  vec3 gg2 = vec3(a1.xy, h.z);
  vec3 gg3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(g0,g0),dot(g1,g1),dot(gg2,gg2),dot(gg3,gg3)));
  g0 *= norm.x; g1 *= norm.y; gg2 *= norm.z; gg3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)), 0.0);
  m = m * m; m = m * m;
  return 42.0 * dot(m, vec4(dot(g0,x0),dot(g1,x1),dot(gg2,x2),dot(gg3,x3)));
}

// --- FBM: 2 octaves, low frequency — very smooth, blobby ---
float fbm(vec3 p) {
  return snoise3(p) * 0.6 + snoise3(p * 1.5 + vec3(100.0, 100.0, 0.0)) * 0.3;
}

// --- 2D FBM for domain warping — very smooth ---
float fbm2(vec2 p) {
  return snoise(p) * 0.6 + snoise(p * 1.5 + vec2(100.0)) * 0.3;
}

void main() {
  float mr = min(uResolution.x, uResolution.y);
  vec2 uv = (vUv * 2.0 - 1.0) * uResolution.xy / mr;
  float dist = length(uv);

  // Soft organic edge mask
  float mask = smoothstep(1.02, 0.65, dist);

  // Breathing: slow ambient pulse on scale + brightness
  float breath = uBreath;

  // Polar rotation with accumulated angle
  float angle = atan(uv.y, uv.x) + uSpeed;
  vec2 rotUv = vec2(dist * cos(angle), dist * sin(angle));

  // === Domain warping: feed FBM into itself for swirling plasma ===
  float t = uTime * 0.12;
  float warpStrength = 0.6 + uAmplitude * 1.2;

  // First warp pass
  float w1 = fbm(vec3(rotUv * 1.0, t));
  float w2 = fbm(vec3(rotUv * 1.0 + vec2(5.2, 1.3), t * 0.8));
  vec2 warpedUv = rotUv + vec2(w1, w2) * warpStrength;

  // Second warp pass (feeds first warp output back in)
  float w3 = fbm(vec3(warpedUv * 0.8, t * 1.1));
  float w4 = fbm(vec3(warpedUv * 0.8 + vec2(1.7, 9.2), t * 0.9));
  warpedUv = rotUv + vec2(w3, w4) * warpStrength * 0.8;

  // Main noise value from the warped coordinates
  float n = fbm(vec3(warpedUv * (0.8 + uAmplitude * 1.0), t * 1.3));
  n = n * 0.5 + 0.5; // remap to 0..1

  // === Multi-layer color mixing ===
  // Warm highlight (shifts toward white/cyan at peaks)
  vec3 highlight = vec3(0.85, 0.95, 1.0);
  // Cool shadow (deeper, more saturated version of base color)
  vec3 shadow = uColor * vec3(0.3, 0.4, 0.7);
  // Subsurface warm glow
  vec3 subsurface = uColor * vec3(1.3, 0.8, 0.6);

  // Mix layers based on noise + a secondary noise for variation
  float n2 = fbm2(warpedUv * 2.0 + t * 0.5);
  n2 = n2 * 0.5 + 0.5;

  vec3 col = mix(shadow, uColor, smoothstep(0.2, 0.6, n));
  col = mix(col, subsurface, smoothstep(0.5, 0.8, n2) * 0.4);
  col = mix(col, highlight, smoothstep(0.7, 0.95, n) * (0.3 + uAmplitude * 0.5));

  // Overall brightness with breathing and amplitude
  float brightness = 0.55 + n * 0.6 + uAmplitude * 0.4 + breath * 0.15;
  col *= brightness;

  // === Fresnel rim with chromatic fringing ===
  float rimBase = pow(smoothstep(0.3, 0.92, dist), 2.5) * smoothstep(1.05, 0.92, dist);
  float rimIntensity = 0.25 + uAmplitude * 0.6 + breath * 0.1;

  // Chromatic aberration: offset R, G, B channels at the rim
  float chromaOffset = 0.015 + uAmplitude * 0.01;
  vec2 uvR = (vUv * 2.0 - 1.0) * (1.0 + chromaOffset) * uResolution.xy / mr;
  vec2 uvB = (vUv * 2.0 - 1.0) * (1.0 - chromaOffset) * uResolution.xy / mr;
  float distR = length(uvR);
  float distB = length(uvB);
  float rimR = pow(smoothstep(0.3, 0.92, distR), 2.5) * smoothstep(1.05, 0.92, distR);
  float rimB = pow(smoothstep(0.3, 0.92, distB), 2.5) * smoothstep(1.05, 0.92, distB);

  col.r += uColor.r * rimR * rimIntensity * 1.2;
  col.g += uColor.g * rimBase * rimIntensity;
  col.b += uColor.b * rimB * rimIntensity * 1.3;

  // Inner glow — simulates subsurface scattering near center
  float innerGlow = smoothstep(0.6, 0.0, dist) * (0.08 + uAmplitude * 0.12 + breath * 0.06);
  col += highlight * innerGlow;

  gl_FragColor = vec4(col * mask, 1.0);
}`;

function compileShader(gl: WebGLRenderingContext, type: number, source: string): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.error("Shader compile error: " + gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

function linkProgram(gl: WebGLRenderingContext, vs: WebGLShader, fs: WebGLShader): WebGLProgram | null {
  const program = gl.createProgram();
  if (!program) return null;
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error("Program link error: " + gl.getProgramInfoLog(program));
    return null;
  }
  return program;
}

function initOrbGL() {
  const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
  const gl = canvas.getContext("webgl");
  if (!gl) {
    console.error("WebGL not supported");
    return;
  }

  const vs = compileShader(gl, gl.VERTEX_SHADER, VERT_SRC);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, FRAG_SRC);
  if (!vs || !fs) return;
  const program = linkProgram(gl, vs, fs);
  if (!program) return;

  // Full-screen triangle covering clip space
  const posBuf = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);

  const uvBuf = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, uvBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 2, 0, 0, 2]), gl.STATIC_DRAW);

  state.orbGL = {
    gl,
    program,
    posBuf,
    uvBuf,
    aPosition: gl.getAttribLocation(program, "position"),
    aUv: gl.getAttribLocation(program, "uv"),
    uTime: gl.getUniformLocation(program, "uTime"),
    uColor: gl.getUniformLocation(program, "uColor"),
    uResolution: gl.getUniformLocation(program, "uResolution"),
    uAmplitude: gl.getUniformLocation(program, "uAmplitude"),
    uSpeed: gl.getUniformLocation(program, "uSpeed"),
    uBreath: gl.getUniformLocation(program, "uBreath"),
  };

  resizeOrbCanvas();
  window.addEventListener("resize", resizeOrbCanvas);
}

function resizeOrbCanvas() {
  if (!state.orbGL) return;
  const canvas = state.orbGL.gl.canvas as HTMLCanvasElement;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
}

function renderOrbFrame(time: number) {
  const o = state.orbGL;
  if (!o) return;
  const gl = o.gl;

  // Update audio level from analyser
  if (state.analyser && state.analyserData) {
    state.analyser.getByteFrequencyData(state.analyserData);
    let sum = 0;
    for (let i = 0; i < state.analyserData.length; i++) sum += state.analyserData[i];
    const avg = sum / state.analyserData.length;
    const norm = Math.min(1, Math.max(0, (avg - 13) / 200));
    // Fast attack, slow decay — keeps orb alive through brief speech gaps
    const smoothing = norm > state.smoothedAudioLevel ? 0.15 : 0.012;
    state.smoothedAudioLevel += (norm - state.smoothedAudioLevel) * smoothing;
  } else {
    state.smoothedAudioLevel += (0 - state.smoothedAudioLevel) * 0.012;
  }

  // Audio drain detection: transition to listening when audio actually goes silent
  if (state.awaitingAudioDrain && state.smoothedAudioLevel < 0.005) {
    state.awaitingAudioDrain = false;
    setStatus("listening");
    resetInactivityTimer();
  }

  const level = state.smoothedAudioLevel;

  // Orb color: active (blue) vs disconnected (gray)
  const orbKey = state.currentStatus === "disconnected" ? "disconnected" : "active";
  const target = STATE_COLORS[orbKey];
  for (let i = 0; i < 3; i++) {
    state.orbColor[i] += (target[i] - state.orbColor[i]) * 0.035;
  }

  // Audio-reactive amplitude (drives FBM detail + rim brightness)
  const amplitude = 0.05 + level * 0.25;

  // Idle breathing — slow sine pulse that fades out when audio is active
  const breathTarget = level > 0.02 ? 0 : 1;
  state.breathMix += (breathTarget - state.breathMix) * 0.01;
  const breath = Math.sin(time * 0.0008) * 0.5 + 0.5; // 0..1 slow pulse
  const breathValue = breath * state.breathMix;

  // Smooth continuous rotation — driven purely by audio level
  const hasAudio = level > 0.01;
  const targetSpinSpeed = hasAudio ? 0.3 + level * 0.5 : 0.05; // slightly faster idle spin
  state.spinSpeed += (targetSpinSpeed - state.spinSpeed) * 0.02;
  state.spinAngle = (state.spinAngle + state.spinSpeed / 60) % (Math.PI * 200);

  // Render WebGL
  gl.viewport(0, 0, gl.canvas.width, gl.canvas.height);
  gl.useProgram(o.program);

  gl.bindBuffer(gl.ARRAY_BUFFER, o.posBuf);
  gl.enableVertexAttribArray(o.aPosition);
  gl.vertexAttribPointer(o.aPosition, 2, gl.FLOAT, false, 0, 0);

  gl.bindBuffer(gl.ARRAY_BUFFER, o.uvBuf);
  gl.enableVertexAttribArray(o.aUv);
  gl.vertexAttribPointer(o.aUv, 2, gl.FLOAT, false, 0, 0);

  gl.uniform1f(o.uTime, time * 0.001);
  gl.uniform3f(o.uColor, state.orbColor[0], state.orbColor[1], state.orbColor[2]);
  gl.uniform3f(o.uResolution, gl.canvas.width, gl.canvas.height, gl.canvas.width / gl.canvas.height);
  gl.uniform1f(o.uAmplitude, amplitude);
  gl.uniform1f(o.uSpeed, state.spinAngle);
  gl.uniform1f(o.uBreath, breathValue);

  gl.drawArrays(gl.TRIANGLES, 0, 3);

  // Update glow color and intensity — highly reactive to audio
  const c = state.orbColor;
  const r = Math.round(c[0] * 255);
  const g = Math.round(c[1] * 255);
  const b = Math.round(c[2] * 255);
  const glowOpacity = 0.08 + level * 3.0;
  const glowInset = -50 - level * 100;
  const blurSize = 50 + level * 60;
  orbGlow.style.background = `rgba(${r}, ${g}, ${b}, ${Math.min(glowOpacity, 1)})`;
  orbGlow.style.inset = `${glowInset}px`;
  orbGlow.style.filter = `blur(${blurSize}px)`;
  orbClip.style.boxShadow = `0 0 ${60 + level * 160}px rgba(${r}, ${g}, ${b}, ${0.15 + level * 0.6})`;

  // Scale: audio-reactive + idle breathing
  const scale = 1 + level * 0.12 + breathValue * 0.03;
  orbClip.style.transform = `scale(${scale})`;

  state.orbAnimId = requestAnimationFrame(renderOrbFrame);
}

function startOrbLoop() {
  if (state.orbAnimId) return;
  state.orbAnimId = requestAnimationFrame(renderOrbFrame);
}

function stopOrbLoop() {
  if (state.orbAnimId) {
    cancelAnimationFrame(state.orbAnimId);
    state.orbAnimId = null;
  }
}

// ═══════════════════════════════════════════════════════════════
// UI Helpers
// ═══════════════════════════════════════════════════════════════

function setStatus(s: "connecting" | "listening" | "thinking" | "speaking" | "disconnected") {
  state.currentStatus = s;
}

// ─── Session Cost & Duration Limits ───
const MAX_SESSION_DURATION_MS = 15 * 60 * 1_000; // 15 minutes hard limit
const MAX_SESSION_COST_USD = 2.00; // $2 cost ceiling per session

// ─── Inactivity Auto-Shutdown ───
const INACTIVITY_TIMEOUT_MS = 10_000;

function resetInactivityTimer() {
  if (state.inactivityTimer) clearTimeout(state.inactivityTimer);
  state.inactivityTimer = setTimeout(() => {
    console.log("Inactivity timeout — ending session");
    addMessage("system", "Session ended due to inactivity.");
    setCaption("Session ended due to inactivity.", "system");
    endSession();
  }, INACTIVITY_TIMEOUT_MS);
}

function clearInactivityTimer() {
  if (state.inactivityTimer) {
    clearTimeout(state.inactivityTimer);
    state.inactivityTimer = null;
  }
}

// ─── Cost Tracking ───
function calculateUsageCost(usage: any): number {
  if (!usage) return 0;

  const inp = usage.input_token_details || {};
  const out = usage.output_token_details || {};
  const cached = inp.cached_tokens_details || {};

  const textIn = (inp.text_tokens || 0) - (cached.text_tokens || 0);
  const textCach = cached.text_tokens || 0;
  const audioIn = (inp.audio_tokens || 0) - (cached.audio_tokens || 0);
  const audioCach = cached.audio_tokens || 0;
  const textOut = out.text_tokens || 0;
  const audioOut = out.audio_tokens || 0;

  return (
    textIn * PRICING.textInput +
    textCach * PRICING.textCached +
    audioIn * PRICING.audioInput +
    audioCach * PRICING.audioCached +
    textOut * PRICING.textOutput +
    audioOut * PRICING.audioOutput
  );
}

function updateCostDisplay() {
  const cost = state.sessionCost;
  if (cost <= 0) {
    costToggle.classList.remove("visible");
    return;
  }
  costValueEl.textContent = cost < 0.01
    ? `$${cost.toFixed(4)}`
    : `$${cost.toFixed(2)}`;
  costToggle.classList.add("visible");
  // Enforce cost ceiling
  if (cost >= MAX_SESSION_COST_USD) {
    console.log(`Session cost $${cost.toFixed(2)} exceeded limit — ending session`);
    addMessage("system", "Session ended — cost limit reached.");
    setCaption("Session ended — cost limit reached.", "system");
    endSession();
  }
}

// ─── Live Caption ───
function setCaption(text: string, role = "assistant") {
  // Show beginning of text, truncate at 350 characters
  liveCaption.textContent = text.length > 350 ? text.slice(0, 350) + "…" : text;
  liveCaption.className = "visible role-" + role;
  // Show beginning of text, not the end
  liveCaption.scrollTop = 0;

  if (state.captionTimeout) {
    clearTimeout(state.captionTimeout);
    state.captionTimeout = null;
  }

  // System captions fade after a delay; assistant and user captions
  // stay visible until the next caption replaces them.
  if (role === "system") {
    state.captionTimeout = setTimeout(() => {
      liveCaption.classList.remove("visible");
    }, 3000);
  }
}

function clearCaption() {
  if (state.captionTimeout) {
    clearTimeout(state.captionTimeout);
    state.captionTimeout = null;
  }
  liveCaption.classList.remove("visible");
}

// ─── Transcript (hidden panel) ───
function addMessage(role: "assistant" | "user" | "system", text: string): HTMLElement {
  const el = document.createElement("div");
  el.className = "msg " + role;
  el.textContent = text;
  transcript.appendChild(el);

  if (transcriptPanel.classList.contains("expanded")) {
    transcriptPanel.scrollTop = transcriptPanel.scrollHeight;
  }

  if (!state.hasTranscriptContent) {
    state.hasTranscriptContent = true;
    transcriptToggle.classList.add("visible");
  }

  return el;
}

// ─── Transcript Toggle ───
function toggleTranscript() {
  const isExpanded = transcriptPanel.classList.toggle("expanded");
  transcriptToggle.classList.toggle("expanded", isExpanded);
  transcriptToggle.querySelector("span")!.textContent = isExpanded ? "Hide transcript" : "Show transcript";
  if (isExpanded) {
    transcriptPanel.scrollTop = transcriptPanel.scrollHeight;
  }
}

// ─── Cart ───
function addCartItem(name: string, qty?: string, productCode?: string, size?: string) {
  cartSection.classList.add("active");
  const li = document.createElement("li");
  if (productCode) li.dataset.productCode = productCode;
  const nameSpan = document.createElement("span");
  nameSpan.className = "cart-item-name";
  nameSpan.textContent = name;
  li.appendChild(nameSpan);
  const badgeWrap = document.createElement("span");
  badgeWrap.className = "cart-item-badges";
  if (size) {
    const sizeSpan = document.createElement("span");
    sizeSpan.className = "cart-badge cart-badge-size";
    sizeSpan.textContent = size;
    badgeWrap.appendChild(sizeSpan);
  }
  if (qty) {
    const qtySpan = document.createElement("span");
    qtySpan.className = "cart-badge cart-badge-qty";
    qtySpan.textContent = qty;
    badgeWrap.appendChild(qtySpan);
  }
  li.appendChild(badgeWrap);
  cartItems.appendChild(li);
  cartItems.scrollTop = cartItems.scrollHeight;
}

function removeCartItem(productCode: string) {
  const items = cartItems.querySelectorAll("li");
  for (const li of items) {
    if ((li as HTMLElement).dataset.productCode === productCode) {
      li.remove();
      break;
    }
  }
  if (cartItems.children.length === 0) {
    cartSection.classList.remove("active");
  }
}

function showCartLink() {
  if (state.cart_id) {
    const a = document.getElementById("cart-link-a") as HTMLAnchorElement;
    const baseUrl = state.cart_url || "/cart";
    a.href = `${baseUrl}?forceCartId=${state.cart_id}`;
  }
  cartLink.style.display = "block";
}

// ═══════════════════════════════════════════════════════════════
// WebRTC Session
// ═══════════════════════════════════════════════════════════════

async function startSession() {
  try {
    startSection.style.display = "none";
    sessionSection.classList.add("active");
    stopBtn.style.display = "block";
    setStatus("connecting");

    // Reset cost tracking
    state.sessionCost = 0;
    costToggle.classList.remove("visible", "expanded");

    // Init WebGL orb
    initOrbGL();
    startOrbLoop();

    // Create AudioContext (user gesture required — we're in a click handler)
    const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    if (audioCtx.state === "suspended") {
      await audioCtx.resume();
    }
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    state.audioCtx = audioCtx;
    state.analyser = analyser;
    state.analyserData = new Uint8Array(analyser.frequencyBinCount);

    // Create audio element for remote audio playback.
    const audioEl = document.createElement("audio");
    audioEl.autoplay = true;
    audioEl.style.display = "none";
    document.body.appendChild(audioEl);
    state.audioEl = audioEl;

    // Firefox silences an <audio> element captured by createMediaElementSource
    // when a WebRTC srcObject is assigned (cross-origin restriction). Chrome,
    // conversely, gives silence when using createMediaStreamSource on WebRTC
    // streams. So we pick the strategy that works per engine.
    const isFirefox = /Firefox/i.test(navigator.userAgent);

    if (!isFirefox) {
      // Chrome / Safari: capture audio element → analyser → destination.
      const mediaSource = audioCtx.createMediaElementSource(audioEl);
      mediaSource.connect(analyser);
      analyser.connect(audioCtx.destination);
      state.remoteSource = mediaSource;
    }
    // Firefox path: audio element plays normally; createMediaStreamSource
    // is wired up in pc.ontrack once the remote stream is available.

    console.log("Requesting ephemeral token...");
    const voiceToken = document.querySelector<HTMLMetaElement>('meta[name="voice-token"]')?.content || "";
    const tokenRes = await fetch("/token", {
      headers: { Authorization: "Bearer " + voiceToken },
    });
    if (!tokenRes.ok) throw new Error("Token request failed: " + tokenRes.status);
    const tokenData = await tokenRes.json();
    const ephemeralKey = tokenData.client_secret.value;

    const pc = new RTCPeerConnection();
    state.pc = pc;

    // When remote audio track arrives, attach to audio element.
    pc.ontrack = (ev) => {
      audioEl.srcObject = ev.streams[0];
      // Ensure playback starts (Firefox may block autoplay if user gesture expired)
      audioEl.play().catch(() => { });
      console.log("Remote audio track received");

      // Firefox: wire the WebRTC stream directly to the analyser via
      // createMediaStreamSource. Don't connect to destination — the
      // <audio> element handles audible playback on its own.
      if (isFirefox && state.audioCtx && state.analyser && !state.remoteSource) {
        try {
          const source = state.audioCtx.createMediaStreamSource(ev.streams[0]);
          source.connect(state.analyser);
          state.remoteSource = source;
          console.log("Audio analysis via createMediaStreamSource (Firefox)");
        } catch (e: any) {
          console.error("createMediaStreamSource failed: " + e.message);
        }
      }
    };

    const localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.localStream = localStream;
    localStream.getTracks().forEach((track) => pc.addTrack(track, localStream));

    const dc = pc.createDataChannel("oai-events");
    state.dc = dc;

    dc.onopen = () => {
      console.log("Data channel open, WebRTC connected");
      setStatus("listening");
      resetInactivityTimer();
      // Start max session duration timer
      state.sessionTimer = setTimeout(() => {
        console.log("Max session duration reached — ending session");
        addMessage("system", "Session ended — maximum duration reached.");
        setCaption("Session ended — maximum duration reached.", "system");
        endSession();
      }, MAX_SESSION_DURATION_MS);
      // Prompt the agent to greet the user and explain what it can do
      sendDataChannelMessage({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "system",
          content: [{ type: "input_text", text: "Greet the user warmly. Briefly tell them you can help come up with recipe ideas and manage their grocery cart. Then ask where they're located so you can find the nearest store." }],
        },
      });
      sendDataChannelMessage({ type: "response.create" });
    };

    dc.onclose = () => {
      state.awaitingAudioDrain = false;
      setStatus("disconnected");
    };

    dc.onmessage = (ev) => {
      handleServerEvent(JSON.parse(ev.data));
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpRes = await fetch(REALTIME_URL, {
      method: "POST",
      headers: {
        Authorization: "Bearer " + ephemeralKey,
        "Content-Type": "application/sdp",
      },
      body: pc.localDescription!.sdp,
    });
    if (!sdpRes.ok) throw new Error("SDP exchange failed: " + sdpRes.status);
    console.log("SDP exchange complete");

    const answerSdp = await sdpRes.text();
    await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

    pc.oniceconnectionstatechange = () => {
      if (pc.iceConnectionState === "disconnected" || pc.iceConnectionState === "failed") {
        state.awaitingAudioDrain = false;
        setStatus("disconnected");
      }
    };
  } catch (err: any) {
    console.error("Session start failed: " + err.message);
    addMessage("system", "Error: " + err.message);
    setCaption("Error: " + err.message, "system");
    setStatus("disconnected");
  }
}

function endSession() {
  clearInactivityTimer();
  if (state.sessionTimer) {
    clearTimeout(state.sessionTimer);
    state.sessionTimer = null;
  }
  // Stop mic
  if (state.localStream) {
    state.localStream.getTracks().forEach((t) => t.stop());
    state.localStream = null;
  }
  // Close WebRTC
  if (state.pc) {
    state.pc.close();
    state.pc = null;
  }
  state.dc = null;
  state.awaitingAudioDrain = false;
  // Release audio
  if (state.audioEl) {
    state.audioEl.srcObject = null;
    state.audioEl.remove();
    state.audioEl = null;
  }
  // Disconnect and close audio graph
  if (state.remoteSource) {
    try { state.remoteSource.disconnect(); } catch (_) { }
    state.remoteSource = null;
  }
  if (state.audioCtx) {
    state.audioCtx.close().catch(() => { });
    state.audioCtx = null;
    state.analyser = null;
    state.analyserData = null;
  }

  setStatus("disconnected");
  stopBtn.style.display = "none";
  addMessage("system", "Session ended.");
  setCaption("Session ended.", "system");

  if (state.cart_id) {
    showCartLink();
  }

  // Stop orb after a brief delay so disconnected state renders
  setTimeout(() => {
    stopOrbLoop();
  }, 2000);
}

// ═══════════════════════════════════════════════════════════════
// Server Event Handling
// ═══════════════════════════════════════════════════════════════

let currentMsgEl: HTMLElement | null = null;

function handleServerEvent(event: any) {
  switch (event.type) {
    case "response.audio_transcript.delta":
      clearInactivityTimer();
      setStatus("speaking");
      if (!currentMsgEl) {
        state.currentAssistantMsg = "";
        currentMsgEl = addMessage("assistant", "");
      }
      state.currentAssistantMsg += event.delta;
      currentMsgEl.textContent = state.currentAssistantMsg;
      setCaption(state.currentAssistantMsg, "assistant");
      break;

    case "response.audio_transcript.done":
      if (currentMsgEl) {
        currentMsgEl.textContent = event.transcript;
      }
      currentMsgEl = null;
      state.currentAssistantMsg = "";
      // Don't immediately set listening — wait for audio to actually drain.
      // Caption stays visible until user speaks or a new caption replaces it.
      state.awaitingAudioDrain = true;
      break;

    case "input_audio_buffer.speech_started":
      resetInactivityTimer();
      state.awaitingAudioDrain = false;
      clearCaption();
      break;

    case "conversation.item.input_audio_transcription.completed":
      if (event.transcript) {
        console.log(`User said: "${event.transcript}"`);
        const userEl = document.createElement("div");
        userEl.className = "msg user";
        userEl.textContent = event.transcript;
        if (currentMsgEl && currentMsgEl.parentNode) {
          currentMsgEl.parentNode.insertBefore(userEl, currentMsgEl);
        } else {
          transcript.appendChild(userEl);
        }
        if (!state.hasTranscriptContent) {
          state.hasTranscriptContent = true;
          transcriptToggle.classList.add("visible");
        }
        setCaption(event.transcript, "user");
      }
      break;

    case "response.function_call_arguments.done":
      resetInactivityTimer();
      state.awaitingAudioDrain = false;
      setStatus("thinking");
      handleToolCall(event);
      break;

    case "response.done":
      if (event.response?.output) {
        for (const item of event.response.output) {
          if (item.type === "function_call" && item.status === "completed") {
            // Already handled by function_call_arguments.done
          }
        }
      }
      // Accumulate cost from usage
      if (event.response?.usage) {
        const cost = calculateUsageCost(event.response.usage);
        state.sessionCost += cost;
        updateCostDisplay();
      }
      if (!currentMsgEl && !state.awaitingAudioDrain) {
        setStatus("listening");
        resetInactivityTimer();
      }
      break;

    case "error":
      console.error("Realtime error:", event.error);
      addMessage("system", "Error: " + (event.error?.message || "Unknown error"));
      setCaption("Error: " + (event.error?.message || "Unknown"), "system");
      break;
  }
}

// ═══════════════════════════════════════════════════════════════
// Tool Call Handling
// ═══════════════════════════════════════════════════════════════

async function handleToolCall(event: any) {
  const { name, arguments: argsStr, call_id } = event;
  let args: any;
  try {
    args = JSON.parse(argsStr);
  } catch {
    args = {};
  }

  console.log(`Tool call: ${name}(${argsStr})`);
  const label = name.replace(/_/g, " ");
  addMessage("system", `Looking up: ${label}...`);
  setCaption(`Looking up: ${label}...`, "system");

  // Auto-create cart if a store_id is available but no cart exists yet
  const needsCart = ["search_products", "add_to_cart", "remove_from_cart"].includes(name);
  if (needsCart && !state.cart_id) {
    const storeId = args.store_id || state.store_id;
    const banner = args.banner || state.banner || "superstore";
    if (storeId) {
      try {
        const cartResult = await callBackend("select_store", { store_id: storeId, banner });
        if (cartResult.cart_id) {
          state.cart_id = cartResult.cart_id;
          state.store_id = storeId;
          state.banner = cartResult.banner || banner;
          state.cart_url = cartResult.cart_url || null;
          console.log(`Auto-created cart ${state.cart_id} for store ${storeId}`);
        }
      } catch (err: any) {
        console.error("Failed to auto-create cart:", err);
      }
    }
  }

  let result: any;
  try {
    result = await callBackend(name, args);
  } catch (err: any) {
    result = { error: err.message };
  }

  if (name === "search_products" && result.products) {
    for (const p of result.products) {
      if (p.code && p.name) {
        const displayName = p.brand ? `${p.brand} ${p.name}` : p.name;
        state.productNames[p.code] = displayName;
        if (p.packageSize && p.packageUnit) {
          state.productSizes[p.code] = `${p.packageSize} ${p.packageUnit}`;
        }
      }
    }
  }

  if (name === "add_to_cart" && !result.error) {
    if (result.added_items && result.added_items.length > 0) {
      for (const item of result.added_items) {
        const displayName = state.productNames[item.product_code] || item.name || item.product_code;
        const size = state.productSizes[item.product_code];
        addCartItem(displayName, `x${item.quantity}`, item.product_code, size);
      }
      showCartLink();
    }
  }

  if (name === "remove_from_cart" && !result.error) {
    if (result.removed_items && result.removed_items.length > 0) {
      for (const item of result.removed_items) {
        removeCartItem(item.product_code);
      }
    }
  }

  if (name === "finish_shopping") {
    if (result.cart_url) {
      const a = document.getElementById("cart-link-a") as HTMLAnchorElement;
      a.href = result.cart_url;
    }
    showCartLink();
    addMessage("system", "Shopping complete! Review your cart.");
    setCaption("Shopping complete!", "system");
    // Auto-end the session for off-topic shutdowns; normal finishes stay open
    // so the user can review their cart link at their own pace.
    if (args.reason === "off_topic") {
      setTimeout(() => {
        endSession();
      }, 4000);
    }
  }

  // Strip cart_url so the voice agent never sees raw URLs to read aloud.
  // The frontend already captured cart_url for UI use above.
  const sanitizedResult = { ...result };
  delete sanitizedResult.cart_url;

  sendDataChannelMessage({
    type: "conversation.item.create",
    item: {
      type: "function_call_output",
      call_id,
      output: JSON.stringify(sanitizedResult),
    },
  });
  sendDataChannelMessage({
    type: "response.create",
  });
}

// ═══════════════════════════════════════════════════════════════
// Backend API
// ═══════════════════════════════════════════════════════════════

async function callBackend(fnName: string, args: any): Promise<any> {
  const endpointMap: Record<string, string> = {
    find_nearest_stores: "/api/find-stores",
    select_store: "/api/create-cart",
    search_products: "/api/search-products",
    add_to_cart: "/api/add-to-cart",
    remove_from_cart: "/api/remove-from-cart",
    finish_shopping: "/api/finish-shopping",
  };
  const endpoint = endpointMap[fnName];
  if (!endpoint) {
    return { error: "Unknown function: " + fnName };
  }
  const body: any = { ...args };
  if (state.cart_id && !body.cart_id) body.cart_id = state.cart_id;
  if (state.store_id && !body.store_id) body.store_id = state.store_id;
  if (state.banner && !body.banner) body.banner = state.banner;

  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error("API error " + res.status + ": " + text);
  }
  return res.json();
}

function sendDataChannelMessage(msg: any) {
  if (state.dc && state.dc.readyState === "open") {
    state.dc.send(JSON.stringify(msg));
  } else {
    console.warn("Data channel not open, cannot send:", msg);
  }
}
