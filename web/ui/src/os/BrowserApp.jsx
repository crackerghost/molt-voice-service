import { useEffect, useRef, useState } from "react";
import {
  FaArrowLeft, FaArrowRight, FaRotateRight, FaHouse, FaLock,
  FaMagnifyingGlass, FaPlus, FaXmark, FaArrowUpRightFromSquare,
} from "react-icons/fa6";

const GOOGLE_HOME = "https://www.google.com/webhp?igu=1";
const NEWTAB = "bugos:newtab";

const favicon = (domain) => `https://www.google.com/s2/favicons?sz=64&domain=${domain}`;

function toUrl(raw) {
  const t = (raw || "").trim();
  if (!t) return GOOGLE_HOME;
  if (/^https?:\/\//i.test(t)) return t;
  if (/^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(t) && !t.includes(" ")) return `https://${t}`;
  return `https://www.google.com/search?q=${encodeURIComponent(t)}&igu=1`;
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "New tab";
  }
}

/* Search-only browser: this window is a Google search surface. Hosts that
 * forbid embedding (YouTube home/search/channels send
 * `X-Frame-Options: SAMEORIGIN`) can never render in an <iframe>, so they
 * get a graceful fallback (open externally) instead of a blank page. */
function blockedHost(url) {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "").replace(/^m\./, "").toLowerCase();
    if (host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be") {
      return host;
    }
  } catch { /* not a URL */ }
  return null;
}

function frameTarget(url) {
  if (blockedHost(url)) return { blocked: true };
  return { src: url };
}

let tabSeq = 1;
const makeTab = (url) => ({ id: `t${tabSeq++}`, history: [url || GOOGLE_HOME], idx: 0, reload: 0 });

/* Professional tabbed browser: toolbar, omnibox, tabs, new-tab page.
   Active-tab URL (+ tab count) is shared upward so the tutor sees what you
   browse. `queue` ([{cmd, target, seq}]) executes imperative moves from the
   agent (navigate/back/forward/newtab/reload/closetab/home) — IN ORDER, each
   seq exactly once. A queue (not a single object) is required: the director
   can emit several browser moves in one turn and same-ms ticks would
   otherwise collapse them into one (new tab opened, navigate never ran). */
