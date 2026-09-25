import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TutorBoard from "./TutorBoard.jsx";
import MenuBar from "./os/MenuBar.jsx";
import Widgets from "./os/Widgets.jsx";
import ProgressWidget from "./os/ProgressWidget.jsx";
import CodeApp from "./os/CodeApp.jsx";
import HelpApp from "./os/HelpApp.jsx";
import BrowserApp from "./os/BrowserApp.jsx";
import NotesApp from "./os/NotesApp.jsx";
import TutorApp from "./os/TutorApp.jsx";
import NotchHUD from "./os/NotchHUD.jsx";
import AppWindow from "./os/AppWindow.jsx";
import ErrorBoundary from "./os/ErrorBoundary.jsx";
import { engine } from "./audioEngine.js";
import { chatMessage, pingMessage, stopMessage } from "./services/ttsProtocol.js";
import { STUDENT, COURSE, COURSES, INITIAL_PROGRESS, getLessonById, getCourseById } from "./data/courseData.js";

const GREETING = "नमस्ते! मैं आपका हिंदी ट्यूटर हूँ। माइक दबाकर बोलिए, लिखकर पूछिए — और स्क्रीन दिखाने के लिए X दबाकर रखें, बोलते रहिए, छोड़ते ही मैं स्क्रीन देखकर जवाब दूँगा। जब मैं बोलूँ तो बीच में कुछ भी बोलिए, मैं तुरंत रुक जाऊँगा।";
const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/tts`;
const ASR_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/asr`;
const CONFIG_URL = `${location.protocol}//${location.host}/api/config`;
const VISION_URL = `${location.protocol}//${location.host}/api/vision`;

/* Live tunables, fetched once from the backend /api/config (which reads them
   from .env). Everything here mirrors an env var server-side, so tuning
   happens in .env — never by editing this file. Defaults below match the
   current behaviour and apply until the fetch resolves. */
const CFG = {
  chatStep: 8, // nfe_step the UI sends for chat replies
  jitterFrames: 1, // start after one TTS frame; raise via VOICE_JITTER_FRAMES if slower hardware underruns
  maxHistory: 8,
  wsReconnectMs: 1500,
  recRestartMs: 400,
  vadTickMs: 50,
  autoSendMs: 750, // end-of-speech silence tail; <500ms chops speech into fragments that each fire a reply
  specChat: true, // server sends a fast "speculative" transcript; reply starts on it, final reconciles
  sendMinChars: 2, // min non-space chars to treat as real words
  vadNoiseFloor: 0.005,
  vadThresholdMin: 0.014,
  vadGateMult: 3.4, // voice gate = noise * this (or threshold_min, whichever is higher)
  vadSustainMs: 250, // energy this long = real voice (barge / arm send)
  vadTextMs: 150, // …or recognizer words + this much energy confirm
  vadFailsafeMs: 650, // 650ms sustained energy barge-in trigger (prevents echo/noise cutting the assistant)
  speakTailMs: 700, // ignore recognition this long after OUR speaker audio stops (echo)
  vadRecActiveMs: 400, // recognizer counts as active within this window
  asrVadMode: "auto", // "server" = Silero VAD on the server owns turn-taking (noise-proof)
  bargeIdleMs: 900, // recognizer-idle safety-net send delay
  visionEnabled: false, // server has a vision engine ready (screen understanding)
  pushMode: true, // push-to-see: hold the button, auto-send on release (SCREEN_PUSH_MODE)
  pushMaxMs: 5000, // hold longer than this -> auto-send anyway
  pushTickMs: 400, // capture cadence DURING the hold (each changed frame warms the VLM)
};
const num = (v, d) => (v === undefined || v === null || Number.isNaN(Number(v)) ? d : Number(v));
const mergeCfg = (c) => {
  if (!c) return;
  CFG.chatStep = num(c.chat_step, CFG.chatStep);
  CFG.jitterFrames = Math.max(0, Math.round(num(c.jitter_frames, CFG.jitterFrames)));
  CFG.maxHistory = num(c.max_history, CFG.maxHistory);
  CFG.wsReconnectMs = num(c.ws_reconnect_ms, CFG.wsReconnectMs);
  CFG.recRestartMs = num(c.rec_restart_ms, CFG.recRestartMs);
  CFG.vadTickMs = num(c.vad_tick_ms, CFG.vadTickMs);
  CFG.autoSendMs = num(c.auto_send_ms, CFG.autoSendMs);
  CFG.sendMinChars = num(c.send_min_chars, CFG.sendMinChars);
  CFG.vadNoiseFloor = num(c.vad_noise_floor, CFG.vadNoiseFloor);
  CFG.vadThresholdMin = num(c.vad_threshold_min, CFG.vadThresholdMin);
  CFG.vadGateMult = num(c.vad_gate_mult, CFG.vadGateMult);
  CFG.vadSustainMs = num(c.vad_sustain_ms, CFG.vadSustainMs);
  CFG.vadTextMs = num(c.vad_text_ms, CFG.vadTextMs);
  CFG.vadFailsafeMs = num(c.vad_failsafe_ms, CFG.vadFailsafeMs);
  CFG.speakTailMs = num(c.speak_tail_ms, CFG.speakTailMs);
  CFG.vadRecActiveMs = num(c.vad_rec_active_ms, CFG.vadRecActiveMs);
  CFG.asrVadMode = c.asr_vad_mode || CFG.asrVadMode;
  CFG.bargeIdleMs = num(c.barge_idle_ms, CFG.bargeIdleMs);
  CFG.specChat = c.spec_chat !== undefined ? !!c.spec_chat : CFG.specChat; // live tunable
  CFG.visionEnabled = c.vision_enabled !== undefined ? !!c.vision_enabled : CFG.visionEnabled;
  CFG.pushMode = c.screen_push_mode !== undefined ? !!c.screen_push_mode : CFG.pushMode;
  CFG.pushMaxMs = num(c.screen_push_max_ms, CFG.pushMaxMs);
  CFG.pushTickMs = num(c.screen_push_tick_ms, CFG.pushTickMs);
};
if (typeof fetch === "function") {
  fetch(CONFIG_URL)
    .then((r) => (r.ok ? r.json() : null))
    .then(mergeCfg)
    .catch(() => {});
}

let msgId = 0;
const nextId = () => ++msgId;

/* Agent OS control allowlists (mirror server/llm/os_control.py — the client
   re-validates every os_action before executing it). */
const AGENT_APPS = ["whiteboard", "browser", "notes", "code", "help", "tutor"];
const AGENT_ZONES = ["left", "right", "tl", "tr", "bl", "br"];
const AGENT_APP_LABEL = { whiteboard: "Green Board", browser: "Browser", notes: "Notes", code: "Code", help: "Help Center", tutor: "Tutor" };
const AGENT_ZONE_LABEL = {
  left: "left half", right: "right half",
  tl: "top-left", tr: "top-right", bl: "bottom-left", br: "bottom-right",
};

