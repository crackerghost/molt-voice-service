import { useEffect, useRef, useState } from "react";
import {
  FaChevronDown, FaDesktop, FaMicrophone, FaPaperPlane,
  FaPause, FaStop, FaTrash, FaXmark,
} from "react-icons/fa6";
import { engine } from "../audioEngine.js";

/* NotchHUD — the tutor lives in the OS notch, not in a window.
   Collapsed: a slim black notch pill with a live aura orb (same voice-driven
   motion as the old gradient) + status. Hover the top edge or click to pin:
   a professional glass panel drops down with the aura, play/pause (mic),
   interrupt (stop), hold-to-share screen, a chat input, and the SINGLE latest
   AI response (streaming). No sidebar, no chat transcript. */

const AURA_BG =
  "radial-gradient(circle at 30% 30%, #ffd6e0 0%, transparent 45%)," +
  "radial-gradient(circle at 70% 25%, #c4b5fd 0%, transparent 50%)," +
  "conic-gradient(from 120deg, #ff5a5f, #b388ff, #67e8f9, #ff8fab, #ff5a5f)";

function statusOf({ connected, listening, speaking, turnActive, typing, userTalking, asrReady }) {
  if (typing) return "Thinking…";
  if (speaking || turnActive) return "Speaking…";
  if (listening) return !asrReady ? "Warming up…" : userTalking ? "Hearing you…" : "Listening…";
  return connected ? "Ready" : "Connecting…";
}

