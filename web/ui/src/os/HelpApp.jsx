import { useMemo, useState } from "react";
import {
  FaMicrophone, FaDesktop, FaWindowMaximize, FaGlobe, FaNoteSticky,
  FaCode, FaChalkboardUser, FaCircleQuestion, FaKeyboard,
  FaTriangleExclamation, FaMagnifyingGlass, FaBolt,
} from "react-icons/fa6";

/* Help Center: every voice command + how to use Bug OS, in one place.
   Pure presentational (no props) — the tutor opens it on "open help center".
   Content mirrors the real agent allowlist (server/llm/os_control.py). */

const CATS = [
  { id: "start", label: "Getting started", icon: <FaBolt /> },
  { id: "voice", label: "Voice commands", icon: <FaMicrophone /> },
  { id: "apps", label: "Apps guide", icon: <FaDesktop /> },
  { id: "windows", label: "Windows & tiles", icon: <FaWindowMaximize /> },
  { id: "keys", label: "Shortcuts", icon: <FaKeyboard /> },
  { id: "fix", label: "Troubleshooting", icon: <FaTriangleExclamation /> },
];

const COMMANDS = [
  { say: "open tutor / start html lesson", does: "Opens Tutor courses + starts voice learning", cat: "voice" },
  { say: "open browser", does: "Opens the Browser", cat: "voice" },
  { say: "open YouTube / show Python docs", does: "Opens Browser + loads site / Google search", cat: "voice" },
  { say: "open a new tab", does: "New browser tab", cat: "voice" },
  { say: "go back / go forward", does: "Browser back / forward", cat: "voice" },
  { say: "reload the page", does: "Reloads the current page", cat: "voice" },
  { say: "close the tab", does: "Closes the current browser tab", cat: "voice" },
  { say: "open notes / write this in notes", does: "Opens Notes / writes a note for you", cat: "voice" },
  { say: "open green board / clear the board", does: "Opens / clears the lesson board", cat: "voice" },
  { say: "open code", does: "Opens the Code editor", cat: "voice" },
  { say: "write code / create a file / edit the code", does: "Tutor writes code into the editor + previews it", cat: "voice" },
  { say: "open help center", does: "Opens this Help Center", cat: "voice" },
  { say: "show side by side / make a grid", does: "Tiles windows (2 halves / 2x2 grid)", cat: "voice" },
  { say: "close / minimize / maximize it", does: "Close / minimize / fullscreen the front app", cat: "voice" },
  { say: "why is this error here? (while showing screen)", does: "Tutor reads your screen + explains the fix", cat: "voice" },
];

const SECTIONS = {
  start: {
    title: "Getting started",
    icon: <FaBolt />,
    body: [
      ["1. Ask anything", "Press the mic and speak, or type below and hit Enter. The tutor answers in Hinglish voice and draws on the board as it speaks."],
      ["2. Show your screen", "PRESS AND HOLD the screen button (or X) for 1–2 seconds, then release — the tutor answers looking at your screen. Errors, code, websites — all work."],
      ["2b. Start a lesson", "Just say the topic — “HTML सिखाओ”, “flexbox समझाओ”, “React lesson शुरू करो”. The tutor opens the Green Board, Code editor and Browser itself and starts teaching by voice."],
      ["3. Interrupt anytime", "Just start speaking while the tutor is talking — it stops immediately (barge-in). No need to ask again."],
      ["4. Learn with apps", "While teaching, the tutor opens and arranges the Browser, Notes, Code and Green Board itself. You never have to move a window — just ask in plain words."],
      ["5. Any language", "Commands work in Hindi, English, Hinglish plus Spanish, French, German, Portuguese, Tamil, Telugu, Kannada, Malayalam, Bengali and Marathi — just speak naturally. Replies stay in Hinglish voice."],
    ],
  },
  apps: {
    title: "Apps guide",
    icon: <FaDesktop />,
    body: [
      ["Green Board — lesson board", "Diagrams appear in chalk as the tutor speaks. Use Prev / Next to step through, ● Live to jump back to live. “Clear the board” wipes it clean."],
      ["Tutor — courses", "Left sidebar lists all courses → modules → lessons with search. Tap a lesson to preview its plan; ask for it in a sentence to have the tutor teach it."],
      ["Browser — web search", "Search-only browser: tabs, back/forward, reload plus a Google-search omnibox. Pages that block embedding show a fallback — open them in a real tab with ↗."],
      ["Notes — auto-saved", "Every note saves instantly. Say “write this in notes” and the tutor creates the note for you."],
      ["Code — editor + live preview", "Monaco editor with folders, a Run button, and Preview + Console on the right. Edits refresh the preview live; console output lands below."],
      ["Help Center — this app", "Every command and trick lives here. Say “open help center” and the tutor opens it."],
    ],
  },
  windows: {
    title: "Windows & tiles",
    icon: <FaWindowMaximize />,
    body: [
      ["The tutor owns the desktop", "There is no dock and no window buttons — you can't move, resize or close a window, and you don't need to. The tutor opens, tiles and closes apps for you as it teaches."],
      ["Ask for a layout", "Say “browser kholo”, “side by side dikhao”, “make a grid”, “close the notes”, “fullscreen the board” — the tutor arranges it and tells you what it did."],
      ["Automatic layout while teaching", "On a teaching turn the tutor opens the board by itself and puts the Code editor or Browser beside it when the topic needs them."],
      ["A small pill confirms each move", "When the tutor rearranges your screen, a short “✨ Agent · …” pill appears so you know what just happened."],
    ],
  },
  keys: {
    title: "Shortcuts",
    icon: <FaKeyboard />,
    body: [
      ["X (hold)", "Push-to-see: hold to capture your screen, release and the tutor answers looking at it."],
      ["Enter", "Send a typed question."],
      ["Esc", "Exit fullscreen."],
      ["Mic button", "Start / stop speaking. Speak while the tutor talks = interrupt."],
    ],
  },
  fix: {
    title: "Troubleshooting",
    icon: <FaTriangleExclamation />,
    body: [
      ["No answer coming", "Use Chrome / Edge, allow mic permission, and check /api/config shows asr_ready. First run downloads models (~1 min)."],
      ["Tutor hears itself", "Use headphones or lower the speaker — the browser echo-canceller only locks in then."],
      ["Blank page in Browser", "The site blocked embedding — open it in a real tab with the ↗ button. The tutor can see the URL, not the page text."],
      ["Tutor asks to share screen", "Use push-to-see: hold the button, then release. Questions without a frame carry no screen context."],
      ["Misheard speech (ASR)", "Speak a little slowly and clearly; tiny “yeah / ok” clips are sometimes skipped — use a full sentence."],
    ],
  },
};