export default function App() {
  const [messages, setMessages] = useState([{ id: nextId(), role: "assistant", text: GREETING }]);
  // ---- Boot splash: smooth OS-style loading with logo + staged app init ----
  const BOOT_STAGES = useMemo(() => [
    { label: "Starting Bug OS", apps: [] },
    { label: "Loading Tutor", apps: ["tutor"] },
    { label: "Preparing Green Board + Browser", apps: ["tutor", "whiteboard", "browser"] },
    { label: "Warming voice engine", apps: ["tutor", "whiteboard", "browser", "code", "notes"] },
    { label: "Ready", apps: ["tutor", "whiteboard", "browser", "code", "notes"] },
  ], []);
  const [bootStage, setBootStage] = useState(0);
  const [booting, setBooting] = useState(true);
  const [bootGone, setBootGone] = useState(false);
  useEffect(() => {
    const timers = [];
    BOOT_STAGES.forEach((_, i) => {
      if (i === 0) return;
      timers.push(setTimeout(() => setBootStage(i), i * 450));
    });
    timers.push(setTimeout(() => setBooting(false), BOOT_STAGES.length * 450 + 250));
    timers.push(setTimeout(() => setBootGone(true), BOOT_STAGES.length * 450 + 800));
    return () => timers.forEach(clearTimeout);
  }, [BOOT_STAGES]);
  const [connected, setConnected] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [userTalking, setUserTalking] = useState(false);
  const [interim, setInterim] = useState("");
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [turnActive, setTurnActive] = useState(false); // a reply is owed/playing: steady "Speaking" label
  const [sharing, setSharing] = useState(false); // push-to-see capture active (button held)
  const [diagram, setDiagram] = useState(null);
  // Fresh board per explanation: first visuals of a new turn wipe the board
  // with a smooth fade (never draw over the old lesson).
  const [wiping, setWiping] = useState(false);
  const wipingRef = useRef(false); // wipe animation in flight (merge guard)
  const heldDuringWipeRef = useRef([]); // new chalk that arrived mid-wipe
  const wipeTimerRef = useRef(0);
  const wipedClientTurnRef = useRef(0); // client turn already wiped for
  const diagramRef = useRef(null); // mirror of `diagram` for stale closures
  useEffect(() => { diagramRef.current = diagram; }, [diagram]);
  // ---- LLM provider: groq | deepseek (per-turn toggle, persisted) ----
  const [llmProvider, setLlmProvider] = useState(() => {
    try {
      const saved = localStorage.getItem("bugos-llm-provider");
      return saved === "deepseek" || saved === "groq" ? saved : "groq";
    } catch {
      return "groq";
    }
  });
  const [llmProviders, setLlmProviders] = useState(["groq"]);
  const [llmModels, setLlmModels] = useState({});
  const llmProviderRef = useRef(llmProvider);
  useEffect(() => {
    llmProviderRef.current = llmProvider;
    try {
      localStorage.setItem("bugos-llm-provider", llmProvider);
    } catch { /* private mode */ }
  }, [llmProvider]);
  // Learn the server's available providers once (which API keys exist).
  useEffect(() => {
    fetch(CONFIG_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then((c) => {
        if (!c) return;
        if (Array.isArray(c.llm_providers) && c.llm_providers.length) {
          setLlmProviders(c.llm_providers);
        }
        if (c.llm_models && typeof c.llm_models === "object") setLlmModels(c.llm_models);
        const dflt = c.llm_provider;
        try {
          const saved = localStorage.getItem("bugos-llm-provider");
          if (saved && c.llm_providers?.includes(saved)) return; // keep user's choice
        } catch { /* ignore */ }
        if (dflt === "deepseek" || dflt === "groq") setLlmProvider(dflt);
      })
      .catch(() => {});
  }, []);
  // ---- Bug OS window manager: tutor lives in the notch (background agent);
  // it pops Whiteboard/Browser/Notes/Code as it teaches. Last = front. ----
  // Tutor opens on boot so courses are discoverable (dock still toggles it).
  const [openApps, setOpenApps] = useState(["tutor"]);
  const [minApps, setMinApps] = useState({});
  const [maxed, setMaxed] = useState({});
  // Split-screen tiles: id -> "left" | "right" | "tl" | "tr" | "bl" | "br".
  // Max 4 snapped windows (2x2 square grid). A snapped window is always
  // un-maximized and un-minimized; dragging it floats it again.
  const [snaps, setSnaps] = useState({});
  const snapsRef = useRef({});
  useEffect(() => { snapsRef.current = snaps; }, [snaps]);
  // Per-app window geometry. Only the agent writes it (see execOsAction);
  // null = the frame falls back to its centered default.
  const [winGeom, setWinGeom] = useState({});
  // Exit animations: a closing/minimizing window plays its shrink-out
  // first (180ms), then actually leaves. Reopening mid-exit cancels it.
  // Declared before visibleApps — render reads it on every pass.
  const [leaving, setLeaving] = useState({});
  const leaveTimers = useRef({});
  useEffect(
    () => () => {
      Object.values(leaveTimers.current).forEach(clearTimeout);
    },
    [],
  );
  const cancelLeave = (id) => {
    if (leaveTimers.current[id]) {
      clearTimeout(leaveTimers.current[id]);
      delete leaveTimers.current[id];
    }
    setLeaving((p) => {
      if (!p[id]) return p;
      const n = { ...p };
      delete n[id];
      return n;
    });
  };
  // EDGE-CASE FIX 1 — stable active window during exit animations.
  // `leaving` windows still render (shrink-out) for 180ms. The old code
  // excluded them from `visibleApps`, so `activeApp` flipped to the window
  // below the instant close/minimize started: MenuBar relabeled mid-flight,
  // the container's fullscreen padding toggled early, and z-order fought the
  // exit animation. Now the leaving window stays active (and on top) until
  // its timer actually removes/minimizes it.
  const navigatingApps = openApps.filter((id) => !minApps[id]); // includes leaving
  const visibleApps = navigatingApps.filter((id) => !leaving[id]);
  const activeApp = navigatingApps.length ? navigatingApps[navigatingApps.length - 1] : null;
  // EDGE-CASE FIX 2 — z-order follows the visible stack so minimized
  // windows never leave stacking gaps; the leaving window pins to the top.
  const zFor = (id) => {
    if (leaving[id]) return 10 + openApps.length + 5;
    const i = visibleApps.indexOf(id);
    return i === -1 ? 10 + openApps.indexOf(id) : 10 + i;
  };
  // ---- split-screen helpers (max 4 tiled windows) ----
  const doSnap = (id, zone) => {
    if (!id || !zone) return false;
    const cur = snapsRef.current;
    // Re-tiling an already-snapped window never counts against the cap.
    if (!cur[id]) {
      const n = Object.keys(cur).filter(
        (k) => cur[k] && openApps.includes(k) && !minApps[k],
      ).length;
      if (n >= 4) return false; // square is full — reject the 5th tile
    }
    cancelLeave(id);
    setMinApps((p) => (p[id] ? { ...p, [id]: false } : p));
    setMaxed((p) => (p[id] ? { ...p, [id]: false } : p)); // tiles are never maximized
    setSnaps((p) => ({ ...p, [id]: zone }));
    focusApp(id);
    return true;
  };
  const unsnap = (id, geom) => {
    setSnaps((p) => {
      if (!p[id]) return p;
      const n = { ...p };
      delete n[id];
      return n;
    });
    // A dragged tile keeps its on-screen pixel rect as its floating geom so
    // the window doesn't jump back to a stale position mid-gesture.
    if (geom) setWinGeom((p) => ({ ...p, [id]: geom }));
  };
  // Auto-arrange up to 4 visible windows into the square grid:
  // 1 -> fullscreen, 2 -> halves, 3 -> half + 2 quarters, 4 -> 2x2.
  const tileGrid = () => {
    const wins = visibleApps.slice(0, 4);
    if (!wins.length) return;
    let zones = [];
    if (wins.length === 1) zones = ["left", "right"]; // placeholder, normalized below
    else if (wins.length === 2) zones = ["left", "right"];
    else if (wins.length === 3) zones = ["left", "tr", "br"];
    else zones = ["tl", "tr", "bl", "br"];
    if (wins.length === 1) {
      // Single window: true fullscreen beats a lonely half tile.
      const id = wins[0];
      cancelLeave(id);
      setSnaps((p) => {
        if (!p[id]) return p;
        const n = { ...p };
        delete n[id];
        return n;
      });
      setMinApps((p) => (p[id] ? { ...p, [id]: false } : p));
      setMaxed((p) => ({ ...p, [id]: true }));
      focusApp(id);
      return;
    }
    const next = {};
    wins.forEach((id, i) => {
      cancelLeave(id);
      next[id] = zones[i];
    });
    setMinApps((p) => {
      const n = { ...p };
      wins.forEach((id) => { delete n[id]; });
      return n;
    });
    setMaxed((p) => {
      const n = { ...p };
      wins.forEach((id) => { delete n[id]; });
      return n;
    });
    setSnaps((p) => ({ ...p, ...next }));
    focusApp(wins[wins.length - 1]);
  };
  const maximized = !!(activeApp && maxed[activeApp]);
  const geomFor = (id) => winGeom[id] || null;
  // Fullscreen chrome: hidden until the pointer hits the top edge.
  const [topChrome, setTopChrome] = useState(false);
  const [browserUrl, setBrowserUrl] = useState("https://www.google.com/webhp?igu=1");
  const [browserTabs, setBrowserTabs] = useState(1);
  // Imperative browser moves from the agent: an ORDERED queue ([{cmd, target,
  // seq}]) drained by BrowserApp. A single object used to collapse when the
  // director emitted 2+ moves in one turn (same-ms tick) — new tab opened,
  // navigate never ran. Monotonic seqs => every move executes exactly once.
  const [browserQueue, setBrowserQueue] = useState([]);
  const browserSeq = useRef(0);
  const agentBrowser = (cmd, target) =>
    setBrowserQueue((q) => [...q.slice(-11), { cmd, ...(target !== undefined ? { target } : {}), seq: ++browserSeq.current }]);
  const ackBrowser = useCallback((seq) => {
    setBrowserQueue((q) => (q.some((c) => c.seq === seq) ? q.filter((c) => c.seq !== seq) : q));
  }, []);
  // Imperative code moves from the agent ([{cmd, path, content, mode, find,
  // replace, seq}]) drained by CodeApp — same ordered-queue pattern as the
  // browser so 2+ moves in one turn never collapse into one.
  const [codeQueue, setCodeQueue] = useState([]);
  const codeSeq = useRef(0);
  const agentCode = (cmd, a) =>
    setCodeQueue((q) => [...q.slice(-11), {
      cmd,
      ...(a.path !== undefined ? { path: a.path } : {}),
      ...(a.content !== undefined ? { content: a.content } : {}),
      ...(a.mode !== undefined ? { mode: a.mode } : {}),
      ...(a.find !== undefined ? { find: a.find } : {}),
      ...(a.replace !== undefined ? { replace: a.replace } : {}),
      seq: ++codeSeq.current,
    }]);
  const ackCode = useCallback((seq) => {
    setCodeQueue((q) => (q.some((c) => c.seq === seq) ? q.filter((c) => c.seq !== seq) : q));
  }, []);
  const onBrowserNavigate = useCallback((u, meta) => {
    setBrowserUrl(u);
    if (meta && typeof meta.tabs === "number") setBrowserTabs(meta.tabs);
  }, []);
  // Transient "agent did X" pill (also briefly reveals the dock).
  const [agentFlash, setAgentFlash] = useState(null);
  const [notes, setNotes] = useState(() => {
    try {
      const next = JSON.parse(localStorage.getItem("bugos-notes") || "null");
      if (Array.isArray(next)) return next;
      const legacy = JSON.parse(localStorage.getItem("saathi-notes") || "[]");
      return Array.isArray(legacy) ? legacy : [];
    } catch {
      return [];
    }
  });
  const [activeNoteId, setActiveNoteId] = useState(null);
  // ---- Course progress (was hardcoded INITIAL_PROGRESS): the learner browses
  // course -> module -> lesson in the Tutor app; the active lesson is context
  // for the tutor, which teaches it by voice when asked. Persisted locally. ----
  const [activeCourseId] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("bugos-course") || "null");
      if (saved?.courseId && getCourseById(saved.courseId)) return saved.courseId;
    } catch { /* fresh */ }
    return INITIAL_PROGRESS.courseId || COURSE.id;
  });
  const [activeLessonId, setActiveLessonId] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("bugos-course") || "null");
      if (saved?.activeLessonId && getLessonById(saved.activeLessonId, getCourseById(saved.courseId) || COURSE)) return saved.activeLessonId;
    } catch { /* fresh */ }
    return INITIAL_PROGRESS.activeLessonId;
  });
  const [completedLessonIds, setCompletedLessonIds] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("bugos-course") || "null");
      if (Array.isArray(saved?.completed)) return saved.completed;
    } catch { /* fresh */ }
    return INITIAL_PROGRESS.completedLessonIds || [];
  });
  const [selectedLesson, setSelectedLesson] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("bugos-course") || "null");
      if (saved?.selected) return saved.selected;
    } catch { /* fresh */ }
    // Default preview = current active lesson (html-3) so Start is one click.
    for (const c of COURSES) for (const m of c.modules || []) {
      if ((m.lessons || []).some((l) => l.id === INITIAL_PROGRESS.activeLessonId)) {
        return { courseId: c.id, moduleId: m.id, lessonId: INITIAL_PROGRESS.activeLessonId };
      }
    }
    return null;
  });
  useEffect(() => {
    try {
      localStorage.setItem("bugos-course", JSON.stringify({
        courseId: activeCourseId, activeLessonId, completed: completedLessonIds, selected: selectedLesson,
      }));
    } catch { /* private mode */ }
  }, [activeCourseId, activeLessonId, completedLessonIds, selectedLesson]);
  const courseProgress = useMemo(() => ({
    courseId: activeCourseId,
    completedLessonIds,
    activeLessonId,
    scores: INITIAL_PROGRESS.scores || {},
  }), [activeCourseId, completedLessonIds, activeLessonId]);
  // Learning activity per local day, powers the desktop progress graph.
  const [dayStats, setDayStats] = useState(() => {
    try {
      const v = JSON.parse(localStorage.getItem("bugos-stats") || "{}");
      return v && typeof v === "object" ? v : {};
    } catch {
      return {};
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("bugos-stats", JSON.stringify(dayStats));
    } catch { /* private mode — stats stay in memory */ }
  }, [dayStats]);
  const recordQuestion = () => {
    const d = new Date();
    const key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    setDayStats((prev) => ({ ...prev, [key]: { q: (prev[key]?.q || 0) + 1 } }));
  };
  const [clock, setClock] = useState("");
  const [dateStr, setDateStr] = useState("");
  // Reopening a leaving window cancels its exit (see cancelLeave above).
  const focusApp = (id) => {
    cancelLeave(id);
    setOpenApps((prev) => (prev.includes(id) ? [...prev.filter((x) => x !== id), id] : [...prev, id]));
    setMinApps((p) => (p[id] ? { ...p, [id]: false } : p));
  };
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      setDateStr(now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }));
    };
    tick();
    const t = setInterval(tick, 15000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("bugos-notes", JSON.stringify(notes));
    } catch { /* private mode — notes stay in memory */ }
  }, [notes]);

  // ---- mutable runtime state (safe across renders) ----
  const wsRef = useRef(null);
  const apiRef = useRef({});
  const historyRef = useRef([]);
  const pendingRef = useRef([]);
  const currentSourceRef = useRef(null);
  const speakingRef = useRef(false);
  const dropRef = useRef(false);
  const drainRestartRef = useRef(false); // queue underran mid-reply — next frame starts playback at once
  const drainStartedRef = useRef(false); // drain() already kicked for the current turn (start-event opens speaking early)
  const activeRef = useRef(false); // a reply is being streamed from the server
  const framesRef = useRef(0);
  const turnStartRef = useRef(0); // browser-side: when the current turn was submitted (first-audio stopwatch)
  const activeTurnIdRef = useRef(0);
  const acceptedOsTurnRef = useRef(null); // turn id whose pre-start agent moves are valid
  const diagramTurnRef = useRef(null);
  const diagramQueueRef = useRef([]); // staged board deltas for smooth step-by-step draw
  const diagramTimerRef = useRef(0);
  // Audio-synced board: server numbers every TTS window (m.type==="window" n),
  // audio blobs arrive in the same WS order, and diagram deltas carry window_n.
  // We stage deltas keyed by window and flush them only when that window's
  // audio STARTS playing — so the viewport always shows the step being spoken.
  const windowOrderRef = useRef([]); // window numbers in arrival order (pairs with audio blobs)
  const audioWindowRef = useRef([]); // window n aligned 1:1 with pendingRef blobs
  const stagedDiagramsRef = useRef(new Map()); // window_n -> elements[]
  const currentWindowRef = useRef(0); // audio window currently playing
  const [diagramFocus, setDiagramFocus] = useState(null); // {ids:[...], tick:n} -> whiteboard scrolls here
  const revealQueueRef = useRef([]); // single elements awaiting paced draw
  const revealTimerRef = useRef(0);
  // Chalk pace: one shape per short beat so the board grows WITH the speech
  // (one audio window ≈ 1.5-3s holds 2-4 shapes). Must stay well under the
  // spoken duration or the board lags behind the voice.
  const REVEAL_MS = 750;

  /* Merge one staged board batch into state (id-keyed, capped).
     Fresh board per explanation: the first visuals of a new turn wipe the
     board first (see maybeWipeBoardForNewVisuals) so the new lesson never
     draws OVER the old one — and recycled window ids (w1-…) can't collide. */
  const mergeDiagramBatch = useCallback((incoming) => {
    if (wipingRef.current) {
      // Wipe in flight: hold the new chalk until the board is clean, then
      // it lands on the fresh board in order (flushed by the wipe timer).
      heldDuringWipeRef.current.push(...(incoming || []).filter(Boolean));
      return;
    }    setDiagram((prev) => {
      const seen = new Set();
      const merged = [];
      for (const el of [...(prev?.elements || []), ...incoming]) {
        if (!el || !el.id || seen.has(el.id)) continue;
        seen.add(el.id);
        merged.push(el);
      }
      return { elements: merged.slice(-500) };
    });
  }, []);

  // Lesson timeline: flat board elements grouped into steps by window tag
  // (w{N}-... ids). Drives back/forward navigation in TutorBoard.
  const stepOf = (el) => {
    const m = /^w(\d+)-/i.exec(String(el?.id || ""));
    return m ? `w${Number(m[1])}` : "w0";
  };
  const steps = useMemo(() => {
    const map = new Map();
    for (const el of diagram?.elements || []) {
      const key = stepOf(el);
      if (!map.has(key)) map.set(key, { key, elements: [] });
      map.get(key).elements.push(el);
    }
    return [...map.values()].sort((a, b) =>
      Number(a.key.slice(1)) - Number(b.key.slice(1)));
  }, [diagram]);
  const [stepIndex, setStepIndex] = useState(0);
  const [followLive, setFollowLive] = useState(true);
  useEffect(() => {
    if (followLive && steps.length) setStepIndex(steps.length - 1);
  }, [steps.length, followLive]);

  // Fresh board per explanation: the first visuals of a new turn wipe the
  // old lesson with a smooth fade instead of drawing OVER it. At most once
  // per client turn; a no-op when the board is already empty. New chalk that
  // lands mid-wipe is held (see mergeDiagramBatch) and drawn right after.
  // Plain closure like matchWaiting (refs + stable setters — safe from the
  // long-lived WS handler).
  const maybeWipeBoardForNewVisuals = () => {
    const turn = activeTurnIdRef.current;
    if (wipedClientTurnRef.current === turn || wipingRef.current) return;
    wipedClientTurnRef.current = turn;
    if (!diagramRef.current?.elements?.length) return;
    wipingRef.current = true;
    setWiping(true);
    if (wipeTimerRef.current) clearTimeout(wipeTimerRef.current);
    wipeTimerRef.current = setTimeout(() => {
      wipeTimerRef.current = 0;
      const held = heldDuringWipeRef.current;
      heldDuringWipeRef.current = [];
      const seen = new Set();
      const merged = [];
      for (const el of held) {
        if (!el || !el.id || seen.has(el.id)) continue;
        seen.add(el.id);
        merged.push(el);
      }
      setDiagram(merged.length ? { elements: merged.slice(-500) } : null);
      setStepIndex(0);
      setFollowLive(true);
      setDiagramFocus(null);
      wipingRef.current = false;
      setWiping(false);
    }, 300);
  };

  // Trigger-gated elements: drawn the instant their trigger word is spoken.
  // Bilingual: server sends trigger (English, matches code/raw) + trigger_hi
  // (Devanagari spoken form, matches the live Hindi caption). Either hit
  // draws now; 4s deadline backstop so a missed trigger never strands content
  // far behind the voice (board must track speech, not trail it).
  const waitingRef = useRef([]); // [{el, stagedAt}]
  const normCaption = (s) => (s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ");
  // Whiteboard entrance: the board must NEVER pop before the tutor speaks.
  // Diagram deltas only STAGE content (audio-synced to the spoken windows);
  // this fronts the Whiteboard the moment the turn's audio starts playing —
  // canvas arrives WITH speech, never first. Plain closure like matchWaiting
  // (refs + stable setters only — safe from the long-lived WS handler).
  // Plain per-render closure (refs + stable setters only — no staleness),
  // callable from stable callbacks and the WS handler without dep churn.
  // force=true (turn done): draw everything regardless of trigger match —
  // a missed trigger must never strand a step as a blank page.
  const matchWaiting = (force = false) => {
    if (!waitingRef.current.length) return;
    // Match triggers against FRESH speech only (last ~160 chars ≈ one spoken
    // sentence). The old cumulative match fired on words spoken long ago, so
    // whole steps popped at once instead of one-by-one with the voice.
    const rawCap = (assistantTextRef.current || "").slice(-160);
    const cap = normCaption(rawCap);
    const now = Date.now();
    // Speech-progress release: if the paced queue already drained, the voice
    // has moved past these elements — release aged waits (>1.2s) in staged
    // order so the board tracks speech instead of dumping late.
    const queueEmpty = revealQueueRef.current.length === 0;
    const ready = [];
    waitingRef.current = waitingRef.current.filter((w) => {
      const t = (w.el?.trigger || "").toLowerCase().trim();
      const th = (w.el?.trigger_hi || "").trim();
      const hitEn = t && cap && cap.includes(t);
      const hitHi = th && rawCap && rawCap.includes(th);
      const age = now - w.stagedAt;
      if (force || !t && !th || hitEn || hitHi || age > 4000 || (queueEmpty && age > 1200)) {
        ready.push(w.el);
        return false;
      }
      return true;
    });
    if (ready.length) {
      revealQueueRef.current.push(...ready);
      if (!revealTimerRef.current) revealNext();
    }
    // Backstop: items still waiting have a future 1.2s speech-progress
    // release but no timer is running to enforce it — schedule a sweep.
    if (waitingRef.current.length && !revealTimerRef.current) {
      const oldest = Math.min(...waitingRef.current.map((w) => w.stagedAt));
      const delay = Math.max(300, Math.min(1200 - (Date.now() - oldest), 1200));
      revealTimerRef.current = setTimeout(revealNext, delay);
    }
  };

  // Whiteboard entrance: the board must NEVER pop before the tutor speaks.
  // Diagram deltas only STAGE content (audio-synced to the spoken windows);
  // this fronts the Whiteboard the moment the turn's audio starts playing —
  // canvas arrives WITH speech, never first. Plain closure like matchWaiting
  // (refs + stable setters only — safe from the long-lived WS handler).
  const pendingBoardRef = useRef(null); // turn_id whose visuals are staged but not yet shown
  const frontBoardIfReady = (force = false) => {
    if (!pendingBoardRef.current) return;
    const hasVisuals =
      revealQueueRef.current.length > 0 ||
      waitingRef.current.length > 0 ||
      stagedDiagramsRef.current.size > 0;
    if (!hasVisuals) return;
    const audioStarted = speakingRef.current || currentWindowRef.current > 0;
    if (!force && !audioStarted) return; // speech hasn't begun — keep staging
    pendingBoardRef.current = null;
    // Canvas always opens FULLSCREEN, centered.
    // Split-screen respect: an agent-tiled whiteboard stays tiled (just focus
    // it); only an untiled board is yanked to fullscreen with the speech.
    if (!snapsRef.current.whiteboard) {
      setMaxed((p) => ({ ...p, whiteboard: true }));
    }
    setOpenApps((prev) =>
      prev.includes("whiteboard")
        ? [...prev.filter((x) => x !== "whiteboard"), "whiteboard"]
        : [...prev, "whiteboard"],
    );
    setMinApps((p) => (p.whiteboard ? { ...p, whiteboard: false } : p));
    setFollowLive(true);
  };

  /* Paced reveal: draw ONE shape per beat so the board grows smoothly with
     the speech instead of popping a whole batch instantly. Each shape gets
     viewport focus as it appears. Backlog (>12) catches up at a fast beat —
     still stepwise, never an instant dump. */
  const revealNext = useCallback(() => {
    // Sweep expired trigger-waits first (deadline backstop: 4s).
    if (waitingRef.current.length) {
      const now = Date.now();
      const due = [];
      waitingRef.current = waitingRef.current.filter((w) => {
        if (now - w.stagedAt > 4000) { due.push(w.el); return false; }
        return true;
      });
      if (due.length) revealQueueRef.current.push(...due);
    }
    const el = revealQueueRef.current.shift();
    if (!el) {
      // Queue drained but trigger-waits remain: speech has moved past them —
      // release aged waits (>1.2s) in order so the board tracks the voice
      // instead of stranding as a blank page or dumping late.
      if (waitingRef.current.length) {
        const now = Date.now();
        const due = [];
        waitingRef.current = waitingRef.current.filter((w) => {
          if (now - w.stagedAt > 1200) { due.push(w.el); return false; }
          return true;
        });
        if (due.length) {
          revealQueueRef.current.push(...due);
          revealTimerRef.current = setTimeout(revealNext, REVEAL_MS);
        } else {
          const oldest = Math.min(...waitingRef.current.map((w) => w.stagedAt));
          const delay = Math.max(300, Math.min(1200 - (Date.now() - oldest), 1200));
          revealTimerRef.current = setTimeout(revealNext, delay);
        }
      } else {
        revealTimerRef.current = 0;
      }
      return;
    }
    mergeDiagramBatch([el]);
    if (el?.id) setDiagramFocus({ ids: [el.id], tick: Date.now() });
    if (revealQueueRef.current.length > 12) {
      // Long turn, reveal far behind speech — catch up at a readable beat,
      // still one shape at a time (never an instant wall of content).
      revealTimerRef.current = setTimeout(revealNext, 700);
      return;
    }
    if (revealQueueRef.current.length) {
      revealTimerRef.current = setTimeout(revealNext, REVEAL_MS);
    } else {
      revealTimerRef.current = 0;
    }
  }, [mergeDiagramBatch]);

  /* Flush staged deltas whose audio window has started playing.
     Trigger-bearing elements wait for their spoken word (matchWaiting);
     the rest join the paced reveal queue in window order.
     force=true (reply done): bypass trigger gating — draw everything now. */
  const flushDiagramsUpTo = useCallback((n, force = false) => {
    const staged = stagedDiagramsRef.current;
    if (force) {
      // Turn over: nothing more will be spoken, so triggers can never hit.
      // Drain staged + waiting straight into the reveal queue.
      const all = [];
      for (const k of [...staged.keys()].sort((a, b) => a - b)) {
        const batch = staged.get(k);
        staged.delete(k);
        if (batch?.length) all.push(...batch);
      }
      if (waitingRef.current.length) {
        all.push(...waitingRef.current.map((w) => w.el));
        waitingRef.current = [];
      }
      if (all.length) {
        revealQueueRef.current.push(...all);
        if (!revealTimerRef.current) revealNext();
      }
      return;
    }
    if (!staged.size) {
      // No new deltas, but waiting triggers may have hit their deadline —
      // still run the backstop so steps can't strand as a blank page.
      matchWaiting();
      return;
    }
    const keys = [...staged.keys()].filter((k) => k <= n).sort((a, b) => a - b);
    const now = Date.now();
    for (const k of keys) {
      const batch = staged.get(k);
      staged.delete(k);
      if (!batch?.length) continue;
      for (const el of batch) {
        if (el?.trigger || el?.trigger_hi) waitingRef.current.push({ el, stagedAt: now });
        else revealQueueRef.current.push(el);
      }
    }
    matchWaiting();
    if (revealQueueRef.current.length && !revealTimerRef.current) revealNext();
  }, [revealNext]);

  /* Staggered drain: one board batch per beat so steps draw one-by-one
     instead of dumping all divs at once. (Legacy whole-board path only —
     window deltas now go through stagedDiagramsRef for audio sync.) */
  const drainDiagramQueue = useCallback(() => {
    const batch = diagramQueueRef.current.shift();
    if (!batch) {
      diagramTimerRef.current = 0;
      return;
    }
    mergeDiagramBatch(batch);
    diagramTimerRef.current = setTimeout(() => {
      // re-dispatch through the ref so unmount/new-turn clears still apply
      if (diagramQueueRef.current.length) drainDiagramQueue();
      else diagramTimerRef.current = 0;
    }, 450);
  }, [mergeDiagramBatch]);

  const clearDiagramQueue = useCallback(() => {
    diagramQueueRef.current = [];
    stagedDiagramsRef.current.clear();
    windowOrderRef.current = [];
    audioWindowRef.current = [];
    currentWindowRef.current = 0;
    revealQueueRef.current = [];
    waitingRef.current = [];
    pendingBoardRef.current = null;
    setDiagramFocus(null);
    // A new turn interrupts everything: drop mid-wipe chalk, cancel the
    // pending wipe (the next explanation wipes again when ITS visuals land).
    heldDuringWipeRef.current = [];
    if (wipeTimerRef.current) {
      clearTimeout(wipeTimerRef.current);
      wipeTimerRef.current = 0;
    }
    wipingRef.current = false;
    setWiping(false);
    if (diagramTimerRef.current) {
      clearTimeout(diagramTimerRef.current);
      diagramTimerRef.current = 0;
    }
    if (revealTimerRef.current) {
      clearTimeout(revealTimerRef.current);
      revealTimerRef.current = 0;
    }
  }, []);

  useEffect(() => () => {
    if (diagramTimerRef.current) clearTimeout(diagramTimerRef.current);
    if (revealTimerRef.current) clearTimeout(revealTimerRef.current);
    if (wipeTimerRef.current) clearTimeout(wipeTimerRef.current);
  }, []);
  const openAssistantId = useRef(null);
  const assistantTextRef = useRef("");
  const asrWsRef = useRef(null); // /ws/asr connection (streaming faster-whisper)
  const asrOpenRef = useRef(false);
  const asrBusyRef = useRef(false); // a "final" transcript is on its way
  const streamingRef = useRef(false); // mic PCM currently being sent to the ASR
  // Push-to-see state: hidden <video> + hold timer + freshest captured frame.
  const sharingRef = useRef(false); // a capture session is active (mirror of `sharing`)
  const screenStreamRef = useRef(null);
  const screenVideoRef = useRef(null);
  const screenTickRef = useRef(0); // capture interval DURING the hold
  const pushTimerRef = useRef(0); // pushMaxMs auto-send cap
  const pushActiveRef = useRef(false); // button currently held down
  const pushFrameRef = useRef(null); // { b64, hash, ts } — newest captured frame
  const pushStartRef = useRef(0); // performance.now() when the hold began
  const pushWarmedHashRef = useRef(""); // hash already sent to /api/vision this hold (dedupe)
  const pushRetryRef = useRef(0); // first-capture retries until video is ready
  const pushReleasePendingRef = useRef(false); // released before the first frame landed -> flush on first frame
  const pushTextRef = useRef(""); // mic question heard DURING the hold (sent with the frame on release)
  const screenCanvasRef = useRef(null); // full-size JPEG encoder canvas
  const screenDiffCanvasRef = useRef(null); // 32x24 signature canvas
  const screenFetchBusyRef = useRef(false); // a warm-up fetch is in flight (never queue)
  const lastSentHashRef = useRef(""); // hash of the frame attached to the last turn
  // VAD state — thresholds/initial values come from CFG (env-driven).
  const vadRef = useRef({
    noise: CFG.vadNoiseFloor, // adaptive ambient floor (updated when idle)
    threshold: Math.max(CFG.vadNoiseFloor * CFG.vadGateMult, CFG.vadThresholdMin),
    hotTicks: 0, // consecutive ticks above open threshold (debounce noise blips)
    strongTicks: 0, // consecutive ticks WELL above the gate (only this may cut the assistant)
    textHeard: false, // recognizer delivered real words during this burst
    anyVoice: false, // analyser saw real voice at least once this burst
    bargeLatched: false, // already cut the assistant during this burst
    voiceSilentSince: 0, // ms timestamp when the burst went silent
    uttEndedAt: 0, // ms timestamp when the utterance was closed (speculative-release timer)
    lastUtt: 0, // recognizer last heard anything (ms)
    lastSpeakAt: 0, // when OUR speaker output last had real audio (echo guard)
    voiceEnergy: null, // leaky-integrator short-term RMS for hysteresis
    streamingRefCur: false, // mirror of streamingRef.current for tick-closed access
    recordingSince: 0, // when the current utterance was opened (diagnostic)
  });
  const listeningRef = useRef(false);
  const userTalkingRef = useRef(false);
  const micToggleRef = useRef(null); // set once by the mic effect; survives re-renders

  // ---------- helpers ----------
  const pushHistory = (role, content) => {
    historyRef.current.push({ role, content });
    if (historyRef.current.length > CFG.maxHistory) historyRef.current.shift();
  };

  const showError = (text) =>
    setMessages((m) => [...m, { id: nextId(), role: "error", text }]);

  /* ---- audio playback with an analyser feeding the globe ---- */
  const playBlob = useCallback(async (blob) => {
    const ctx = engine.unlock();
    const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
    let src;
    try {
      src = ctx.createBufferSource();
      src.buffer = buf;
      engine.connectSpeak(src);
      if (typeof src.start === "function") src.start(); // legacy WebKit fallback
      else src.noteOn(0);
      currentSourceRef.current = src;
      return new Promise((resolve) => {
        src.onended = () => {
          currentSourceRef.current = null;
          try { src.disconnect(); } catch { /* noop */ } // free the audio graph — every frame adds nodes
          resolve();
        };
      });
    } catch {
      try { src && src.disconnect(); } catch { /* noop */ }
      throw new Error("audio play failure");
    }
  }, []);

  /* ---- play an already-decoded buffer (drain prefetches decodes) ---- */
  const playBuf = useCallback((buf) => {
    const ctx = engine.unlock();
    return new Promise((resolve, reject) => {
      const src = ctx.createBufferSource();
      src.buffer = buf;
      engine.connectSpeak(src);
      currentSourceRef.current = src;
      src.onended = () => {
        currentSourceRef.current = null;
        try { src.disconnect(); } catch { /* noop */ } // free the audio graph
        resolve();
      };
      src.onerror = () => {
        currentSourceRef.current = null;
        try { src.disconnect(); } catch { /* noop */ }
        reject(new Error("audio playback error"));
      };
      try {
        src.start();
      } catch (e) {
        currentSourceRef.current = null;
        try { src.disconnect(); } catch { /* noop */ }
        reject(e);
      }
    });
  }, []);

  const drain = useCallback(async () => {
    const ctx = engine.unlock();
    let nxt = null; // AudioBuffer prefetched for the next frame (decoded while current plays)
    const startedAt = Date.now();
    while (pendingRef.current.length > 0) {
      if (dropRef.current) {
        pendingRef.current.length = 0;
        speakingRef.current = false;
        setSpeaking(false);
        return;
      }
      const blob = pendingRef.current.shift();
      const winN = audioWindowRef.current.length ? audioWindowRef.current.shift() : currentWindowRef.current + 1;
      currentWindowRef.current = winN || 0;
      // Audio-synced board: this window's diagram delta (if already arrived)
      // appears exactly when its speech starts — position matches explanation.
      // First audio also fronts the staged Whiteboard (canvas with speech).
      try { flushDiagramsUpTo(currentWindowRef.current); } catch { /* board must never break voice */ }
      try { frontBoardIfReady(); } catch { /* board must never break voice */ }
      // decode the NEXT queued frame in parallel with playing this one, so
      // the handoff is gapless instead of "play -> stop -> decode -> play"
      const pre = (pendingRef.current.length > 0)
        ? ctx.decodeAudioData(await pendingRef.current[0].arrayBuffer()).catch(() => null)
        : Promise.resolve(null);
      let buf = nxt;
      nxt = null;
      if (!buf) {
        try {
          buf = await ctx.decodeAudioData(await blob.arrayBuffer());
        } catch {
          // bad frame — drop it but keep the queue and speaking state healthy
          console.warn("[voice] dropped a corrupt TTS audio frame");
          await pre.catch(() => null); // keep the prefetch warm
          continue;
        }
      }
      try {
        await playBuf(buf);
      } catch {
        // playback failed — stop claiming we're speaking so the UI recovers
        currentSourceRef.current = null;
        speakingRef.current = false;
        setSpeaking(false);
        pendingRef.current = [];
        console.warn("[voice] TTS playback failed; cleared pending frames");
        return;
      }
      nxt = await pre; // cache for the next iteration
    }
    // Queue drained while the reply is still streaming — remember it so the
    // NEXT arriving frame restarts playback immediately instead of waiting
    // for the jitter buffer to refill (which would add dead air).
    if (activeRef.current) drainRestartRef.current = true;
    speakingRef.current = false;
    setSpeaking(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playBuf, flushDiagramsUpTo]);

  /* ---- hard stop: instant audio cut + server cancel (barge-in) ---- */
  const hardStop = useCallback(() => {
    dropRef.current = true; // drop stale frames/text until the next "start"
    acceptedOsTurnRef.current = null; // pre-start agent moves need a fresh submit
    drainRestartRef.current = false;
    drainStartedRef.current = false;
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop();
      } catch { /* noop */ }
      currentSourceRef.current = null;
    }
    pendingRef.current.length = 0;
    audioWindowRef.current = [];
    windowOrderRef.current = [];
    stagedDiagramsRef.current.clear();
    revealQueueRef.current = [];
    waitingRef.current = [];
    if (revealTimerRef.current) {
      clearTimeout(revealTimerRef.current);
      revealTimerRef.current = 0;
    }
    if (wsRef.current && wsRef.current.readyState === 1) {
      wsRef.current.send(stopMessage());
    }
    speakingRef.current = false;
    setSpeaking(false);
    setTurnActive(false);
  }, []);

  /* ---- push-to-see: hold X (or the screen button) → capture → describe →
     auto-send on release ----
     Latency design (replaces the continuous 1.2 s screen-share loop):
     1. Press  → the capture stream is already granted (see below), so frames
        start immediately (400 ms cadence, NO change-detection — the user IS
        the trigger). First press of a session shows Chrome's picker ONCE;
        the stream then stays alive silently between presses (a browser can
        never capture without the one-time permission picker).
     2. Every captured frame goes to /api/vision in the BACKGROUND with a
        unique hash, so the Qwen2.5-VL describe runs WHILE the user is still
        holding/talking. The last warm-up's result stays in the server cache.
     3. Release (or 5 s cap) → the FRESHEST frame is attached to the turn as
        {screen: {image, hash, wait_ms}}. A question spoken into the mic
     during the hold is absorbed and sent as the turn text; with no text
     the turn IS the screen ("Describe what is on this screen").
     4. No GPU/network vision cost while X is NOT held — only the idle local
        capture stream (no frames fetched, no uploads). Revoke anytime via
        Chrome's own "Stop sharing" bar. */
  const stopScreenCapture = useCallback(() => {
    pushActiveRef.current = false;
    pushReleasePendingRef.current = false;
    if (pushTimerRef.current) { clearTimeout(pushTimerRef.current); pushTimerRef.current = 0; }
    if (screenTickRef.current) { clearInterval(screenTickRef.current); screenTickRef.current = 0; }
    const stream = screenStreamRef.current;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    screenStreamRef.current = null;
    const vid = screenVideoRef.current;
    if (vid) { try { vid.srcObject = null; } catch { /* noop */ } }
    sharingRef.current = false;
    pushFrameRef.current = null;
    setSharing(false);
  }, []);

  /* Grant the capture stream ONCE and keep it alive between holds. Chrome
     always shows its permission picker on the first getDisplayMedia (no API
     skips it — security rule), but a live stream can be reused silently, so
     every X-hold after the first starts at ZERO picker latency. */
  const ensureCaptureStream = useCallback(async () => {
    const existing = screenStreamRef.current;
    if (existing && existing.getVideoTracks()[0]?.readyState === "live") return existing;
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 5 }, audio: false,
    });
    const vid = document.createElement("video");
    vid.srcObject = stream;
    vid.muted = true;
    vid.playsInline = true;
    await vid.play().catch(() => {});
    screenStreamRef.current = stream;
    screenVideoRef.current = vid;
    stream.getVideoTracks()[0]?.addEventListener("ended", () => {
      // user hit Chrome's "Stop sharing" — revoke fully
      stopScreenCapture();
    });
    return stream;
  }, [stopScreenCapture]);

  /* One capture tick while the button is held: grab the frame NOW (no diff
     gate — during a hold every tick is a deliberate capture) and warm the
     vision cache in the background. Never queues: one in-flight fetch max. */
  const pushCaptureTick = () => {
    const vid = screenVideoRef.current;
    if (!vid || !pushActiveRef.current) return;
    if (!vid.videoWidth) {
      // The video element needs a moment after .play() — retry quickly instead
      // of silently dropping the whole hold's warm-up window.
      if (pushRetryRef.current < 10) {
        pushRetryRef.current += 1;
        setTimeout(pushCaptureTick, 100);
      }
      return;
    }
    if (!screenCanvasRef.current) {
      screenCanvasRef.current = document.createElement("canvas");
      screenDiffCanvasRef.current = document.createElement("canvas");
      screenDiffCanvasRef.current.width = 32;
      screenDiffCanvasRef.current.height = 24;
    }
    // encode at 960px/q0.65 — OCR-grade quality, ~2x smaller upload than 1280
    const scale = Math.min(1, 960 / vid.videoWidth);
    const c = screenCanvasRef.current;
    c.width = Math.round(vid.videoWidth * scale);
    c.height = Math.round(vid.videoHeight * scale);
    c.getContext("2d").drawImage(vid, 0, 0, c.width, c.height);
    const b64 = c.toDataURL("image/jpeg", 0.65).split(",")[1];
    // per-tick signature — each distinct screen state gets its own cache key,
    // so the LAST tick's describe is always the freshest one in the cache
    const dctx = screenDiffCanvasRef.current.getContext("2d", { willReadFrequently: true });
    dctx.drawImage(vid, 0, 0, 32, 24);
    const px = dctx.getImageData(0, 0, 32, 24).data;
    let sig = 0;
    for (let i = 0, j = 0; i < 32 * 24; i++, j += 4) {
      sig = (sig * 31 + ((px[j] * 299 + px[j + 1] * 587 + px[j + 2] * 114) / 1000)) | 0;
    }
    const hash = `p${sig >>> 0}`;
    pushFrameRef.current = { b64, hash, ts: Date.now() };
    // Dedupe: an unchanged screen during a hold has the SAME hash — re-POSTing
    // it would only burn GPU re-describing (or OCR-ing) identical pixels. Warm
    // each DISTINCT screen state once per hold.
    if (hash === pushWarmedHashRef.current || screenFetchBusyRef.current) return;
    pushWarmedHashRef.current = hash;
    screenFetchBusyRef.current = true;
    const t0 = performance.now();
    fetch(VISION_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: b64, hash }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j && console.info(
        `[vision] hold warm-up ${j.cached ? "HIT" : "FILLED"} (${Math.round(performance.now() - t0)}ms)`,
      ))
      .catch(() => {})
      .finally(() => { screenFetchBusyRef.current = false; });
  };

  const startPushCapture = useCallback(async () => {
    if (sharingRef.current || pushActiveRef.current) return;
    if (!CFG.visionEnabled) {
      showError("Vision is disabled on the server — check VISION_BACKEND in .env.");
      return;
    }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      showError("Screen capture is not available in this browser — try Chrome/Edge.");
      return;
    }
    try {
      // First press of a session: Chrome's picker shows here (unavoidable).
      // Every later press: this resolves instantly from the live stream.
      await ensureCaptureStream();
      sharingRef.current = true;
      pushActiveRef.current = true;
      pushStartRef.current = performance.now();
      pushWarmedHashRef.current = "";
      pushRetryRef.current = 0;
      pushReleasePendingRef.current = false;
      pushTextRef.current = "";
      setSharing(true);
      // first frame IMMEDIATELY, then every pushTickMs until release/cap
      pushCaptureTick();
      screenTickRef.current = setInterval(pushCaptureTick, CFG.pushTickMs);
      // hard cap: a held key auto-sends anyway ("not more than 5 sec")
      pushTimerRef.current = setTimeout(() => {
        if (pushActiveRef.current) {
          console.info("[push] hold exceeded max — auto-sending");
          apiRef.current.releasePush();
        }
      }, CFG.pushMaxMs);
    } catch (e) {
      if (e && e.name === "NotAllowedError") {
        showError("Screen capture permission denied — try again and press 'Share'.");
      } else {
        showError("Could not start screen capture: " + (e.message || e.name));
      }
      console.warn("[push] getDisplayMedia failed:", e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ensureCaptureStream]);  /* Release the held X/button: stop the capture LOOP (the granted stream
     stays alive for the next hold — no picker again), attach the freshest
     frame to a turn, and send. A question spoken into the mic while holding
     becomes the turn text; with no text the turn IS the screen. */
  const releasePush = useCallback(() => {
    if (!pushActiveRef.current) return;
    pushActiveRef.current = false;
    if (pushTimerRef.current) { clearTimeout(pushTimerRef.current); pushTimerRef.current = 0; }
    if (screenTickRef.current) { clearInterval(screenTickRef.current); screenTickRef.current = 0; }
    const heldMs = Math.round(performance.now() - pushStartRef.current);
    const frame = pushFrameRef.current;
    pushFrameRef.current = null;
    sharingRef.current = false;
    setSharing(false);
    if (!frame) {
      // First capture hasn't landed yet (very fast tap / picker just closed):
      // arm a short flush so the first frame STILL becomes the turn instead
      // of being dropped.
      if (pushRetryRef.current > 0 || screenVideoRef.current) {
        pushReleasePendingRef.current = true;
        setTimeout(() => {
          if (pushReleasePendingRef.current && pushFrameRef.current) {
            pushReleasePendingRef.current = false;
            apiRef.current.releasePush();
          }
        }, 300);
      }
      console.warn("[push] released after " + heldMs + "ms but no frame was captured yet — flushing on first frame");
      return;
    }
    console.info(`[push] hold ${heldMs}ms -> turn with frame (${Math.round(frame.b64.length * 3 / 4 / 1024)} KB, hash ${frame.hash})`);
    lastSentHashRef.current = frame.hash;
    // If the release-instant frame was NEVER warmed (identical-frame dedupe,
    // dropped fetch, or a very short tap), describe it now. NOT forced: a
    // cache-first call piggybacks on any in-flight describe of the same hash
    // (which the turn's wait_ms then waits on) and costs 0 ms if a previous
    // hold already described these exact pixels.
    if (frame.hash !== pushWarmedHashRef.current) {
      fetch(VISION_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: frame.b64, hash: frame.hash }),
      }).catch(() => {});
    }
    // A question spoken during the hold wins; typed text second; screen-only
    // (no words) makes the turn "describe what you see".
    const text = (pushTextRef.current || "").trim() || (input || "").trim()
      || "Describe what is on this screen — what do you see?";
    pushTextRef.current = "";
    setInput("");
    submitPushChat(text, frame, heldMs);

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input]);

  /* One capture tick (legacy continuous mode): downsample -> change detect ->
     encode JPEG on change -> background warm-up call. */
  const screenTick = () => {
    const vid = screenVideoRef.current;
    if (!vid || !sharingRef.current || !vid.videoWidth) return;
    if (!screenCanvasRef.current) {
      screenCanvasRef.current = document.createElement("canvas");
      screenDiffCanvasRef.current = document.createElement("canvas");
      screenDiffCanvasRef.current.width = 32;
      screenDiffCanvasRef.current.height = 24;
    }
    // 1) downsample to 32x24 gray and build a cheap signature
    const dctx = screenDiffCanvasRef.current.getContext("2d", { willReadFrequently: true });
    dctx.drawImage(vid, 0, 0, 32, 24);
    const px = dctx.getImageData(0, 0, 32, 24).data;
    let prevSig = 0;
    for (let i = 0, j = 0; i < 32 * 24; i++, j += 4) {
      prevSig = (prevSig * 31 + ((px[j] * 299 + px[j + 1] * 587 + px[j + 2] * 114) / 1000)) | 0;
    }
    // 2) skip if the screen looks identical to the last warm-up (cursor blinks
    //    etc. still sneak through — the hash makes the server cache absorb them)
    const hash = `s${prevSig >>> 0}`;
    if (hash === lastSentHashRef.current && !screenFetchBusyRef.current) return;
    // 3) encode the real frame (max 1280px wide, q0.7 ≈ 100-250 KB)
    const scale = Math.min(1, 1280 / vid.videoWidth);
    const c = screenCanvasRef.current;
    c.width = Math.round(vid.videoWidth * scale);
    c.height = Math.round(vid.videoHeight * scale);
    c.getContext("2d").drawImage(vid, 0, 0, c.width, c.height);
    const b64 = c.toDataURL("image/jpeg", 0.7).split(",")[1];
    // 4) background warm-up: describe the NEW screen now so the reply later
    //    hits the server cache and pays ZERO vision latency.
    //    NEVER queue: a local VLM takes 7-15 s per screen. One in-flight max.
    if (screenFetchBusyRef.current) return;
    screenFetchBusyRef.current = true;
    const t0 = performance.now();
    fetch(VISION_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: b64, hash }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j && console.info(`[vision] warm cache ${j.cached ? "HIT" : "FILLED"} (${(j.description || "").length} chars, ${Math.round(performance.now() - t0)}ms)`))
      .catch(() => {})
      .finally(() => { screenFetchBusyRef.current = false; });
  };

  const startScreenShare = useCallback(async () => {
    if (sharingRef.current) return;
    if (!CFG.visionEnabled) {
      showError("Vision is disabled on the server — check VISION_BACKEND in .env.");
      return;
    }
    if (!navigator.mediaDevices?.getDisplayMedia) {
      showError("Screen sharing is not available in this browser — try Chrome/Edge.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 5 }, audio: false,
      });
      const vid = document.createElement("video");
      vid.srcObject = stream;
      vid.muted = true;
      vid.playsInline = true;
      await vid.play().catch(() => {});
      screenStreamRef.current = stream;
      screenVideoRef.current = vid;
      lastSentHashRef.current = "";
      sharingRef.current = true;
      setSharing(true);
      console.info("[screen] legacy continuous capture loop started (tick " + CFG.screenTickMs + "ms)");
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        // user hit "Stop sharing" — tear the loop down
        const s = screenStreamRef.current;
        if (s) s.getTracks().forEach((t) => t.stop());
        screenStreamRef.current = null;
        const v = screenVideoRef.current;
        if (v) { try { v.srcObject = null; } catch { /* noop */ } }
        if (screenTickRef.current) { clearInterval(screenTickRef.current); screenTickRef.current = 0; }
        sharingRef.current = false;
        setSharing(false);
      }); // user hit "Stop sharing"
      screenTickRef.current = setInterval(screenTick, CFG.screenTickMs);
    } catch (e) {
      // VISIBLE failures: a swallowed NotAllowedError made users believe the
      // screen was being shared when the browser had actually blocked it.
      if (e && e.name === "NotAllowedError") {
        showError("Screen share permission denied — try again and press 'Share'.");
      } else {
        showError("Could not start screen sharing: " + (e.message || e.name));
      }
      console.warn("[screen] getDisplayMedia failed:", e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Capture the screen RIGHT NOW (used at question time so the tutor always
     sees the screen as it is when you ask — never a stale cached frame).
     960px/q0.65: OCR reads text fine at this size and the WS upload (and the
     inline OCR) shrink ~2x vs 1280px/q0.7 — pure latency win on the reply. */
  const grabScreen = () => {
    const vid = screenVideoRef.current;
    if (!vid || !sharingRef.current || !vid.videoWidth) return null;
    if (!screenCanvasRef.current) screenCanvasRef.current = document.createElement("canvas");
    const scale = Math.min(1, 960 / vid.videoWidth);
    const c = screenCanvasRef.current;
    c.width = Math.round(vid.videoWidth * scale);
    c.height = Math.round(vid.videoHeight * scale);
    c.getContext("2d").drawImage(vid, 0, 0, c.width, c.height);
    const b64 = c.toDataURL("image/jpeg", 0.65).split(",")[1];
    // signature from the same instant — same pixels = same hash = 0 ms OCR;
    // changed pixels = new hash = server OCRs fresh (~0.5-1 s GPU)
    if (!screenDiffCanvasRef.current) {
      screenDiffCanvasRef.current = document.createElement("canvas");
      screenDiffCanvasRef.current.width = 32;
      screenDiffCanvasRef.current.height = 24;
    }
    const dctx = screenDiffCanvasRef.current.getContext("2d", { willReadFrequently: true });
    dctx.drawImage(vid, 0, 0, 32, 24);
    const px = dctx.getImageData(0, 0, 32, 24).data;
    let sig = 0;
    for (let i = 0, j = 0; i < 32 * 24; i++, j += 4) {
      sig = (sig * 31 + ((px[j] * 299 + px[j + 1] * 587 + px[j + 2] * 114) / 1000)) | 0;
    }
    return { image: b64, b64, hash: `s${sig >>> 0}` };
  };

  /* ---- submit a new user turn ---- */
  const submitChat = useCallback(
    (rawText, screenFrame = null) => {
      const text = (rawText || "").trim();
      if (!text) return;
      hardStop();
      clearDiagramQueue();
      activeTurnIdRef.current += 1;
      // This turn's pre-start agent moves (blocking director) are valid even
      // though dropRef is still true until the server's "start".
      acceptedOsTurnRef.current = String(activeTurnIdRef.current);
      diagramTurnRef.current = null;
      // Fresh board per explanation: the old lesson stays visible while the
      // tutor thinks, then wipes (smooth fade) the moment the NEW reply's
      // first visuals arrive — never drawn over. Resume live-follow.
      setFollowLive(true);
      setMessages((m) => [...m, { id: nextId(), role: "user", text, ts: Date.now() }]);
      pushHistory("user", text);

      const ws = wsRef.current;
      if (!ws || ws.readyState !== 1) {
        if (ws && ws.readyState === 0) {
          // Socket is reconnecting: wait 350ms and retry rather than dropping
          // turn — the attached screen frame rides along on the retry too.
          setTimeout(() => submitChat(rawText, screenFrame), 350);
          return;
        }
        showError("No server connection — please wait and ask again.");
        return;
      }
      // dropRef stays true (set by hardStop) until the server's "start" for
      // this reply — any stale frames of the aborted reply are ignored.
      framesRef.current = 0;
      turnStartRef.current = performance.now(); // browser-measured first-audio latency
      activeRef.current = false;
      // SELF-BARGE-IN GUARD: hardStop() just stopped the mic's echo gate; the
      // barge path sees speakingRef=false but an old VAD burst can STILL fire
      // hardStop again AFTER this submission, killing the turn server-side
      // (0 frames, silent reply). Latch barge-in for a moment so our own turn
      // can never cut itself off (a real user interrupt re-arms it via text).
      openAssistantId.current = null;
      assistantTextRef.current = "";
      setTyping(true);
      recordQuestion();
      const payload = {
        text,
        history: historyRef.current,
        nfeStep: CFG.chatStep,
        clientTurnId: activeTurnIdRef.current,
        provider: llmProviderRef.current,
      };
      // Push-to-see: the held button already captured + warmed the frame.
      // Attach it (with wait_ms) so the server waits briefly for the in-flight
      // describe instead of answering blind. Legacy continuous-share path
      // (CFG.pushMode off) still captures at question time below.
      if (screenFrame) {
        payload.screen = {
          image: screenFrame.b64,
          hash: screenFrame.hash,
          wait_ms: 2000, // release-time warm-up gets a bounded window to land
        };
        console.info(
          `[screen] push frame attached (${Math.round(screenFrame.b64.length * 3 / 4 / 1024)} KB, hash ${screenFrame.hash}, hold ${screenFrame.heldMs}ms)`,
        );
      } else if (!CFG.pushMode && sharingRef.current) {
        // PRODUCTION RULE (legacy continuous mode): capture at question time —
        // the tutor always sees the screen as it is RIGHT NOW, automatically.
        const shot = grabScreen();
        if (shot) {
          payload.screen = shot;
          lastSentHashRef.current = shot.hash;
          console.info(`[screen] frame attached to turn (${Math.round(shot.b64.length * 3 / 4 / 1024)} KB, hash ${shot.hash})`);
        } else {
          console.warn("[screen] sharing is ON but grabScreen() returned null — video not ready");
        }
      }
      ws.send(chatMessage({
        ...payload,
        screen: payload.screen,
        // OS Director context: the full desktop snapshot the agent reasons
        // over to drive apps/browser/tiles via os_action messages.
        os: {
          app: activeApp,
          open: openApps,
          minimized: Object.keys(minApps).filter((k) => minApps[k]),
          snapped: snaps,
          browserUrl,
          browserTabs,
          note: (() => {
            const n = notes.find((x) => x.id === (activeNoteId || notes[0]?.id));
            return n ? { title: n.title, snippet: String(n.body || "").slice(0, 600) } : null;
          })(),
          whiteboardSteps: steps.length,
          code: codeCtxRef.current,
          // Hardcoded learner + curriculum context (generic schema — same keys
          // work for any subject, not just MERN/coding). Server may ignore
          // unknown keys; sanitizer keeps what it allows.
          student: { name: STUDENT.name, gender: STUDENT.gender, qualification: STUDENT.qualification, college: STUDENT.college },
          courseId: activeCourseId,
          progress: { completed: completedLessonIds, activeLessonId, scores: INITIAL_PROGRESS.scores },
          lesson: (() => {
            const course = getCourseById(activeCourseId) || COURSE;
            const l = getLessonById(activeLessonId, course);
            return l ? { id: l.id, title: l.title, kind: l.kind, objective: l.objective } : null;
          })(),
        },
      }));
    },
    [hardStop, activeApp, openApps, minApps, snaps, browserUrl, browserTabs, notes, activeNoteId, steps.length, activeCourseId, activeLessonId, completedLessonIds]
  );

  /* Push-to-see turn: text + the frame captured during the hold. */
  const submitPushChat = useCallback(
    (text, frame, heldMs) => submitChat(text, { ...frame, heldMs }),
    [submitChat],
  );

  apiRef.current = {
    submitChat,
    hardStop,
    // Agent OS control: validated window moves from the OS Director sidecar.
    execOsAction: (a) => execOsAction(a),
    // Push-to-see: press starts a capture session, release sends the turn.
    startPush: () => startPushCapture(),
    releasePush: () => releasePush(),
    pushActiveRef,
    // Legacy continuous-share toggle (SCREEN_PUSH_MODE=0)
    toggleScreenShare: () => startPushCapture(),
    setSpeaking: (v) => {
      speakingRef.current = v;
      setSpeaking(v);
    },
    setUserTalking,
    userTalkingRef,
    // toggleMic lives in a ref (set once by the mic effect); apiRef.current is
    // rebuilt on every render, so we expose a stable dispatcher instead.
    toggleMic: () => micToggleRef.current && micToggleRef.current(),
  };

  /* ---------- ASR readiness: server preloads Whisper at boot ---------- */
  const [asrReady, setAsrReady] = useState(false);
  const [asrReconnecting, setAsrReconnecting] = useState(false);
  // Server rejected the last utterance (speaker-gate or noise blip) — show a
  // transient chip so it's clear WHY nothing happened, then auto-dismiss.
  const [asrRejected, setAsrRejected] = useState("");
  const asrRejTimerRef = useRef(0);
  useEffect(() => () => clearTimeout(asrRejTimerRef.current), []); // unmount cleanup
  useEffect(() => {
    let alive = true;
    let t = 0;
    const check = () => {
      fetch(CONFIG_URL)
        .then((r) => (r.ok ? r.json() : null))
        .then((c) => {
          if (alive && c && c.asr_ready) {
            setAsrReady(true);
            clearInterval(t);
          }
        })
        .catch(() => {});
    };
    check();
    t = setInterval(check, 3000); // re-poll until the warmup finishes
    return () => { alive = false; clearInterval(t); };
  }, []);

  /* ---------- WebSocket ---------- */
  useEffect(() => {
    let closed = false;
    let ttsAttempts = 0;
    let ttsHb = 0;
    let ttsLastPong = 0;
    // playback watchdog: if we claim to be speaking but nothing is actually
    // playing and no new frame has arrived, clear the stuck state so the UI
    // and the echo guard don't stay wrong.
    let speakWatchdog = 0;
    const connect = () => {
      const ws = new WebSocket(WS_URL);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => {
        ttsAttempts = 0;
        ttsLastPong = Date.now();
        setConnected(true);
        // heartbeat: detect a dead connection in ~15s instead of uvicorn's 40s
        ttsHb = setInterval(() => {
          try {
            ws.send(pingMessage());
          } catch { /* closed — onclose handles it */ }
          if (Date.now() - ttsLastPong > 15000) {
            try { ws.close(); } catch { /* noop */ } // force reconnect
          }
        }, 5000);
      };
      ws.onerror = () => setConnected(false);
      ws.onclose = () => {
        setConnected(false);
        if (ttsHb) { clearInterval(ttsHb); ttsHb = 0; }
        if (!closed) {
          ttsAttempts += 1;
          // exponential backoff, capped: 1.5s -> 3s -> 6s -> 12s -> 15s
          const delay = Math.min(CFG.wsReconnectMs * 2 ** Math.min(ttsAttempts - 1, 3), 15000);
          setTimeout(connect, delay);
        }
      };
      ws.onmessage = (ev) => {
        const api = apiRef.current;
        if (typeof ev.data === "string") {
          let m;
          try {
            m = JSON.parse(ev.data);
          } catch {
            return;
          }
          if (m.type === "pong") { // heartbeat reply
            ttsLastPong = Date.now();
            return;
          }
          if (m.type === "start") {
            dropRef.current = false;
            activeRef.current = true;
            framesRef.current = 0;
            drainRestartRef.current = false;
            drainStartedRef.current = false;
            setTyping(false);
            setTurnActive(true); // reply owed: notch shows Speaking until done/error
            // Mark the reply "speaking" from the START of the stream, not
            // when the first sample plays. The mic echo-gates and the server
            // VAD assistant-gate key off this flag; during the jitter-buffer
            // wait (no audio yet) they must already be closed, or the mic
            // hears speaker echo and barge-in kills the reply before it plays.
            if (!speakingRef.current) {
              speakingRef.current = true;
              api.setSpeaking(true);
            }
          } else if (m.type === "window") {
            // Debug: how the LLM stream was divided into TTS chunks + their
            // generation cost. RTF > 1 means that chunk generates slower than
            // it plays — the direct cause of mid-reply underruns.
            console.info(
              `[voice] TTS window #${m.n}: ${m.chars} ch, ${m.steps} steps, speed ${m.speed}` +
              ` | audio ${m.audio_s}s / gen ${m.gen_s}s (RTF ${m.rtf})` +
              ` | "${m.text}"`,
            );
            // Pair window numbers with the audio blobs that follow in WS order.
            if (m.n != null) windowOrderRef.current.push(Number(m.n));
          } else if (m.type === "diagram") {
            if (dropRef.current) return;
            if (m.client_turn_id && m.client_turn_id !== String(activeTurnIdRef.current)) return;
            // Whole-board (legacy) or window delta (watcher sidecar).
            const incoming = m.diagram?.elements?.length ? m.diagram.elements : (m.elements?.length ? m.elements : null);
            if (!incoming) return;
            // Tutor called canvas: first visual of a turn only STAGES the
            // board — it fronts when the turn's audio starts (frontBoardIfReady),
            // so the canvas arrives with speech, never before it.
            // Functional setStates only — safe inside this long-lived handler.
            const isNewVisualTurn = m.turn_id && diagramTurnRef.current !== m.turn_id;
            if (m.turn_id) diagramTurnRef.current = m.turn_id;
            if (isNewVisualTurn) pendingBoardRef.current = m.turn_id;
            console.info(`[diagram] ${m.mode === "append" ? `delta window #${m.window_n ?? "?"}` : "board"}: +${incoming.length} element(s)`);
            if (m.mode === "append" && m.window_n != null) {
              // New explanation: wipe the old lesson first (smooth fade) so
              // the new chalk lands on a clean board, never over the old one.
              if (isNewVisualTurn) {
                try { maybeWipeBoardForNewVisuals(); } catch { /* noop */ }
              }
              // Audio-synced staging: draw only when window_n's speech plays.
              const wn = Number(m.window_n);
              const prev = stagedDiagramsRef.current.get(wn) || [];
              const seenIds = new Set(prev.map((el) => el?.id));
              for (const el of incoming) {
                if (el?.id && !seenIds.has(el.id)) { seenIds.add(el.id); prev.push(el); }
              }
              stagedDiagramsRef.current.set(wn, prev);
              // Late planner (diagram arrived after its audio already played)
              // still draws instead of stranding the step forever — and fronts
              // the board now that speech is already going.
              try { flushDiagramsUpTo(currentWindowRef.current); } catch { /* noop */ }
              try { frontBoardIfReady(); } catch { /* noop */ }
            } else {
              try { maybeWipeBoardForNewVisuals(); } catch { /* noop */ }
              mergeDiagramBatch(incoming);
            }
          } else if (m.type === "diagram_error") {
            if (!dropRef.current) console.info("[diagram] visual explanation unavailable", m.message || "");
          } else if (m.type === "os_action") {
            // OS Director moves. Blocking-path moves arrive BEFORE "start"
            // (so the tutor can narrate them) while dropRef is still true —
            // accept them only for the current turn; stale/interrupted ones
            // (barge with no resubmit, old turns) are dropped.
            const turnId = String(m.action?.client_turn_id || "");
            if (dropRef.current && turnId !== String(acceptedOsTurnRef.current)) return;
            try {
              apiRef.current.execOsAction && apiRef.current.execOsAction(m.action);
            } catch { /* agent moves must never break voice */ }
          } else if (m.type === "text") {
            if (dropRef.current) return; // stale sentence of an aborted reply
            setTyping(false);
            setMessages((ms) => {
              let list = ms;
              if (!openAssistantId.current) {
                const b = { id: nextId(), role: "assistant", text: "", ts: Date.now() };
                openAssistantId.current = b.id;
                list = [...ms, b];
              }
              return list.map((x) =>
                x.id === openAssistantId.current
                  ? { ...x, text: x.text + m.text }
                  : x
              );
            });
            assistantTextRef.current += m.text;
            // Trigger-watch: a board element whose spoken word just arrived
            // in the caption draws NOW (caption == speech clock).
            try { matchWaiting(); } catch { /* board must never break voice */ }
          } else if (m.type === "error") {
            if (assistantTextRef.current) pushHistory("assistant", assistantTextRef.current);
            assistantTextRef.current = "";
            openAssistantId.current = null;
            activeRef.current = false;
            // a server-side failure (e.g. OmniVoice returned no audio) should
            // not leave the UI stuck in a "speaking" state.
            speakingRef.current = false;
            setSpeaking(false);
            if (speakWatchdog) { clearTimeout(speakWatchdog); speakWatchdog = 0; }
            if (currentSourceRef.current) {
              try { currentSourceRef.current.stop(); } catch { /* noop */ }
              currentSourceRef.current = null;
            }
            pendingRef.current = [];
            showError("Speech error: " + m.message);
            setTurnActive(false);
          } else if (m.type === "done") {
            if (dropRef.current) {
              // closing done of the reply we interrupted — discard silently
              openAssistantId.current = null;
              assistantTextRef.current = "";
              activeRef.current = false;
              setTurnActive(false);
              return;
            }
            console.info(
              `[voice] reply done: ${m.frames} frame(s) | server total ${m.elapsed}s | first audio ${m.first_audio ?? "?"}s | TTS RTF ${m.rtf ?? "?"}`,
            );
            // attach the server-measured response time to the finished bubble
            const doneId = openAssistantId.current;
            if (doneId && m.elapsed != null) {
              setMessages((ms) =>
                ms.map((x) => (x.id === doneId ? { ...x, elapsed: m.elapsed } : x))
              );
            }
            if (assistantTextRef.current) pushHistory("assistant", assistantTextRef.current);
            // Reply stream done: draw EVERYTHING still staged/waiting (slow
            // planner tail + unmatched triggers) — nothing strands as blank.
            // Paced reveal keeps it stepwise; board fronts now if not yet shown.
            try { flushDiagramsUpTo(Number.MAX_SAFE_INTEGER, true); } catch { /* noop */ }
            try { frontBoardIfReady(true); } catch { /* noop */ }

            assistantTextRef.current = "";
            openAssistantId.current = null;
            activeRef.current = false;
            setTurnActive(false); // stream over — Speaking label now follows playback only
            // Reply stream is complete — if the jitter buffer is still holding
            // frames (never reached jitterFrames), start playback NOW so the
            // tail isn't stranded silent until the next turn.
            if (!speakingRef.current && pendingRef.current.length > 0) {
              speakingRef.current = true;
              api.setSpeaking(true);
              drain();
            }
            // audio may still be playing its last frame — aura keeps pulsing
            // until drain() ends; only force-stop if nothing is left.
            if (!currentSourceRef.current && pendingRef.current.length === 0) {
              api.setSpeaking(false);
            }
          }
        } else {
          if (dropRef.current) return; // stale audio frame of an aborted reply
          framesRef.current += 1;
          if (framesRef.current === 1 && turnStartRef.current) {
            console.info(
              `[voice] first audio received ${(performance.now() - turnStartRef.current).toFixed(0)}ms after submit (browser-measured, incl. network)`,
            );
          }
          pendingRef.current.push(new Blob([ev.data], { type: "audio/wav" }));
          // Pair this blob with its TTS window number (WS order is preserved:
          // window(n) arrives just before audio(n)). Falls back to sequential.
          if (windowOrderRef.current.length) {
            audioWindowRef.current.push(windowOrderRef.current.shift());
          } else {
            const last = audioWindowRef.current.length
              ? audioWindowRef.current[audioWindowRef.current.length - 1]
              : currentWindowRef.current;
            audioWindowRef.current.push((Number(last) || 0) + 1);
          }
          // Jitter buffer: don't start playing on the first frame alone. The
          // first window is a tiny ~1s fragment; starting immediately means
          // playback runs dry before window #2 is generated (RTF > 1 on
          // MPS/CPU) — heard as mid-word cutoffs. Wait until jitterFrames
          // are queued, or the reply stream ends (done/error), to start.
          const wantStart =
            CFG.jitterFrames <= 0 ||
            pendingRef.current.length >= CFG.jitterFrames ||
            drainRestartRef.current ||
            !activeRef.current;
          if (!speakingRef.current && wantStart) {
            drainRestartRef.current = false;
            speakingRef.current = true;
            api.setSpeaking(true);
            drain();
          }
          // If the "start" event already opened the speaking state, just kick
          // playback when the jitter condition is met.
          else if (speakingRef.current && !currentSourceRef.current && !drainStartedRef.current && wantStart) {
            drainStartedRef.current = true;
            drain().finally(() => { drainStartedRef.current = false; });
          }
          // keep the playback watchdog honest: a new frame just landed
          if (speakWatchdog) {
            clearTimeout(speakWatchdog);
            speakWatchdog = 0;
          }
          // arm the watchdog the first time we start playing — if the queue
          // empties and nothing replays within ~2.5 s, something is stuck.
          if (!speakWatchdog && currentSourceRef.current) {
            speakWatchdog = setTimeout(() => {
              if (speakingRef.current && !currentSourceRef.current && pendingRef.current.length === 0) {
                speakingRef.current = false;
                setSpeaking(false);
                console.warn("[voice] speaking stuck with no active source — cleared");
              }
              speakWatchdog = 0;
            }, 2500);
          }
        }
      };
    };
    connect();
    return () => {
      closed = true;
      if (speakWatchdog) { clearTimeout(speakWatchdog); speakWatchdog = 0; }
      const ws = wsRef.current;
      if (ws) ws.close();
    };
  }, [drain]);

  /* ---------- Mic: realtime conversation -----------------------------
     Echo-free voice input (OpenAI/Gemini-style):
       1. Mic ON  -> getUserMedia with echoCancellation. Chrome subtracts our
          own speaker output from this stream, so the assistant can never
          "hear" itself. The Web Speech API is GONE — its separate capture
          path had no AEC reference, which caused the self-conversation loop.
       2. The AEC-cleaned mic is tapped (AudioWorklet, 16 kHz) and streamed to
          the server's /ws/asr (faster-whisper). Partial transcripts come back
          as live captions; the authoritative "final" is sent as the user turn.
       3. VAD (energy) drives turn-taking: sustained voice (~250 ms) opens an
          utterance, ~0.5 s of silence closes it, barge-in still cuts the
          assistant on real sustained speech. While our reply is audibly
          playing, mic frames are dropped, so residual echo can never even be
          sent to the transcriber.
  -------------------------------------------------------------------- */
  useEffect(() => {
    let rafVad = 0;
    let pcmTimer = 0;
    let closingAsr = false;
    let asrClosedCount = 0;
    let asrAttempts = 0;
    let asrHb = 0;
    let asrLastPong = 0;
    let asrWarned = false;
    let pcmBuf = []; // Float32Array pieces waiting to be flushed to /ws/asr
    let pcmLen = 0;
    // Silence-tail hold: after "early_end" we STOP streaming mic PCM so the
    // server's early-decode buffer stays frozen (exact reuse at "end"). Frames
    // arriving during the tail are parked here and restored if speech resumes.
    let tailHold = false;
    let tailBuf = [];
    // Server-side Silero VAD mode: the SERVER decides when an utterance opens
    // (neural speech/noise classification — fans/doors/keys can't open turns).
    // The browser becomes a dumb continuous streamer + keeps energy barge-in.
    let serverMode = CFG.asrVadMode === "server";
    let prevAssistant = false; // speaking-state edge -> /ws/asr "assistant" gate
    let lastPartial = ""; // most recent live caption (fallback if final is empty)
    let specSentFor = ""; // text already submitted speculatively (guards double-send)
    // Pre-roll ring buffer: ALWAYS keep the last ~350 ms of non-echo mic PCM.
    // When the VAD opens an utterance (~250 ms sustain delay) we replay this
    // first, so the first 2-3 words are never eaten by the open latency.
    const PRE_ROLL_LEN = Math.floor(16000 * 0.35); // 350 ms @ 16 kHz
    let preRoll = new Float32Array(PRE_ROLL_LEN);
    let preRollPos = 0;
    let preRollLen = 0;
    const preRollPush = (arr) => {
      for (let i = 0; i < arr.length; i++) {
        preRoll[preRollPos] = arr[i];
        preRollPos = (preRollPos + 1) % PRE_ROLL_LEN;
        if (preRollLen < PRE_ROLL_LEN) preRollLen += 1;
      }
    };
    const preRollRead = () => {
      if (!preRollLen) return null;
      const out = new Float32Array(preRollLen);
      const start = preRollLen === PRE_ROLL_LEN ? preRollPos : 0;
      for (let i = 0; i < preRollLen; i++) out[i] = preRoll[(start + i) % PRE_ROLL_LEN];
      return out;
    };
    const preRollClear = () => { preRollLen = 0; };

    const asrSendJson = (obj) => {
      const ws = asrWsRef.current;
      if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
    };
    const asrSendPcm = () => {
      // Server-VAD mode makes the browser a dumb continuous streamer: flush
      // whenever the socket is open, EVEN before Silero opens an utterance.
      // streamingRef only turns true on the server's vad_start, which cannot
      // arrive until the server has HEARD audio — gating the flush on it here
      // deadlocks the whole path (no PCM sent -> Silero never opens -> no
      // vad_start -> no transcription at all).
      const canStream = streamingRef.current || serverMode;
      // During a decode (asrBusy) the server worker is busy but still QUEUES
      // incoming PCM — in server mode keep flushing so the first words of the
      // user's next sentence are never dropped (the server's Silero pre-roll
      // covers the seam). Only the legacy client-VAD path pauses while a
      // final is on its way.
      const notBusy = serverMode || !asrBusyRef.current;
      if (pcmLen && canStream && asrOpenRef.current && notBusy) {
        const joined = new Float32Array(pcmLen);
        let o = 0;
        for (const p of pcmBuf) {
          joined.set(p, o);
          o += p.length;
        }
        try {
          asrWsRef.current.send(joined.buffer);
        } catch { /* socket closed mid-flush — reconnect handles it */ }
      }
      pcmBuf = [];
      pcmLen = 0;
    };

    const connectAsr = () => {
      const ws = new WebSocket(ASR_URL);
      ws.binaryType = "arraybuffer";
      asrWsRef.current = ws;
      ws.onopen = () => {
        asrOpenRef.current = true;
        asrClosedCount = 0;
        asrAttempts = 0;
        asrLastPong = Date.now();
        // opt into server-side Silero VAD (the server then owns open/close)
        if (serverMode) asrSendJson({ type: "mode", vad: "server" });
        // heartbeat: detect a dead ASR socket in ~15s
        asrHb = setInterval(() => {
          try {
            ws.send(JSON.stringify({ type: "ping" }));
          } catch { /* closed — onclose handles it */ }
          if (Date.now() - asrLastPong > 15000) {
            try { ws.close(); } catch { /* noop */ }
          }
        }, 5000);
      };
      ws.onclose = () => {
        asrOpenRef.current = false;
        asrBusyRef.current = false;
        streamingRef.current = false;
        pcmBuf = [];
        pcmLen = 0;
        if (asrHb) { clearInterval(asrHb); asrHb = 0; }
        if (listeningRef.current && !closingAsr) {
          asrClosedCount += 1;
          asrAttempts += 1;
          // reconnect immediately (bounded) so a momentary server restart or
          // network blip doesn't leave the mic open and silent.
          const delay = Math.min(CFG.wsReconnectMs * 2 ** Math.min(asrAttempts - 1, 3), 15000);
          setTimeout(connectAsr, delay);
          // transient indicator while we're down — clearer than a silent mic.
          if (asrAttempts <= 3) {
            setInterim("");
            setAsrReconnecting(true);
          }
          // The /ws/asr endpoint only exists on a server running the current
          // code — tell the user to restart it instead of failing silently,
          // but only after a few reconnect attempts so a transient drop isn't
          // surfaced as a server error.
          if (asrClosedCount >= 3 && !asrWarned) {
            asrWarned = true;
            showError("Cannot connect to the voice engine (Whisper) — please restart the server (python voice_api.py).");
          }
        }
      };
      ws.onmessage = (ev) => {
        let m;
        try {
          m = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (m.type === "pong") { // heartbeat reply
          asrLastPong = Date.now();
          if (asrReconnecting) {
            setAsrReconnecting(false);
            setInterim("");
          }
          return;
        }
        if (m.type === "vad_start") {
          // Server Silero opened an utterance — mirror client state so the
          // legacy hooks (interim, watchdogs) stay coherent.
          streamingRef.current = true;
          vadRef.current.streamingRefCur = true;
          vadRef.current.textHeard = false;
          specSentFor = "";
          setInterim("");
          return;
        }
        if (m.type === "vad_end") {
          // Server closed it: speculative/final transcripts follow next
          streamingRef.current = false;
          vadRef.current.streamingRefCur = false;
          asrBusyRef.current = true;
          return;
        }
        if (m.type === "rejected") {
          // Server dropped the utterance ("speaker" = voiceprint mismatch from
          // the gate, "blip" = too short). Show why, clear any stale caption
          // fallback so it can never fire a phantom turn, release the mic.
          clearTimeout(asrRejTimerRef.current);
          setAsrRejected(m.message || "blip");
          asrRejTimerRef.current = setTimeout(() => setAsrRejected(""), 2500);
          lastPartial = "";
          asrBusyRef.current = false;
          streamingRef.current = false;
          vadRef.current.streamingRefCur = false;
          setInterim("");
          return;
        }
        if (m.type === "partial") {
          // live caption from Whisper; also confirms real speech for barge-in
          const t = (m.text || "").trim();
          if (t) {
            lastPartial = t;
            vadRef.current.textHeard = true;
            setInterim(t);
          }
        } else if (m.type === "speculative") {
          // Fast greedy decode of the finished utterance: start the LLM turn
          // NOW. The authoritative "final" follows and reconciles.
          if (!asrBusyRef.current) return; // stale spec after a watchdog release — ignore
          const t = (m.text || "").trim();
          if (pushActiveRef.current || pushReleasePendingRef.current) {
            // Holding X (or just released, turn assembling): ABSORB the
            // question — it becomes the push turn's text on release instead of
            // firing a screenless reply now.
            if (t) pushTextRef.current = (pushTextRef.current ? pushTextRef.current + " " : "") + t;
            asrBusyRef.current = false;
            specSentFor = "";
            lastPartial = "";
            setInterim("");
            return;
          }
          if (CFG.specChat && t && t.replace(/\s/g, "").length >= CFG.sendMinChars) {
            vadRef.current.textHeard = true;
            setInterim("");
            specSentFor = t;
            lastPartial = ""; // final reconciliation only if no spec turn went out
            asrBusyRef.current = false; // allow the next utterance to open while the final lands
            apiRef.current.submitChat(t);
          }
        } else if (m.type === "final") {
          // short clips can come back empty — fall back to the last live caption
          const t = (m.text || "").trim() || lastPartial;
          lastPartial = "";
          asrBusyRef.current = false;
          streamingRef.current = false;
          if (pushActiveRef.current) {
            // Holding X: absorb the beam final too (replaces/merges with the
            // speculative guess) — no turn until the key comes up.
            if (t) pushTextRef.current = (pushTextRef.current ? pushTextRef.current + " " : "") + t;
            specSentFor = "";
            setInterim("");
            return;
          }
          if (pushReleasePendingRef.current) {
            // X was JUST released but the turn is still assembling (waiting
            // for the first frame). Attach this transcript to the push turn's
            // text instead of firing a separate screenless reply now.
            if (t) pushTextRef.current = (pushTextRef.current ? pushTextRef.current + " " : "") + t;
            specSentFor = "";
            setInterim("");
            return;
          }
          if (specSentFor) {
            // A speculative turn already went out: reconcile only on real divergence.
            const norm = (s) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
            const same = norm(t) === norm(specSentFor);
            const tokensA = new Set(norm(specSentFor).split(/\s+/).filter(Boolean));
            const tokensB = new Set(norm(t).split(/\s+/).filter(Boolean));
            const common = [...tokensA].filter((w) => tokensB.has(w)).length;
            const beamLen = t.replace(/\s/g, "").length;
            const specLen = specSentFor.replace(/\s/g, "").length;
            // Only reconcile UPWARD: the beam may add/correct text the greedy
            // pass missed, but a SHORTER beam guess on a short clip is just
            // noise-vs-noise — resubmitting there barge-ins our own reply.
            const diverged =
              !same &&
              tokensB.size > 0 &&
              beamLen >= specLen &&
              (common / Math.max(1, tokensA.size) < 0.5 || beamLen > specLen * 1.6);
            if (diverged) {
              specSentFor = "";
              setInterim(t);
              apiRef.current.submitChat(t); // beam heard something meaningfully different
            } else {
              specSentFor = ""; // close enough — the speculative reply stands
            }
          } else if (t && t.replace(/\s/g, "").length >= CFG.sendMinChars) {
            vadRef.current.textHeard = true;
            setInterim(t);
            apiRef.current.submitChat(t); // the turn goes out with the real transcript
          } else {
            setInterim("");
          }
        } else if (m.type === "error") {
          asrBusyRef.current = false;
          streamingRef.current = false;
          vadRef.current.streamingRefCur = false; // keep the VAD hold-mirror in sync
          specSentFor = ""; // never let a dead utterance's guard leak into the next one
          if (asrReconnecting) setAsrReconnecting(false);
          setInterim("");
          showError("Speech recognition error: " + (m.message || ""));
        }
      };
    };

    const ticksFor = (ms) => Math.max(1, Math.round(ms / CFG.vadTickMs));

    /* Tap handler: called with 16 kHz Float32 frames whenever the user's mic
       burst is open. While OUR reply is audibly playing (or its tail is still
       ringing out) the frames are dropped — belt-and-suspenders over Chrome's
       AEC so the assistant's own voice can never reach the transcriber. */
    const onFrame = (arr) => {
      const v = vadRef.current;
      const now = performance.now();
      // Always push into rolling pre-roll (350ms of audio) so when the user
      // interrupts (barges in), their initial words are NEVER lost!
      preRollPush(arr);

      if (serverMode) {
        // Server VAD owns turn-taking: stream continuously so Silero can detect speech
        if (!asrOpenRef.current) return;
        pcmBuf.push(arr);
        pcmLen += arr.length;
        return;
      }

      // In client mode, drop frames only while audio is playing and no utterance is open
      const echo = speakingRef.current || (!streamingRef.current && now - v.lastSpeakAt <= CFG.speakTailMs);
      if (echo && !streamingRef.current) {
        return;
      }

      if (tailHold) {
        tailBuf.push(arr); // park tail frames; restored if speech resumes
        return;
      }
      if (!streamingRef.current) return;
      pcmBuf.push(arr);
      pcmLen += arr.length;
    };

    // Leaky-integrator voice metric with hysteresis.
    //
    // The old gate was brittle: one tick below threshold reset the open counter,
    // so a brief mouth noise or a mic-gain pump could kill an utterance that was
    // already mid-word. The new gate smooths short-term RMS into `v.voiceEnergy`
    // and opens only when that smoothed value has been above a *lower* open
    // threshold for vadSustainMs, then HOLDS the mic open down to an even lower
    // hold threshold (hysteresis), so brief dips never steal the next phoneme.
    // Barge-in still uses the original strong-energy path so the assistant can be
    // cut reliably on real sustained speech.
    const vadTick = () => {
      if (!listeningRef.current) return;
      const mic = engine.readMic();
      const v = vadRef.current;
      const now = performance.now();

      // thresholds recomputed per tick so a late /api/config fetch is honored
      const sustainTicks = ticksFor(CFG.vadSustainMs); // real voice energy length
      const textTicks = ticksFor(CFG.vadTextMs); // words + energy confirm
      const failsafeTicks = ticksFor(CFG.vadFailsafeMs); // sustained-energy failsafe

      // smoothed short-term energy (leaky integrator, ~1 s time constant at
      // 50 ms ticks). Keeps momentary dips from resetting the open decision.
      const alpha = 0.08;
      v.voiceEnergy = v.voiceEnergy == null
        ? mic.rms
        : v.voiceEnergy * (1 - alpha) + mic.rms * alpha;

      // hysteresis thresholds are recomputed from the live noise floor each tick
      // so a late /api/config fetch is honored without restarting the mic.
      const openThresh = Math.max(v.noise * CFG.vadGateMult * 0.9, CFG.vadThresholdMin * 0.9);
      const holdThresh = Math.max(v.noise * CFG.vadGateMult * 0.45, CFG.vadThresholdMin * 0.45);
      const strongThresh = v.threshold * 1.6;

      // hot = clearly above the open gate this tick
      const hot = mic.rms > openThresh;
      const inHold = v.streamingRefCur || v.voiceSilentSince > 0
        ? mic.rms > holdThresh : false;
      const sustainedVoice = v.hotTicks >= sustainTicks;

      // Remember when OUR reply is audibly playing — the frame-drop gate in
      // onFrame keys off this deterministic app state.
      if (speakingRef.current) v.lastSpeakAt = now;

      // Assistant-audio gate for server VAD: tell /ws/asr when OUR TTS plays
      // so Silero never opens an utterance on AEC residue of our own voice.
      if (serverMode && speakingRef.current !== prevAssistant) {
        prevAssistant = speakingRef.current;
        asrSendJson({ type: "assistant", active: prevAssistant });
      }

      // Aura: show the user is talking (from the raw mic analyser).
      if (mic.rms > v.noise * 0.8 && mic.rms > CFG.vadNoiseFloor) {
        if (!apiRef.current.userTalkingRef.current) apiRef.current.setUserTalking(true);
      } else if (mic.rms < v.noise * 0.6) {
        if (apiRef.current.userTalkingRef.current) apiRef.current.setUserTalking(false);
      }

      // strong energy (well above the gate) — barge-in path only
      const strong = mic.rms > strongThresh;
      if (hot || (v.streamingRefCur && inHold)) {
        v.hotTicks += 1;
        v.lastUtt = now; // energy-backed speech time (drives end-of-speech)
      } else {
        // do NOT hard-reset while we're holding an open utterance — allow brief
        // dips below the open line but above the hold line
        if (!v.streamingRefCur || mic.rms <= holdThresh) v.hotTicks = Math.max(0, v.hotTicks - 1);
      }
      if (strong) v.strongTicks += 1;
      else v.strongTicks = 0;
      if (sustainedVoice) v.anyVoice = true;

      // voice heard = open energy OR recognizer already delivered words OR we
      // previously latched that real voice existed this burst
      const voiceHeard = sustainedVoice || v.textHeard || v.anyVoice;

      // Ambient noise-floor tracking ONLY while nobody has spoken recently.
      if (!voiceHeard && now - v.lastUtt > CFG.vadRecActiveMs + 200) {
        v.noise = v.noise * 0.998 + mic.rms * 0.002;
        v.threshold = Math.max(v.noise * CFG.vadGateMult, CFG.vadThresholdMin);
      }

      const assistantBusy = speakingRef.current || activeRef.current;
      v.streamingRefCur = streamingRef.current; // used by the hold logic above

      // ---- OPEN an utterance on real sustained voice ------------------
      // (client energy VAD path only — in server mode Silero decides)
      if (!serverMode && sustainedVoice && !streamingRef.current && !asrBusyRef.current && asrOpenRef.current) {
        streamingRef.current = true;
        v.voiceSilentSince = 0;
        v.hotTicks = 0; // reset open-counter once the utterance is open (hold mode)
        specSentFor = ""; // new utterance: drop any stale speculative-turn guard
        asrSendJson({ type: "start" });
        v.recordingSince = now;
        // Replay the pre-roll right after "start" so the ~250 ms the VAD
        // needed to open the utterance is NOT lost from the transcript.
        const pr = preRollRead();
        if (pr) {
          pcmBuf.unshift(pr);
          pcmLen += pr.length;
        }
        preRollClear();
      }

      // ---- BARGE-IN (real sustained speech cuts the assistant) --------
      // Grace window: for ~1.2 s after WE submit a turn, ignore barge-in —
      // the tail of the user's own just-ended utterance (or its echo) can
      // otherwise kill the turn server-side and the reply comes back EMPTY
      // (the mysterious 0-frame replies). Real interrupts still work: 1.2 s
      // is shorter than the first TTS window, and sustained speech AFTER the
      // grace cuts normally.
      const bargeGrace = turnStartRef.current && (performance.now() - turnStartRef.current) < 1200;
      if (assistantBusy && !bargeGrace && !v.bargeLatched) {
        const enough =
          (v.textHeard && v.hotTicks >= textTicks) || v.strongTicks >= failsafeTicks;
        if (enough) {
          v.bargeLatched = true;
          v.lastSpeakAt = 0; // Clear echo tail so speech immediately after barge-in is NOT dropped!
          apiRef.current.hardStop();
          if (serverMode) {
            asrSendJson({ type: "assistant", active: false });
          } else if (!streamingRef.current && asrOpenRef.current) {
            streamingRef.current = true;
            v.voiceSilentSince = 0;
            v.hotTicks = 0;
            specSentFor = "";
            asrSendJson({ type: "start" });
            const pr = preRollRead();
            if (pr) {
              pcmBuf.unshift(pr);
              pcmLen += pr.length;
            }
            preRollClear();
          }
        }
      }
      // latch releases once the user stops producing sound (next burst can cut)
      if (v.bargeLatched && !hot && v.strongTicks === 0) v.bargeLatched = false;

      // ---- END-OF-SPEECH: silence after a real burst closes it ---------
      const recActive = now - v.lastUtt < CFG.vadRecActiveMs;
      // If no speculative transcript arrives shortly after "end" (slow backend
      // or disabled), release the mic anyway so the next burst works.
      if (!streamingRef.current && !asrBusyRef.current && !specSentFor &&
          now - v.uttEndedAt > (CFG.specChat ? 120 : 0)) {
        asrBusyRef.current = false;
        streamingRef.current = false;
      }

      if (!serverMode && streamingRef.current && voiceHeard && !assistantBusy) {
        if (hot || inHold || recActive) {
          if (v.voiceSilentSince) {
            v.voiceSilentSince = 0; // resumed within the silence tail
            asrSendJson({ type: "resume" }); // void any early pre-decode
            if (tailHold) {
              tailHold = false; // resume streaming; restore parked frames first
              pcmBuf.unshift(...tailBuf);
              pcmLen += tailBuf.reduce((n, p) => n + p.length, 0);
              tailBuf = [];
            }
          }
        } else {
          if (!v.voiceSilentSince) {
            v.voiceSilentSince = now;
            // silence just started -> server pre-decodes NOW while this tail
            // counts down; the "end" below then reuses that decode instantly.
            // Stop streaming PCM so the server's decode buffer stays frozen.
            tailHold = true;
            tailBuf = [];
            asrSendJson({ type: "early_end" });
          }
          else if (now - v.voiceSilentSince > CFG.autoSendMs) {
            v.voiceSilentSince = 0;
            v.hotTicks = 0;
            v.textHeard = false;
            v.anyVoice = false;
            v.streamingRefCur = false;
            streamingRef.current = false;
            v.uttEndedAt = now;
            asrBusyRef.current = true;
            tailHold = false; // discard parked tail frames (post-speech silence)
            tailBuf = [];
            asrSendJson({ type: "end" });
            // Watchdog: if neither a speculative nor the final transcript
            // arrives (lost frame/drop), don't leave the mic dead — release
            // after 12 s so the next burst works.
            setTimeout(() => {
              if (asrBusyRef.current) {
                asrBusyRef.current = false;
                streamingRef.current = false;
                v.streamingRefCur = false;
                setInterim("");
              }
            }, 12000);
          }
        }
      }
    };

    const enableMic = async () => {
      const v = vadRef.current;
      serverMode = CFG.asrVadMode === "server"; // re-read config each session
      prevAssistant = false;
      tailHold = false;
      tailBuf = [];
      v.noise = CFG.vadNoiseFloor;
      v.threshold = Math.max(CFG.vadNoiseFloor * CFG.vadGateMult, CFG.vadThresholdMin);
      v.hotTicks = 0;
      v.strongTicks = 0;
      v.textHeard = false;
      v.anyVoice = false;
      v.bargeLatched = false;
      v.voiceSilentSince = 0;
      v.uttEndedAt = 0;
      v.lastUtt = 0;
      v.lastSpeakAt = 0;
      v.voiceEnergy = null;
      v.streamingRefCur = false;
      v.recordingSince = 0;
      streamingRef.current = false;
      asrBusyRef.current = false;
      asrWarned = false;
      lastPartial = "";
      preRollClear(); // fresh pre-roll per listening session — no stale audio
      setInterim("");
      listeningRef.current = true;
      setListening(true);
      rafVad = setInterval(vadTick, CFG.vadTickMs);
      pcmTimer = setInterval(asrSendPcm, 25); // flush mic PCM every 25 ms (was 50 — halves mic-side latency)
      const ok = await engine.startMic(); // AEC-enabled mic (inside the click)
      if (!ok) {
        disableMic();
        showError("Microphone permission denied. Allow mic access in the browser and try again.");
        return;
      }
      connectAsr();
      const tapped = await engine.startTap(onFrame);
      if (!tapped.ok) {
        disableMic();
        const msg =
          tapped.error
            ? `Audio streaming is not available — ${tapped.error}. Try Chrome/Edge.`
            : "Audio streaming is not available in this browser — try Chrome/Edge.";
        showError(msg);
      }
    };

    const disableMic = () => {
      clearInterval(rafVad);
      clearInterval(pcmTimer);
      listeningRef.current = false;
      setListening(false);
      apiRef.current.setUserTalking(false);
      closingAsr = true;
      const ws = asrWsRef.current;
      if (ws) {
        try {
          ws.onclose = null;
          ws.close();
        } catch { /* noop */ }
      }
      asrWsRef.current = null;
      asrOpenRef.current = false;
      asrBusyRef.current = false;
      streamingRef.current = false;
      pcmBuf = [];
      pcmLen = 0;
      tailHold = false;
      tailBuf = [];
      engine.stopTap();
      engine.stopMic();
      setInterim("");
    };

    micToggleRef.current = () => {
      if (listeningRef.current) disableMic();
      else enableMic();
    };
    return () => {
      disableMic();
    };
  }, []);

  /* ---------- Hold X = push-to-see (screen context on demand) ----------
     keydown X starts the capture+warm hold, keyup releases and sends the turn
     with the freshest frame plus anything spoken into the mic while holding.
     Ignored while typing in the input/textarea; window blur releases safely
     (a lost keyup must never leave a stuck hold). */
  useEffect(() => {
    if (!CFG.pushMode) return;
    const isX = (e) => e.key === "x" || e.key === "X";
    const isTyping = () => {
      const el = document.activeElement;
      return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };
    const down = (e) => {
      if (e.repeat || !isX(e) || isTyping()) return;
      e.preventDefault();
      apiRef.current.startPush && apiRef.current.startPush();
    };
    const up = (e) => {
      if (!isX(e) || !apiRef.current.pushActiveRef?.current) return;
      e.preventDefault();
      apiRef.current.releasePush && apiRef.current.releasePush();
    };
    const blur = () => {
      // lost keyup (alt-tab, minimize) — release so the hold can't stick
      if (apiRef.current.pushActiveRef?.current) apiRef.current.releasePush();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, []);

  const sendText = useCallback((event) => {
    event.preventDefault();
    const text = input.trim();
    if (!text) return;
    submitChat(text);
    setInput("");
  }, [input, submitChat]);

  /* ---------- single-screen shell handlers (UI only — voice logic untouched) ---------- */
  const clearChat = useCallback(() => {
    hardStop();
    clearDiagramQueue();
    historyRef.current = [];
    openAssistantId.current = null;
    assistantTextRef.current = "";
    setDiagram(null);
    setStepIndex(0); // fresh lesson timeline
    setFollowLive(true);
    setMessages([{ id: nextId(), role: "assistant", text: GREETING }]);
  }, [hardStop]);

  const handleToggleMic = useCallback(() => {
    apiRef.current.toggleMic && apiRef.current.toggleMic();
  }, []);

  const shareDown = useCallback(() => {
    if (!CFG.pushMode) {
      if (sharingRef.current) stopScreenCapture();
      else startScreenShare();
      return;
    }
    apiRef.current.startPush && apiRef.current.startPush();
  }, [startScreenShare, stopScreenCapture]);

  const shareUp = useCallback(() => {
    if (CFG.pushMode && apiRef.current.pushActiveRef?.current) apiRef.current.releasePush();
  }, []);


  /* ---------- AI-owned desktop: the tutor lays out every window ----------
     The learner has NO window controls (no dock, no drag/resize/close) — the
     OS Director sidecar drives the shell through os_action. Tutor keeps the
     full voice+chat pipeline; Whiteboard/Browser/Notes share context into
     every turn via message.os (see submitChat). */
  const openApp = (id) => {
    focusApp(id);
    if (id === "whiteboard") {
      setFollowLive(true);
      // Explicit open = fullscreen canvas: leave the tile grid first so
      // snap and maximize never fight over the same window.
      setSnaps((p) => {
        if (!p.whiteboard) return p;
        const n = { ...p };
        delete n.whiteboard;
        return n;
      });
      setMaxed((p) => ({ ...p, whiteboard: true })); // canvas is fullscreen
      setStepIndex(Math.max(0, steps.length - 1));
    }
  };
  const codeCtxRef = useRef(null);
  const scheduleLeave = (id, action) => {
    if (leaving[id]) return;
    cancelLeave(id);
    setLeaving((p) => ({ ...p, [id]: action }));
    leaveTimers.current[id] = setTimeout(() => {
      delete leaveTimers.current[id];
      if (action === "close") {
        setOpenApps((prev) => prev.filter((x) => x !== id));
        setSnaps((p) => {
          if (!p[id]) return p;
          const n = { ...p };
          delete n[id];
          return n;
        });
        setMinApps((p) => {
          if (!p[id]) return p;
          const n = { ...p };
          delete n[id];
          return n;
        });
        setMaxed((p) => {
          if (!p[id]) return p;
          const n = { ...p };
          delete n[id];
          return n;
        });
        setWinGeom((p) => {
          if (!p[id]) return p;
          const n = { ...p };
          delete n[id];
          return n;
        });
      } else {
        setMinApps((p) => ({ ...p, [id]: true }));
      }
      setLeaving((p) => {
        const n = { ...p };
        delete n[id];
        return n;
      });
    }, 180);
  };
  const closeApp = (id) => scheduleLeave(id, "close");
  const minimizeApp = (id) => scheduleLeave(id, "min");
  const zoomApp = (id) => {
    // Green zoom always leaves the tile grid: a maximized window owns the
    // screen, a zoomed-out one returns to floating (agent re-tiles it).
    setSnaps((p) => {
      if (!p[id]) return p;
      const n = { ...p };
      delete n[id];
      return n;
    });
    setMinApps((p) => (p[id] ? { ...p, [id]: false } : p));
    setMaxed((p) => ({ ...p, [id]: !p[id] }));
  };
  // ---- Agent OS control: executes validated os_action moves from the OS
  // Director sidecar (open/focus/arrange apps, drive the browser, notes).
  // Plain closure (fresh state every render), exposed via apiRef so the
  // long-lived WS handler always calls the current one. Server allowlists +
  // bounds everything; the client re-validates (defense in depth).
  const agentFlashTimer = useRef(0);
  useEffect(() => () => clearTimeout(agentFlashTimer.current), []);
  // Resubmits (speculative → final) can deliver the same move twice —
  // swallow exact duplicates within 8s (note_add must never double-write).
  const lastAgentSigRef = useRef({ sig: "", ts: 0 });
  const flashAgent = (label) => {
    setAgentFlash({ label, tick: Date.now() });
    clearTimeout(agentFlashTimer.current);
    agentFlashTimer.current = setTimeout(() => setAgentFlash(null), 2600);
  };
  const execOsAction = (action) => {
    if (!action || typeof action.op !== "string") return false;
    const sig = JSON.stringify([action.op, action.app || "", action.zone || "",
      action.target || "", action.title || "", action.body || ""]);
    const nowTs = Date.now();
    if (lastAgentSigRef.current.sig === sig && nowTs - lastAgentSigRef.current.ts < 8000) {
      return true; // duplicate delivery — already executed
    }
    lastAgentSigRef.current = { sig, ts: nowTs };
    const op = action.op;
    const app = AGENT_APPS.includes(action.app) ? action.app : null;
    const needApp = () => {
      if (!app) {
        console.warn("[agent] action missing valid app:", JSON.stringify(action).slice(0, 120));
        return false;
      }
      return true;
    };
    const ensureBrowser = () => {
      // Unconditional: opens if closed, fronts + unminimizes if open (focusApp
      // clears min). The old conditional left navigate running in a minimized
      // window the user couldn't see.
      openApp("browser");
    };
    switch (op) {
      case "open_app":
        if (!needApp()) return false;
        openApp(app);
        flashAgent(`Opened ${AGENT_APP_LABEL[app]}`);
        return true;
      case "focus_app":
        if (!needApp()) return false;
        focusApp(app);
        flashAgent(`${AGENT_APP_LABEL[app]} focused`);
        return true;
      case "close_app":
        if (!needApp()) return false;
        if (app === "browser") setBrowserQueue([]); // stale moves must not fire on next open
        closeApp(app);
        flashAgent(`Closed ${AGENT_APP_LABEL[app]}`);
        return true;
      case "minimize_app":
        if (!needApp()) return false;
        if (!minApps[app]) minimizeApp(app);
        flashAgent(`Minimized ${AGENT_APP_LABEL[app]}`);
        return true;
      case "maximize_app":
        if (!needApp()) return false;
        if (!maxed[app]) zoomApp(app);
        else focusApp(app);
        flashAgent(`Maximized ${AGENT_APP_LABEL[app]}`);
        return true;
      case "restore_app":
        if (!needApp()) return false;
        cancelLeave(app);
        setMinApps((p) => {
          if (!p[app]) return p;
          const n = { ...p };
          delete n[app];
          return n;
        });
        setMaxed((p) => {
          if (!p[app]) return p;
          const n = { ...p };
          delete n[app];
          return n;
        });
        focusApp(app);
        flashAgent(`Restored ${AGENT_APP_LABEL[app]}`);
        return true;
      case "tile_app": {
        if (!needApp()) return false;
        const zone = AGENT_ZONES.includes(action.zone) ? action.zone : null;
        if (!zone) {
          console.warn("[agent] tile_app missing valid zone");
          return false;
        }
        if (!doSnap(app, zone)) return false; // grid full — refused
        flashAgent(`${AGENT_APP_LABEL[app]} → ${AGENT_ZONE_LABEL[zone]}`);
        return true;
      }
      case "tile_grid":
        tileGrid();
        flashAgent("Tiled 2×2 grid");
        return true;
      case "float_app":
        if (!needApp()) return false;
        unsnap(app);
        flashAgent(`${AGENT_APP_LABEL[app]} floated`);
        return true;
      case "browser_navigate": {
        const target = String(action.target || "").trim().slice(0, 500);
        if (!target || /^\s*(javascript|data|vbscript|file|blob)\s*:/i.test(target)) {
          console.warn("[agent] browser_navigate rejected target");
          return false;
        }
        ensureBrowser();
        agentBrowser("navigate", target);
        flashAgent(`Browser → ${target.slice(0, 42)}`);
        return true;
      }
      case "browser_back":
        ensureBrowser();
        agentBrowser("back");
        flashAgent("Browser ← back");
        return true;
      case "browser_forward":
        ensureBrowser();
        agentBrowser("forward");
        flashAgent("Browser → forward");
        return true;
      case "browser_new_tab":
        ensureBrowser();
        agentBrowser("newtab");
        flashAgent("Browser new tab");
        return true;
      case "browser_reload":
        ensureBrowser();
        agentBrowser("reload");
        flashAgent("Browser reloaded");
        return true;
      case "browser_close_tab":
        if (!openApps.includes("browser")) return true; // nothing to close
        agentBrowser("closetab");
        flashAgent("Browser tab closed");
        return true;
      case "code_create":
      case "code_write":
      case "code_edit": {
        const path = String(action.path || "").trim();
        if (!path) {
          console.warn("[agent] code action missing path");
          return false;
        }
        openApp("code");
        agentCode(op, action);
        flashAgent(op === "code_create" ? `File ${path.slice(0, 32)} created`
          : op === "code_write" ? `Code → ${path.slice(0, 32)}`
          : `Edited ${path.slice(0, 32)}`);
        return true;
      }
      case "note_add": {
        const n = {
          id: `n${Date.now()}`,
          title: String(action.title || "Untitled").trim().slice(0, 80) || "Untitled",
          body: String(action.body || "").slice(0, 2000),
        };
        setNotes((prev) => [n, ...prev]);
        setActiveNoteId(n.id);
        focusApp("notes");
        flashAgent("Note added");
        return true;
      }
      case "clear_board":
        // Displayed board only — staged/in-flight chalk still lands after,
        // so a mid-turn clear can't strand the explanation.
        setDiagram(null);
        setStepIndex(0);
        setFollowLive(true);
        setDiagramFocus(null);
        flashAgent("Board cleared");
        return true;
      default:
        console.warn("[agent] unknown op:", op);
        return false;
    }
  };
  // MenuBar carries no window/app actions — the tutor owns every move.
  const menuAction = (action) => {
    if (action === "clear-chat") clearChat();
  };
  const addNote = () => {
    const n = { id: `n${Date.now()}`, title: "Untitled", body: "" };
    setNotes((prev) => [n, ...prev]);
    setActiveNoteId(n.id);
  };
  const updateNote = (id, patch) =>
    setNotes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)));
  const deleteNote = (id) =>
    setNotes((prev) => {
      const next = prev.filter((n) => n.id !== id);
      if (activeNoteId === id) setActiveNoteId(next[0]?.id || null);
      return next;
    });
  /* ---------- Tutor: browse a lesson; the AI teaches it ----------
     How realtime tutoring works here (same pipeline as any question):
     submitChat(text) -> WS /ws/tts -> LLM streams Hinglish-Devenagari reply
     -> TTS windows stream audio blobs -> client plays them in order ->
     diagram sidecar streams board deltas keyed by audio window ->
     flushed exactly when that window's speech plays (audio-synced board).
     There is no "Start learning" control: the learner asks for a topic and the
     OS Director sidecar (server-side) opens + tiles the apps that teach it. */
  const selectLesson = (courseId, moduleId, lessonId) => {
    setSelectedLesson({ courseId, moduleId, lessonId });
  };
  const completeLesson = (courseId, moduleId, lessonId, advance = false) => {
    const course = getCourseById(courseId) || COURSE;
    const flat = course.modules?.flatMap((m) => (m.lessons || []).map((l) => ({ courseId: course.id, moduleId: m.id, ...l }))) || [];
    const i = flat.findIndex((l) => l.id === lessonId);
    setCompletedLessonIds((prev) => (prev.includes(lessonId) ? prev : [...prev, lessonId]));
    if (advance && i >= 0 && i < flat.length - 1) {
      const n = flat[i + 1];
      setActiveLessonId(n.id);
      setSelectedLesson({ courseId: n.courseId, moduleId: n.moduleId, lessonId: n.id });
    } else if (!advance && i >= 0 && i < flat.length - 1 && lessonId === activeLessonId) {
      // Completing the active lesson advances the "in progress" marker too.
      const n = flat[i + 1];
      setActiveLessonId(n.id);
      setSelectedLesson({ courseId: n.courseId, moduleId: n.moduleId, lessonId: n.id });
    }
  };
  // Single AI response for the notch HUD: the newest assistant message
  // (streams live — messages update per text event). User bubbles are gone.
  const latestAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].text;
    }
    return "";
  }, [messages]);
  // Boot to fullscreen: the OS should own the whole screen like a real OS.
  // Browsers grant fullscreen only on user gesture, so try on load (works
  // in kiosk/allowlisted contexts) and retry on clicks/keys until entry is
  // confirmed. Esc exits — and the next press anywhere on the OS goes
  // fullscreen again.
  useEffect(() => {
    let entered = false;
    const arm = () => {
      window.addEventListener("pointerdown", enter);
      window.addEventListener("keydown", enter);
    };
    const disarm = () => {
      window.removeEventListener("pointerdown", enter);
      window.removeEventListener("keydown", enter);
    };
    const onChange = () => {
      if (document.fullscreenElement) {
        entered = true;
        disarm();
      } else if (entered) {
        entered = false;
        arm(); // Esc'd out — re-arm so the next press returns to fullscreen
      }
    };
    const enter = () => {
      if (document.fullscreenElement) return;
      try {
        const p = document.documentElement.requestFullscreen?.();
        if (p && typeof p.catch === "function") p.catch(() => {});
      } catch { /* needs a gesture — the next click/key retries */ }
    };
    document.addEventListener("fullscreenchange", onChange);
    arm();
    enter();
    return () => {
      disarm();
      document.removeEventListener("fullscreenchange", onChange);
    };
  }, []);

  /* ---------- UI: Bug OS desktop ---------- */
  return (
    <div
      className="os-wallpaper photo relative h-screen overflow-hidden text-slate-900"
      onMouseMove={(e) => {
        // Fullscreen chrome: reveals ONLY on a true hot-edge push (top ~5px),
        // hides once the pointer leaves the chrome zone (~96px).
        if (maximized) {
          if (e.clientY < 5) setTopChrome(true);
          else if (e.clientY > 96 && topChrome) setTopChrome(false);
        }
        else if (topChrome) setTopChrome(false);
      }}
    >
      {/* Diwali lights first: below every sibling, above wallpaper only. */}
      <div className="os-lights os-lights-a" aria-hidden="true" />
      <div className="os-lights os-lights-b" aria-hidden="true" />
      <MenuBar
        activeApp={activeApp}
        connected={connected}
        speaking={speaking}
        listening={listening}
        typing={typing}
        clock={clock}
        date={dateStr}
        hidden={maximized && !topChrome}
        onAction={menuAction}
      />
      <Widgets />
      <ProgressWidget days={dayStats} noteCount={notes.length} boardSteps={steps.length} />

      <div className={`absolute inset-x-0 bottom-1 ${maximized && !topChrome ? "top-0" : "top-9"} ${maximized ? "px-0" : "px-2 sm:px-4"}`}>
        <div className="relative h-full w-full">
        {openApps.map((winId) =>
          minApps[winId] && !leaving[winId] ? null : (
          /* Click-through layer: only the window box itself is hittable, so a
             behind window stays clickable through empty desktop area. */
          <div
            key={winId}
            className="pointer-events-none absolute inset-0"
            style={{ zIndex: zFor(winId) }}
          >
        {winId === "whiteboard" && (
          <AppWindow
            title="Green Board"
            geom={geomFor("whiteboard")}
            maximized={!!maxed.whiteboard}
            snap={snaps.whiteboard}
            cascade={openApps.indexOf("whiteboard")}
            leaving={leaving.whiteboard}
            hideChrome={!!maxed.whiteboard && !topChrome}
          >
            <div className="min-h-0 flex-1 overflow-hidden rounded-b-[18px] bg-[#143626]">
              {/* Single continuous board: flat revealed elements; the camera
                  follows new drawing while Live, manual zoom keeps your view. */}
              <ErrorBoundary appName="Green Board">
              <TutorBoard
                elements={diagram?.elements || []}
                focus={diagramFocus}
                followLive={followLive}
                onFollowChange={setFollowLive}
                caption={latestAssistant}
                wiping={wiping}
              />
              </ErrorBoundary>
            </div>
          </AppWindow>
        )}

        {winId === "browser" && (
          <AppWindow
            title="Browser"
            geom={geomFor("browser")}
            maximized={!!maxed.browser}
            snap={snaps.browser}
            cascade={openApps.indexOf("browser")}
            leaving={leaving.browser}
            hideChrome={!!maxed.browser && !topChrome}
          >
            <div className="min-h-0 flex-1 p-3 pt-1">
              <ErrorBoundary appName="Browser">
              <BrowserApp url={browserUrl} onNavigate={onBrowserNavigate} queue={browserQueue} onAck={ackBrowser} />
              </ErrorBoundary>
            </div>
          </AppWindow>
        )}

        {winId === "notes" && (
          <AppWindow
            title="Notes"
            geom={geomFor("notes")}
            maximized={!!maxed.notes}
            snap={snaps.notes}
            cascade={openApps.indexOf("notes")}
            leaving={leaving.notes}
            hideChrome={!!maxed.notes && !topChrome}
          >
            <div className="min-h-0 flex-1 p-3 pt-1">
              <ErrorBoundary appName="Notes">
              <NotesApp
                notes={notes}
                activeId={activeNoteId || notes[0]?.id}
                onSelect={setActiveNoteId}
                onChange={updateNote}
                onAdd={addNote}
                onDelete={deleteNote}
              />
              </ErrorBoundary>
            </div>
          </AppWindow>
        )}
        {winId === "code" && (
          <AppWindow
            title="Code"
            geom={geomFor("code")}
            maximized={!!maxed.code}
            snap={snaps.code}
            cascade={openApps.indexOf("code")}
            leaving={leaving.code}
            hideChrome={!!maxed.code && !topChrome}
          >
            <div className="min-h-0 flex-1">
              <ErrorBoundary appName="Code">
              <CodeApp
                onContext={(c) => {
                  codeCtxRef.current = c;
                }}
                queue={codeQueue}
                onAck={ackCode}
              />
              </ErrorBoundary>
            </div>
          </AppWindow>
        )}
        {winId === "help" && (
          <AppWindow
            title="Help Center"
            geom={geomFor("help")}
            maximized={!!maxed.help}
            snap={snaps.help}
            cascade={openApps.indexOf("help")}
            leaving={leaving.help}
            hideChrome={!!maxed.help && !topChrome}
          >
            <div className="min-h-0 flex-1 p-3 pt-1">
              <ErrorBoundary appName="Help Center">
              <HelpApp />
              </ErrorBoundary>
            </div>
          </AppWindow>
        )}
        {winId === "tutor" && (
          <AppWindow
            title="Tutor — Courses"
            geom={geomFor("tutor")}
            maximized={!!maxed.tutor}
            snap={snaps.tutor}
            cascade={openApps.indexOf("tutor")}
            leaving={leaving.tutor}
            hideChrome={!!maxed.tutor && !topChrome}
          >
            <div className="min-h-0 flex-1 p-3 pt-1">
              <ErrorBoundary appName="Tutor">
              <TutorApp
                courses={COURSES}
                progress={courseProgress}
                activeCourseId={activeCourseId}
                activeLessonId={activeLessonId}
                selected={selectedLesson}
                onSelect={selectLesson}
                onCompleteLesson={completeLesson}
              />
              </ErrorBoundary>
            </div>
          </AppWindow>
        )}
          </div>
        ))}
        </div>
      </div>

      {/* Tutor lives in the notch — voice agent background, no popup.
          Auto-collapses its expanded panel when any app window opens;
          the notch pill itself always stays visible. */}
      <NotchHUD
        hidden={visibleApps.length > 0}
        connected={connected}
        speaking={speaking}
        turnActive={turnActive}
        listening={listening}
        userTalking={userTalking}
        typing={typing}
        interim={interim}
        input={input}
        setInput={setInput}
        sendText={sendText}
        onToggleMic={handleToggleMic}
        onStop={hardStop}
        onShareDown={shareDown}
        onShareUp={shareUp}
        sharing={sharing}
        visionEnabled={CFG.visionEnabled}
        llmProvider={llmProvider}
        llmProviders={llmProviders}
        llmModels={llmModels}
        onProvider={setLlmProvider}
        response={latestAssistant}
        asrReady={asrReady}
        asrRejected={asrRejected}
        onClear={clearChat}
      />

      {/* Agent move indicator: transient pill, the only desktop status the
          learner sees — the tutor is arranging their screen right now. */}
      {agentFlash && (
        <div className="pointer-events-none absolute inset-x-0 bottom-6 z-40 flex justify-center" aria-live="polite">
          <span className="animate-window-in rounded-full bg-black/70 px-3.5 py-1.5 text-xs font-semibold whitespace-nowrap text-white shadow-lg backdrop-blur">
            ✨ Agent · {agentFlash.label}
          </span>
        </div>
      )}
      {/* ── Boot splash: logo + staged loading, fades out smoothly ── */}
      {!bootGone && (
        <div
          className={`absolute inset-0 z-[200] flex flex-col items-center justify-center text-slate-900 transition-opacity duration-500 ${
            booting ? "opacity-100" : "pointer-events-none opacity-0"
          }`}
          style={{
            backgroundColor: "#ffffff",
            backgroundImage:
              "linear-gradient(rgba(15,23,42,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.06) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
          }}
          aria-hidden={!booting}
          aria-label="Loading Bug OS"
        >
          <img src="/logo.png" alt="Bug OS" className="h-16 w-16 rounded-2xl border border-slate-200 object-cover shadow-[0_12px_40px_rgba(255,90,95,0.35)]" />
          <p className="mt-4 text-lg font-bold tracking-tight">Bug OS</p>
          <p className="mt-1 text-xs text-slate-500">Hindi voice tutor desktop</p>
          <div className="mt-6 h-1 w-56 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-[#ff5a5f] transition-all duration-300"
              style={{ width: `${((bootStage + 1) / BOOT_STAGES.length) * 100}%` }}
            />
          </div>
          <p className="mt-3 text-xs font-semibold text-slate-600" aria-live="polite">{BOOT_STAGES[bootStage]?.label}…</p>
          <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-500">
            {["tutor", "whiteboard", "browser", "code", "notes"].map((a) => {
              const ready = (BOOT_STAGES[bootStage]?.apps || []).includes(a);
              return (
                <span
                  key={a}
                  className={`flex items-center gap-1 rounded-full px-2 py-1 ring-1 transition ${
                    ready ? "bg-red-50 text-slate-800 ring-[#ff5a5f]/40" : "bg-white text-slate-400 ring-slate-200"
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${ready ? "bg-[#ff5a5f]" : "bg-slate-300"}`} />
                  {a === "tutor" ? "Tutor" : a === "whiteboard" ? "Green Board" : a[0].toUpperCase() + a.slice(1)}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