export default function BrowserApp({ url, onNavigate, queue, onAck }) {
  const cleanInitial = url && url !== NEWTAB ? url : GOOGLE_HOME;
  const [tabs, setTabs] = useState(() => [makeTab(cleanInitial)]);
  const [activeId, setActiveId] = useState(() => "t1");
  // Never leak the internal "bugos:newtab" id into the omnibox (it used to
  // happen on remount and broke hero search: submit navigated the literal id).
  const [draft, setDraft] = useState(() => (url && url !== NEWTAB ? url : ""));
  const [hero, setHero] = useState("");

  // Ref mirror so agent commands always act on the LATEST tabs even when
  // several land inside one React batch (setState updaters stay pure — all
  // reporting happens outside them).
  const stateRef = useRef({ tabs: null, activeId: "t1" });
  stateRef.current = { tabs, activeId };

  const report = (next, id) => {
    const t = next.find((x) => x.id === id) || next[0];
    onNavigate(t.history[t.idx], { tabs: next.length });
  };

  const applyTabs = (next, id) => {
    setTabs(next);
    setActiveId(id);
    const t = next.find((x) => x.id === id) || next[0];
    const u = t.history[t.idx];
    setDraft(u === NEWTAB ? "" : u);
    report(next, id);
  };

  const snapshot = () => {
    const { tabs: ts, activeId: aid } = stateRef.current;
    const list = ts && ts.length ? ts : tabs;
    const a = list.find((t) => t.id === aid) || list[0];
    return { list, active: a };
  };

  const navigate = (raw) => {
    const target = toUrl(raw);
    const { list, active } = snapshot();
    const next = list.map((t) =>
      t.id === active.id
        ? { ...t, history: [...t.history.slice(0, t.idx + 1), target], idx: t.idx + 1 }
        : t,
    );
    applyTabs(next, active.id);
  };

  const goBack = () => {
    const { list, active } = snapshot();
    if (active.idx <= 0) return;
    const next = list.map((t) => (t.id === active.id ? { ...t, idx: t.idx - 1 } : t));
    applyTabs(next, active.id);
  };

  const goFwd = () => {
    const { list, active } = snapshot();
    if (active.idx >= active.history.length - 1) return;
    const next = list.map((t) => (t.id === active.id ? { ...t, idx: t.idx + 1 } : t));
    applyTabs(next, active.id);
  };

  const reload = () => {
    const { list, active } = snapshot();
    setTabs(list.map((t) => (t.id === active.id ? { ...t, reload: t.reload + 1 } : t)));
  };

  const goHome = () => navigate(GOOGLE_HOME);

  const addTab = () => {
    const t = makeTab(NEWTAB);
    const { list } = snapshot();
    setHero("");
    applyTabs([...list, t], t.id);
  };

  const closeTab = (e, id) => {
    e?.stopPropagation?.();
    const { list, active } = snapshot();
    const target = id || active.id;
    if (list.length === 1) {
      const fresh = [makeTab(NEWTAB)];
      setHero("");
      applyTabs(fresh, fresh[0].id);
      return;
    }
    const next = list.filter((t) => t.id !== target);
    const cur = next[next.length - 1];
    applyTabs(next, target === active.id ? cur.id : active.id);
  };

  const switchTab = (id) => {
    const { list } = snapshot();
    const t = list.find((x) => x.id === id);
    if (!t) return;
    setActiveId(id);
    const u = t.history[t.idx];
    setDraft(u === NEWTAB ? "" : u);
    report(list, id);
  };

  // Agent command queue: drain in order, each seq once (doneRef = idempotent
  // even if the effect re-fires), then ack so App drops it from the queue.
  const doneRef = useRef(new Set());
  useEffect(() => {
    if (!queue || !queue.length) return;
    if (doneRef.current.size > 500) doneRef.current.clear();
    for (const c of queue) {
      if (!c || c.seq == null || doneRef.current.has(c.seq)) continue;
      doneRef.current.add(c.seq);
      if (c.cmd === "navigate" && c.target) navigate(c.target);
      else if (c.cmd === "back") goBack();
      else if (c.cmd === "forward") goFwd();
      else if (c.cmd === "newtab") addTab();
      else if (c.cmd === "reload") reload();
      else if (c.cmd === "closetab") closeTab(null, c.target || undefined);
      else if (c.cmd === "home") goHome();
      try { onAck && onAck(c.seq); } catch { /* noop */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue]);

  // Render-time view of the active tab (handlers above use the ref mirror).
  const active = tabs.find((t) => t.id === activeId) || tabs[0];
  const current = active.history[active.idx];
  const canBack = active.idx > 0;
  const canFwd = active.idx < active.history.length - 1;
  const frame = current === NEWTAB ? null : frameTarget(current);

  const submit = (e) => {
    e?.preventDefault();
    if (current === NEWTAB && !draft.trim() && hero.trim()) navigate(hero);
    else if (draft.trim()) navigate(draft);
  };

  const iconBtn =
    "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-600 transition hover:bg-slate-900/5 disabled:opacity-30";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* tab strip */}
      <div className="flex shrink-0 items-end gap-1 px-1 pt-1">
        <div className="flex min-w-0 flex-1 items-end gap-1 overflow-x-auto">
          {tabs.map((t) => {
            const u = t.history[t.idx];
            const isNew = u === NEWTAB;
            const on = t.id === activeId;
            return (
              <button
                key={t.id}
                onClick={() => switchTab(t.id)}
                title={isNew ? "New tab" : u}
                className={`flex max-w-44 min-w-0 items-center gap-1.5 rounded-t-xl px-3 py-1.5 text-xs font-medium transition ${
                  on ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:bg-white/50"
                }`}
              >
                {isNew ? (
                  <FaPlus className="h-3 w-3 shrink-0" />
                ) : (
                  <img
                    src={favicon(hostOf(u))}
                    alt=""
                    className="h-3.5 w-3.5 shrink-0 rounded-sm"
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                    }}
                  />
                )}
                <span className="truncate">{isNew ? "New tab" : hostOf(u)}</span>
                <span
                  role="button"
                  aria-label="Close tab"
                  onClick={(e) => closeTab(e, t.id)}
                  className="rounded-full p-0.5 transition hover:bg-slate-900/10"
                >
                  <FaXmark className="h-3 w-3" />
                </span>
              </button>
            );
          })}
        </div>
        <button onClick={addTab} aria-label="New tab" title="New tab" className={`${iconBtn} mb-0.5`}>
          <FaPlus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* toolbar */}
      <div className="os-glass flex shrink-0 items-center gap-1 rounded-2xl px-2 py-1.5">
        <button onClick={goBack} disabled={!canBack} aria-label="Back" title="Back" className={iconBtn}>
          <FaArrowLeft className="h-3.5 w-3.5" />
        </button>
        <button onClick={goFwd} disabled={!canFwd} aria-label="Forward" title="Forward" className={iconBtn}>
          <FaArrowRight className="h-3.5 w-3.5" />
        </button>
        <button onClick={reload} aria-label="Reload" title="Reload" className={iconBtn}>
          <FaRotateRight className="h-3.5 w-3.5" />
        </button>
        <button onClick={goHome} aria-label="Home" title="Home (Google)" className={iconBtn}>
          <FaHouse className="h-3.5 w-3.5" />
        </button>
        <form
          onSubmit={submit}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-full bg-white/70 px-3 py-1.5 shadow-inner"
        >
          <FaLock className="h-3 w-3 shrink-0 text-emerald-600" />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onFocus={(e) => e.target.select()}
            aria-label="Address bar"
            placeholder="Search Google or type a URL"
            className="min-w-0 flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
          />
          {draft.trim() && (
            <button
              type="submit"
              aria-label="Go"
              className="rounded-full bg-slate-900 p-1.5 text-white transition hover:bg-slate-700"
            >
              <FaMagnifyingGlass className="h-3 w-3" />
            </button>
          )}
        </form>
        {current !== NEWTAB && (
          <a
            href={current}
            target="_blank"
            rel="noreferrer"
            aria-label="Open in new tab"
            title="Open in new tab"
            className={iconBtn}
          >
            <FaArrowUpRightFromSquare className="h-3.5 w-3.5" />
          </a>
        )}
      </div>

      {/* page */}
      <div className="relative mt-2 min-h-0 flex-1 overflow-hidden rounded-2xl border border-white/50 bg-white shadow-sm">
        {current === NEWTAB ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 overflow-y-auto bg-gradient-to-b from-white to-slate-100 p-6">
            <p className="text-4xl font-bold tracking-tight">
              <span className="text-[#4285F4]">B</span>
              <span className="text-[#EA4335]">u</span>
              <span className="text-[#FBBC05]">g</span>
              <span className="ml-2 text-slate-700">Search</span>
            </p>
            <form onSubmit={submit} className="flex w-full max-w-md items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 shadow-md">
              <FaMagnifyingGlass className="h-4 w-4 shrink-0 text-slate-400" />
              <input
                value={hero}
                onChange={(e) => setHero(e.target.value)}
                aria-label="Search the web"
                placeholder="Search Google…"
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-800 outline-none"
              />
            </form>
            <p className="max-w-md text-center text-xs leading-5 text-slate-400">
              Search-only browser — results open here. A page that refuses to load
              can be opened externally with ↗.
            </p>
          </div>
        ) : frame?.blocked ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 bg-slate-50 p-6 text-center">
            <p className="text-sm font-bold text-slate-900">This site blocks embedding</p>
            <p className="max-w-sm text-xs leading-5 text-slate-500">
              This page refuses to load inside the search browser — open it in a
              real tab instead.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <a
                href={current}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 rounded-xl bg-[#ff5a5f] px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:brightness-95"
              >
                Open externally <FaArrowUpRightFromSquare className="h-3 w-3" />
              </a>
              <button
                onClick={goBack}
                disabled={!canBack}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-600 transition hover:border-slate-300 disabled:opacity-40"
              >
                Go back
              </button>
            </div>
          </div>
        ) : (
          <iframe
            key={`${active.id}-${active.idx}-${active.reload}`}
            src={frame.src}
            title="Browser"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-presentation"
            className="h-full w-full border-0 bg-white"
          />
        )}
      </div>
      <p className="mt-1 truncate px-1 text-[11px] text-slate-500">
        {current === NEWTAB
          ? "New tab — type above to search."
          : (
            <>
              Tutor sees: <span className="font-medium text-slate-700">{current}</span>
              <span className="text-slate-400"> · blank page? the site blocks embedding — use ↗</span>
            </>
          )}
      </p>
    </div>
  );
}