const APP_ICON = {
  "Green Board": <FaChalkboardUser className="text-amber-600" />,
  Browser: <FaGlobe className="text-blue-600" />,
  Notes: <FaNoteSticky className="text-yellow-600" />,
  Code: <FaCode className="text-violet-600" />,
  Help: <FaCircleQuestion className="text-emerald-600" />,
};

export default function HelpApp() {
  const [cat, setCat] = useState("start");
  const [q, setQ] = useState("");

  const cmdResults = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return COMMANDS;
    return COMMANDS.filter(
      (c) => c.say.toLowerCase().includes(needle) || c.does.toLowerCase().includes(needle),
    );
  }, [q]);

  const section = SECTIONS[cat];
  const showCommands = cat === "voice" || q.trim();

  return (
    <div className="flex h-full min-h-0 gap-3">
      {/* category rail */}
      <div className="os-glass flex w-44 shrink-0 flex-col gap-1 rounded-2xl p-2">
        <p className="px-2 pt-1 pb-2 text-[11px] font-bold tracking-wider text-slate-500 uppercase">
          Help Center
        </p>
        {CATS.map((c) => (
          <button
            key={c.id}
            onClick={() => { setCat(c.id); }}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${
              cat === c.id && !q.trim()
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:bg-white/60"
            }`}
          >
            <span className="text-sm">{c.icon}</span>
            {c.label}
          </button>
        ))}
        <div className="mt-auto rounded-xl bg-emerald-50 px-3 py-2 text-[11px] leading-5 text-emerald-800">
          Tip: just say <span className="font-bold">“open help center”</span> — the tutor opens this app.
        </div>
      </div>

      {/* content */}
      <div className="os-glass flex min-w-0 flex-1 flex-col rounded-2xl p-4">
        <div className="mb-3 flex shrink-0 items-center gap-2 rounded-full bg-white/70 px-4 py-2 shadow-inner">
          <FaMagnifyingGlass className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search commands"
            placeholder="Search commands… e.g. ‘tab’, ‘notes’, ‘screen’"            className="min-w-0 flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {showCommands && (
            <div className="mb-5">
              <p className="mb-2 text-[11px] font-bold tracking-wider text-slate-500 uppercase">
                Voice commands {q.trim() ? `(${cmdResults.length})` : `(${COMMANDS.length})`}
              </p>
              {cmdResults.length === 0 && (
                <p className="rounded-xl bg-white/60 px-3 py-4 text-xs text-slate-500">
                  Nothing found — try “browser”, “notes” or “screen”.
                </p>
              )}
              {cmdResults.map((c) => (
                <div
                  key={c.say}
                  className="mb-1.5 flex flex-col gap-0.5 rounded-xl bg-white/70 px-3 py-2 shadow-sm sm:flex-row sm:items-center sm:gap-3"
                >
                  <span className="shrink-0 rounded-lg bg-slate-900 px-2.5 py-1 font-mono text-[11px] font-bold text-white">
                    “{c.say}”
                  </span>
                  <span className="text-xs text-slate-600">{c.does}</span>
                </div>
              ))}
            </div>
          )}

          {!q.trim() && section && (
            <div>
              <p className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-900">
                <span className="text-base text-slate-500">{section.icon}</span>
                {section.title}
              </p>
              {section.body.map(([h, p]) => (
                <div key={h} className="mb-1.5 rounded-xl bg-white/70 px-3 py-2.5 shadow-sm">
                  <p className="text-xs font-bold text-slate-900">{h}</p>
                  <p className="mt-0.5 text-xs leading-5 text-slate-600">{p}</p>
                </div>
              ))}
              {cat === "apps" && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.keys(APP_ICON).map((a) => (
                    <span
                      key={a}
                      className="flex items-center gap-1.5 rounded-full bg-white/70 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm"
                    >
                      {APP_ICON[a]} {a}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
