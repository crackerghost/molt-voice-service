import { useState } from "react";
import { FaWifi, FaBatteryFull } from "react-icons/fa6";

const APP_META = {
  tutor: { name: "Tutor" },
  whiteboard: { name: "Green Board" },
  code: { name: "Code" },
  browser: { name: "Browser" },
  notes: { name: "Notes" },
};

// The learner has no window/app control — the tutor opens, arranges and closes
// every window through os_action. The only menu left is chat housekeeping.
const MENUS = {
  Chat: ["clear-chat"],
};

const ACTION_LABEL = {
  "clear-chat": "Clear Chat",
};

/* macOS menu bar: bug menu, app menus, centered notch, status icons right.
   Hidden (slid away) in fullscreen until the pointer hits the top edge. */
export default function MenuBar({ activeApp, connected, speaking, listening, typing, clock, date, hidden, onAction }) {
  const [openMenu, setOpenMenu] = useState(null);
  const [showAbout, setShowAbout] = useState(false);
  const meta = APP_META[activeApp] || { name: "Bug OS" };
  const status = typing
    ? "Thinking…"
    : speaking
      ? "Speaking…"
      : listening
        ? "Listening…"
        : connected
          ? "Ready"
          : "Connecting…";

  const fire = (action) => {
    setOpenMenu(null);
    if (action === "about") {
      setShowAbout(true);
      return;
    }
    onAction && onAction(action);
  };

  return (
    <>
      <div className={`pointer-events-auto absolute inset-x-0 top-0 z-50 flex h-9 items-center gap-1 border-b border-slate-200 bg-white px-3 text-[13px] font-medium text-slate-900 transition-transform duration-200 ${hidden ? "-translate-y-full" : "translate-y-0"}`}>
        <button
          onClick={() => setOpenMenu(openMenu === "bug" ? null : "bug")}
          aria-label="Bug OS menu"
          className={`rounded-md p-0.5 transition hover:bg-black/10 ${openMenu === "bug" ? "bg-black/10" : ""}`}
        >
          <img src="/logo.png" alt="Bug OS" className="h-5 w-5 rounded-[6px] object-cover" />
        </button>
        {openMenu === "bug" && (
          <div className="absolute left-2 top-9 min-w-44 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-2xl">
            <button
              onClick={() => fire("about")}
              className="block w-full rounded-lg px-3 py-1.5 text-left text-[13px] transition hover:bg-[#0a84ff] hover:text-white"
            >
              About Bug OS
            </button>
          </div>
        )}
        <span className="px-1 font-bold">{meta.name}</span>
        {Object.keys(MENUS).map((menu) => (
          <div key={menu} className="relative hidden sm:block">
            <button
              onClick={() => setOpenMenu(openMenu === menu ? null : menu)}
              className={`rounded-md px-2 py-0.5 transition hover:bg-black/10 ${openMenu === menu ? "bg-black/10" : ""}`}
            >
              {menu}
            </button>
            {openMenu === menu && (
              <div className="absolute left-0 top-8 min-w-44 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-2xl">
                {MENUS[menu].map((a) => (
                  <button
                    key={a}
                    onClick={() => fire(a)}
                    className="block w-full rounded-lg px-3 py-1.5 text-left text-[13px] transition hover:bg-[#0a84ff] hover:text-white"
                  >
                    {ACTION_LABEL[a]}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {/* notch */}
        <div className="pointer-events-none absolute left-1/2 top-0 h-6 w-44 -translate-x-1/2 rounded-b-2xl bg-black" aria-hidden="true" />
        <span className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-1.5 md:flex">
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-600" : "bg-amber-500"}`} />
            <span className="text-slate-700">{status}</span>
          </span>
          <FaBatteryFull className="text-slate-800" aria-label="Battery" />
          <FaWifi className="text-slate-800" aria-label="Wi-Fi" />
          <span className="tabular-nums text-slate-800">{date} {clock}</span>
        </span>
      </div>
      {openMenu && (
        <div className="absolute inset-0 z-40" onClick={() => setOpenMenu(null)} aria-hidden="true" />
      )}
      {showAbout && (
        <div className="absolute inset-0 z-50 flex items-center justify-center" onClick={() => setShowAbout(false)}>
          <div
            className="w-72 rounded-[22px] border border-slate-200 bg-white p-6 text-center shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <img src="/logo.png" alt="Bug OS logo" className="mx-auto h-14 w-14 rounded-2xl object-cover shadow-md" />
            <p className="mt-2 text-lg font-bold text-slate-900">Bug OS</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Hindi voice tutor desktop.
              <br />The tutor drives every window for you.
            </p>
            <button
              onClick={() => setShowAbout(false)}
              className="mt-4 rounded-full bg-slate-900 px-4 py-1.5 text-xs font-bold text-white"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export { APP_META };
