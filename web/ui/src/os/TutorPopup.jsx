/* Floating tutor companion: voice + chat reachable from any app.
   Appears while the tutor is active; pin it to keep it always on screen. */

export default function TutorPopup({
  open, pinned, onTogglePin, onOpenTutor,
  speaking, listening, typing, interim, input, setInput, sendText, connected,
  onToggleMic, micBusy,
}) {
  if (!open && !pinned) return null;
  const line = typing
    ? "Tutor is thinking…"
    : speaking
      ? "Speaking…"
      : listening
        ? "Listening…"
        : interim || "Tutor ready";
  return (
    <div className="os-glass absolute right-4 bottom-20 z-40 w-[300px] rounded-[22px] p-3 shadow-2xl" role="complementary" aria-label="Tutor companion">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xl" aria-hidden="true">🐞</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-bold text-slate-900">Bug Tutor</p>
          <p className="truncate text-[11px] text-slate-500">{line}</p>
        </div>
        <button
          onClick={onTogglePin}
          title={pinned ? "Unpin companion" : "Pin companion"}
          className={`rounded-full px-2 py-1 text-[11px] font-bold transition ${pinned ? "bg-slate-900 text-white" : "bg-white/60 text-slate-600 hover:bg-white"}`}
        >
          {pinned ? "📌" : "📍"}
        </button>
        <button
          onClick={onOpenTutor}
          title="Open Tutor app"
          className="rounded-full bg-white/60 px-2 py-1 text-[11px] font-bold text-slate-700 transition hover:bg-white"
        >
          ⤢
        </button>
      </div>
      {interim ? (
        <p className="mb-2 truncate rounded-xl bg-white/60 px-3 py-2 text-xs text-slate-600">
          {interim}
        </p>
      ) : null}
      <form
        onSubmit={sendText}
        className="flex items-center gap-1.5"
      >
        <button
          type="button"
          onClick={onToggleMic}
          disabled={micBusy}
          aria-label={listening ? "Stop listening" : "Start listening"}
          className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white transition active:scale-95 disabled:opacity-40 ${listening ? "bg-slate-900" : "bg-[#ff5a5f]"}`}
        >
          {listening ? "■" : "🎙"}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask…"
          aria-label="Ask the tutor"
          className="min-w-0 flex-1 rounded-full bg-white/60 px-3 py-2 text-xs text-slate-800 outline-none placeholder:text-slate-400"
        />
        <button
          type="submit"
          disabled={!input.trim() || !connected}
          aria-label="Send"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-slate-700 disabled:opacity-40"
        >
          ➤
        </button>
      </form>
    </div>
  );
}