export default function NotchHUD({
  hidden, connected, speaking, turnActive, listening, userTalking, typing,
  interim, input, setInput, sendText,
  onToggleMic, onStop, onShareDown, onShareUp, sharing, visionEnabled,
  llmProvider, llmProviders, llmModels, onProvider,
  response, asrReady, asrRejected, onClear,
}) {
  const [pinned, setPinned] = useState(false);
  const [hover, setHover] = useState(false);
  const [focused, setFocused] = useState(false);
  const orbRef = useRef(null);
  const miniRef = useRef(null);
  const wrapRef = useRef(null);
  const open = pinned || hover || focused;
  const status = statusOf({ connected, listening, speaking, turnActive, typing, userTalking, asrReady });
  // Auto-collapse: when any app window opens (`hidden` from App.jsx), collapse
  // the expanded panel if it was open — the notch pill itself always stays.
  useEffect(() => {
    if (hidden) {
      setPinned(false);
      setHover(false);
    }
  }, [hidden]);
  // Outside click: collapse the expanded panel. The notch pill stays.
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setPinned(false);
        setHover(false);
        setFocused(false);
        if (document.activeElement && document.activeElement.blur) {
          try { document.activeElement.blur(); } catch { /* noop */ }
        }
      }
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  }, [open]);
  const providers = Array.isArray(llmProviders) && llmProviders.length ? llmProviders : ["groq"];

  // Live aura: same voice-driven motion as the old gradient, heavy low-pass
  // so it drifts instead of jittering. Drives both the notch orb and panel.
  useEffect(() => {
    let raf = 0;
    let lvl = 0.05;
    const draw = () => {
      const mic = engine.readMic();
      const spk = engine.readSpeak();
      const active = speaking || (listening && userTalking);
      const raw = Math.min(
        1,
        Math.max(
          speaking ? spk.rms * 9 : 0,
          listening && userTalking ? mic.rms * 11 : 0,
          listening ? mic.rms * 6 + 0.05 : 0.04,
        ),
      );
      lvl += (raw - lvl) * 0.06;
      const t = performance.now() / 1000;
      const breathe = Math.sin(t * 2.1) * 0.05;
      // Panel orb gets the full motion; the mini notch orb is capped so it
      // never outgrows the pill's padding (no top/bottom clipping).
      const orb = orbRef.current;
      if (orb) {
        const s = 1 + lvl * 0.85 + breathe;
        orb.style.transform = `scale(${s.toFixed(3)}) rotate(${(t * 14).toFixed(1)}deg)`;
        orb.style.opacity = active ? String(Math.min(1, 0.75 + lvl * 0.25)) : "0.6";
      }
      const mini = miniRef.current;
      if (mini) {
        const s = 1 + lvl * 0.32 + breathe * 0.5;
        mini.style.transform = `scale(${s.toFixed(3)}) rotate(${(t * 14).toFixed(1)}deg)`;
        mini.style.opacity = active ? String(Math.min(1, 0.75 + lvl * 0.25)) : "0.6";
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [listening, speaking, userTalking]);

  return (
    <>
      {/* hover strip: drift to the notch at the very top edge and the panel
          appears; leaving it collapses (moving into the notch/panel
          re-asserts open). Narrow (just wider than the notch pill) so
          hovering window title bars or the menu bar never opens the panel —
          ONLY the notch area triggers it. z-100: always above windows, dock
          and menu bar — never hidden. */}
      <div
        className="absolute top-0 left-1/2 z-[100] h-8 w-80 -translate-x-1/2"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        aria-hidden="true"
      />
      <div ref={wrapRef} className="pointer-events-none absolute inset-x-0 top-0 z-[101] flex flex-col items-center">
        {/* the notch itself — click pins/unpins the panel */}
        <button
          onClick={() => setPinned((v) => !v)}
          onMouseEnter={() => setHover(true)}
          aria-label={open ? "Collapse tutor" : "Expand tutor"}
          aria-expanded={open}
          className="pointer-events-auto flex h-8 w-72 items-center gap-2.5 overflow-visible rounded-b-md bg-black/95 px-4 shadow-[0_10px_36px_rgba(0,0,0,0.45)] backdrop-blur transition hover:bg-black"
        >
          <span className="relative flex h-6 w-6 shrink-0 items-center justify-center overflow-visible p-0.5">
            <span
              ref={miniRef}
              className="block h-5 w-5 rounded-full"
              style={{ background: AURA_BG }}
              aria-hidden="true"
            />
          </span>
          <span className="min-w-0 flex-1 truncate text-left text-[11px] font-semibold tracking-wide text-white/85">
            {status}
          </span>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${connected ? "bg-emerald-400" : "bg-amber-400"}`} aria-hidden="true" />
          <FaChevronDown className={`h-2.5 w-2.5 shrink-0 text-white/50 transition-transform duration-300 ${open ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>

        {/* drop-down professional panel */}
        <div
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          className={`pointer-events-auto w-[min(420px,calc(100vw-2rem))] origin-top overflow-hidden rounded-[26px] border border-white/10 bg-[#0b0b10]/92 text-white shadow-[0_30px_90px_rgba(0,0,0,0.55)] backdrop-blur-2xl transition-all duration-300 ${
            open ? "mt-2 max-h-[70vh] scale-100 opacity-100" : "mt-0 max-h-0 scale-95 opacity-0"
          }`}
          aria-hidden={!open}
        >
          <div className="flex items-center gap-3 px-4 pt-3.5">
            <span className="relative flex h-12 w-12 shrink-0 items-center justify-center">
              <span className="absolute inset-0 rounded-full bg-white/5" aria-hidden="true" />
              <span
                ref={orbRef}
                className="block h-9 w-9 rounded-full"
                style={{ background: AURA_BG, filter: "blur(1px) saturate(1.25)" }}
                aria-hidden="true"
              />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold tracking-wide">{status}</p>
              <p className="truncate text-[11px] text-white/50">
                {llmProvider === "deepseek" ? (llmModels?.deepseek || "deepseek") : (llmModels?.groq || "groq")}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-0.5 rounded-full bg-white/8 p-0.5" role="group" aria-label="AI provider">
              {["groq", "deepseek"].map((p) => {
                const available = providers.includes(p);
                const active = llmProvider === p;
                return (
                  <button
                    key={p}
                    onClick={() => available && onProvider && onProvider(p)}
                    disabled={!available}
                    title={available ? p : `${p} key not set`}
                    className={`rounded-full px-2.5 py-1 text-[10px] font-bold capitalize transition ${
                      active ? "bg-[#ff5a5f] text-white" : available ? "text-white/60 hover:text-white" : "cursor-not-allowed text-white/25"
                    }`}
                  >
                    {p === "groq" ? "Groq" : "DeepSeek"}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => { onClear && onClear(); }}
              title="Clear chat"
              aria-label="Clear chat"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white/50 transition hover:bg-white/10 hover:text-white"
            >
              <FaTrash className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => { setPinned(false); setHover(false); }}
              aria-label="Collapse"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white/50 transition hover:bg-white/10 hover:text-white"
            >
              <FaXmark className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* single AI response — the only text surface */}
          <div className="px-4 pt-2.5" aria-live="polite">
            <div className="max-h-52 min-h-16 overflow-y-auto rounded-2xl bg-white/6 px-3.5 py-3">
              {asrRejected ? (
                <p className="text-xs font-semibold text-amber-300">{asrRejected}</p>
              ) : interim ? (
                <>
                  <p className="mb-1 text-[10px] font-bold tracking-[0.14em] text-[#ff8f96] uppercase">You’re saying…</p>
                  <p className="text-sm leading-6 text-white/85">{interim}</p>
                </>
              ) : typing && !response ? (
                <p className="text-sm text-white/45">Tutor is thinking<span className="animate-pulse">…</span></p>
              ) : response ? (
                <p className="text-sm leading-6 whitespace-pre-wrap text-white/90">{response}</p>
              ) : (
                <p className="text-sm text-white/45">Tap the mic and ask — I’ll answer here and draw on the board.</p>
              )}
            </div>
          </div>

          {/* controls: play/pause mic, interrupt, share, input, send */}
          <form onSubmit={sendText} className="flex items-center gap-1.5 px-3 pt-2.5 pb-3.5">
            <button
              type="button"
              onClick={onToggleMic}
              title={listening ? "Pause listening" : "Play — start listening"}
              aria-label={listening ? "Pause listening" : "Start listening"}
              className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition active:scale-95 ${
                listening ? "bg-white text-slate-900" : "bg-[#ff5a5f] text-white shadow-[0_8px_24px_rgba(255,90,95,0.5)]"
              }`}
            >
              {listening ? <FaPause className="h-3.5 w-3.5" /> : <FaMicrophone className="h-4 w-4" />}
            </button>
            {speaking && (
              <button
                type="button"
                onClick={onStop}
                title="Interrupt the tutor"
                aria-label="Interrupt"
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white/80 transition hover:bg-white/20 active:scale-95"
              >
                <FaStop className="h-3.5 w-3.5" />
              </button>
            )}
            <button
              type="button"
              onPointerDown={(e) => { e.preventDefault(); onShareDown && onShareDown(); }}
              onPointerUp={() => onShareUp && onShareUp()}
              onPointerLeave={() => onShareUp && onShareUp()}
              onContextMenu={(e) => e.preventDefault()}
              disabled={!visionEnabled}
              title="Hold to share your screen"
              aria-label="Share screen"
              className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-30 ${
                sharing ? "bg-[#ff5a5f] text-white" : "bg-white/10 text-white/70 hover:bg-white/20"
              }`}
            >
              <FaDesktop className="h-3.5 w-3.5" />
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              placeholder={speaking ? "Speaking… type to interrupt" : "Ask or hold X to show screen…"}
              aria-label="Message the tutor"
              className="min-h-10 flex-1 rounded-full bg-white/10 px-4 text-sm text-white outline-none placeholder:text-white/40 focus:bg-white/15"
            />
            <button
              type="submit"
              disabled={!input.trim() || !connected}
              aria-label="Send message"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#ff5a5f] text-white shadow-[0_8px_24px_rgba(255,90,95,0.5)] transition hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FaPaperPlane className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
