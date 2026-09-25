import { FaDesktop, FaMicrophone, FaPaperPlane, FaStop } from "react-icons/fa6";

/* Dark voice dock for mic, screen-share, text input, and send. */

export default function BottomBar({
  input,
  setInput,
  sendText,
  connected,
  listening,
  micBusy,
  speaking,
  sharing,
  visionEnabled,
  onToggleMic,
  onShareDown,
  onShareUp,
}) {
  return (
    <div className="sticky bottom-0 z-20 px-4 pt-2 pb-4 sm:px-6">
      <div className="relative overflow-hidden rounded-[28px] bg-[#050505] shadow-[0_18px_60px_rgba(5,5,10,0.5)]">
        <form
          onSubmit={sendText}
          className="relative z-10 flex items-center gap-1.5 px-3 py-3"
        >
          <button
            type="button"
            onPointerDown={(e) => {
              e.preventDefault();
              onShareDown && onShareDown();
            }}
            onPointerUp={() => onShareUp && onShareUp()}
            onPointerLeave={() => onShareUp && onShareUp()}
            onContextMenu={(e) => e.preventDefault()}
            disabled={!visionEnabled}
            title="Hold to share your screen"
            className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full backdrop-blur transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-35 ${
              sharing ? "bg-[#ff5a5f] text-white" : "bg-white/10 text-white/70 hover:bg-white/20 hover:text-white"
            }`}
          >
            <FaDesktop className="h-4 w-4" />
            <span className="sr-only">Share screen</span>
          </button>
          <button
            type="button"
            onClick={onToggleMic}
            disabled={micBusy}
            title={listening ? "Stop listening" : "Start listening"}
            className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 ${
              listening ? "bg-white text-slate-900" : "bg-[#ff5a5f]"
            }`}
          >
            {micBusy ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : listening ? (
              <FaStop className="h-4 w-4" />
            ) : (
              <FaMicrophone className="h-4 w-4" />
            )}
            <span className="sr-only">{listening ? "Stop listening" : "Start listening"}</span>
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={speaking ? "Speaking… type to interrupt" : "Ask your tutor…"}
            aria-label="Message the tutor"
            className="min-h-11 flex-1 rounded-full bg-white/10 px-4 text-sm text-white outline-none backdrop-blur placeholder:text-white/50 focus:bg-white/15"
          />
          <button
            type="submit"
            disabled={!input.trim() || !connected}
            aria-label="Send message"
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#ff5a5f] text-white shadow-[0_10px_24px_rgba(255,90,95,0.45)] transition hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FaPaperPlane className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
