import {
  FaClock,
  FaComments,
  FaDesktop,
  FaMicrophone,
  FaTrash,
  FaWandMagicSparkles,
  FaXmark,
} from "react-icons/fa6";

export default function Sidebar({
  open,
  onClose,
  width,
  connected,
  listening,
  asrReady,
  messageCount,
  hasDiagram,
  onClear,
  onToggleMic,
  onShareScreen,
  sharing,
  visionEnabled,
  llmProvider,
  llmProviders,
  llmModels,
  onProvider,
}) {
  const status = connected
    ? listening
      ? asrReady
        ? "Listening"
        : "Warming up"
      : "Ready"
    : "Connecting";
  const providers = Array.isArray(llmProviders) && llmProviders.length ? llmProviders : ["groq"];
  const modelOf = (p) => (llmModels && llmModels[p]) || (p === "deepseek" ? "deepseek-chat" : "groq");

  return (
    <aside
      className="z-30 flex h-full shrink-0 flex-col border-r border-slate-200/80 bg-white max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:w-72 max-md:shadow-2xl md:w-[var(--sidebar-w)]"
      style={{ "--sidebar-w": `${width}px` }}
      aria-label="Tutor sidebar"
      aria-hidden={!open}
    >
      <div className="flex items-center justify-between px-5 pt-6 pb-5">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#ff5a5f] text-white shadow-[0_10px_26px_rgba(255,90,95,0.35)]">
            <FaWandMagicSparkles className="h-4 w-4" />
          </span>
          <div>
            <h1 className="text-sm font-bold tracking-[0.12em] text-slate-900 uppercase">Tutor</h1>
            <p className="mt-0.5 text-[11px] text-slate-500">Hindi voice tutor</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          aria-label="Close sidebar"
        >
          <FaXmark className="h-4 w-4" />
        </button>
      </div>

      <div className="mx-5 flex items-center gap-2 rounded-2xl bg-slate-50 px-3.5 py-2.5 text-xs font-medium text-slate-600">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${connected ? "bg-emerald-500" : "bg-amber-500"}`}
        />
        {status}
        {hasDiagram && (
          <span className="ml-auto rounded-full bg-[#ff5a5f]/10 px-2 py-0.5 text-[10px] font-bold text-[#ff5a5f]">
            BOARD LIVE
          </span>
        )}
      </div>

      <nav className="mt-4 flex flex-col gap-1 px-3" aria-label="Tutor actions">
        {/* LLM provider toggle: groq <-> deepseek (per-turn, server falls back) */}
        <div className="mb-1 rounded-xl bg-slate-50 p-1.5" aria-label="LLM provider">
          <p className="px-1.5 pb-1 text-[10px] font-bold tracking-[0.12em] text-slate-400 uppercase">
            AI Provider
          </p>
          <div className="grid grid-cols-2 gap-1">
            {["groq", "deepseek"].map((p) => {
              const available = providers.includes(p);
              const active = llmProvider === p;
              return (
                <button
                  key={p}
                  onClick={() => available && onProvider && onProvider(p)}
                  disabled={!available}
                  title={available ? modelOf(p) : `${p} API key not set in .env`}
                  className={`rounded-lg px-2 py-1.5 text-xs font-bold capitalize transition ${
                    active
                      ? "bg-[#ff5a5f] text-white shadow-sm"
                      : available
                        ? "text-slate-600 hover:bg-white hover:text-[#ff5a5f]"
                        : "cursor-not-allowed text-slate-300"
                  }`}
                >
                  {p}
                </button>
              );
            })}
          </div>
          <p className="truncate px-1.5 pt-1 text-[10px] text-slate-400" title={modelOf(llmProvider || "groq")}>
            {modelOf(llmProvider || "groq")}
          </p>
        </div>
        <button
          onClick={onToggleMic}
          className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-[#ff5a5f]/5 hover:text-[#ff5a5f]"
        >
          <FaMicrophone className="h-4 w-4 text-[#ff5a5f]" />
          {listening ? "Stop listening" : "Start listening"}
        </button>
        <button
          onClick={onShareScreen}
          disabled={!visionEnabled}
          className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-[#ff5a5f]/5 hover:text-[#ff5a5f] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <FaDesktop className="h-4 w-4 text-[#ff5a5f]" />
          {sharing ? "Stop screen share" : "Share screen"}
          <span className="ml-auto rounded-md border border-dashed border-slate-300 px-1.5 py-0.5 text-[10px] font-bold text-slate-400">
            X
          </span>
        </button>
        <button
          onClick={onClear}
          className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-[#ff5a5f]/5 hover:text-[#ff5a5f]"
        >
          <FaTrash className="h-4 w-4 text-[#ff5a5f]" />
          Clear chat
        </button>
      </nav>

      <div className="mt-auto border-t border-slate-200/70 px-5 py-4">
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <FaComments className="h-3.5 w-3.5 text-[#ff5a5f]" />
          {messageCount} messages this session
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
          <FaClock className="h-3.5 w-3.5" />
          Hold X to show your screen, release to ask
        </div>
      </div>
    </aside>
  );
}
