"""Agent OS control: the tutor drives the desktop (apps, browser, tiles).

Architecture mirrors the diagram watcher: the voice stream stays pure
(Devanagari-only, no tool calls). A per-turn sidecar planner (the OS
Director) reads the user text + OS snapshot and emits validated window
actions that stream to the client as {"type": "os_action"} — best-effort,
never blocks voice. The client executes them against its window manager.

Safety: allowlisted ops/apps/zones, bounded strings, max 6 actions/turn,
dangerous URL schemes rejected. The client re-validates everything.
"""

import json
import re
import threading

APPS = ("whiteboard", "browser", "notes", "code", "help", "tutor")
ZONES = ("left", "right", "tl", "tr", "bl", "br")
MAX_ACTIONS = 12

# Ops that need {"app"} / {"app","zone"} / {"target"}.
_APP_OPS = {
    "open_app", "focus_app", "close_app", "minimize_app",
    "maximize_app", "restore_app", "tile_app", "float_app",
}
_BROWSER_OPS = {"browser_back", "browser_forward", "browser_new_tab", "browser_reload", "browser_close_tab"}
_NOARG_OPS = {"tile_grid", "code_run"}
_CODE_OPS = {"code_create", "code_write", "code_edit", "code_open", "code_delete", "code_mkdir", "code_rmdir", "code_search", "code_set_module"}
OPS = _APP_OPS | _BROWSER_OPS | _NOARG_OPS | {"browser_navigate", "note_add", "clear_board"} | _CODE_OPS
# Code payloads ride the same tool call as window moves — give those turns a
# bigger token budget (a teaching-sized file dwarfs the usual 400).
CODE_DIRECTOR_TOKENS = 1500

_DANGEROUS_SCHEME_RE = re.compile(r"^\s*(javascript|data|vbscript|file|blob)\s*:", re.IGNORECASE)

_OS_SEMAPHORE = threading.Semaphore(2)  # one director call per turn max anyway

OS_CONTROL_TOOL = {
    "type": "function",
    "function": {
        "name": "control_os",
        "description": "Drive the tutoring desktop: open/focus/arrange apps, drive the browser, add notes, write code (create/write/edit files).",
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "maxItems": MAX_ACTIONS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": sorted(OPS),
                            },
                            "app": {"type": "string", "enum": list(APPS)},
                            "zone": {"type": "string", "enum": list(ZONES)},
                            "target": {"type": "string", "description": "browser_navigate only: URL or search words."},
                            "title": {"type": "string", "description": "note_add only: note title."},
                            "body": {"type": "string", "description": "note_add only: note body."},
                            "path": {"type": "string", "description": "code_create/write/edit/open/delete only: relative file path like index.html or js/app.js. code_mkdir/rmdir: folder path like css or js."},
                            "content": {"type": "string", "description": "code_create/write only: full file content (create) or replacement/appended code (write). Keep teaching-sized."},
                            "mode": {"type": "string", "enum": ["overwrite", "append"], "description": "code_write only: replace the file (default) or append to it."},
                            "find": {"type": "string", "description": "code_edit only: exact existing snippet to replace (first match)."},
                            "replace": {"type": "string", "description": "code_edit only: replacement snippet."},
                            "query": {"type": "string", "description": "code_search only: text to find across all project files (the studio highlights matches)."},
                            "module": {"type": "string", "enum": ["html_css_js", "mernstack"], "description": "code_set_module only: teaching environment selected for this practical example."},
                        },
                        "required": ["op"],
                    },
                },
            },
            "required": ["actions"],
        },
    },
}

_DIRECTOR_SYSTEM = (
    "You are the OS director for a voice-tutored desktop with six apps: "
    "tutor (course list; the learner previews lessons here), "
    "whiteboard (green board, lesson board), browser (tabbed web), notes, code (editor), "
    "help (help center with every command and how-to). "
    "You are the ONLY agent that can move windows: the learner has NO dock, NO "
    "window buttons, NO drag/resize/close and NO shortcuts — speaking and typing "
    "are their only input. So make every desktop change here yourself, and NEVER "
    "tell the learner to open, close, move or resize a window. "
    "Read the USER request + OS snapshot, then call control_os with the MINIMAL "
    "window actions that fulfill it — usually 1-3, never more than 6, in execution "
    "order. The USER may write in ANY language — "
    "judge by MEANING, never by language or script. Act on two kinds of turn: "
    "(a) the learner asks for an app, a website, docs, a video, a search, a note, "
    "or the help center — or names something to show; "
    "(b) the learner asks you to TEACH a topic that is better shown than told — "
    "for coding, markup, styling, debugging or file topics, first ask whether they "
    "want a practical editor demo. NEVER open or write code until the OS snapshot "
    "says code.practice_allowed is true; an explanation alone is not permission. "
    "When permission is true, open the code editor "
    "(create a small runnable example) and tile it beside the board; when a live "
    "demo, docs page or video teaches it better, open the browser to it. Keep "
    "teaching surfaces to what the topic actually needs. A pure definition, "
    "conceptual question or small-talk turn needs NO action (the whiteboard "
    "appears by itself): return no tool call. browser_navigate opens the browser by itself; "
    "target may be a full URL or plain search words. browser_navigate reuses "
    "the CURRENT tab (it opens the browser by itself); browser_new_tab ONLY "
    "when the learner explicitly asks for a new tab — never open one just to "
    "visit a site. COMPOUND requests finish in ONE call: 'open browser and "
    "search youtube' / 'browser kholo aur youtube dikhao' means browser_navigate "
    "to youtube NOW (it opens the browser by itself — no separate open_app "
    "needed). The named site or search words ARE the target — use them verbatim "
    "as browser_navigate target. NEVER open an empty browser and leave the "
    "search for later, and NEVER split one request across turns. CODE moves "
    "drive the Code editor and open it by themselves: code_set_module must be the "
    "first code move and must choose html_css_js for browser UI, HTML, CSS, DOM and "
    "vanilla JavaScript; choose mernstack when React, Node, Express, MongoDB, an API, "
    "backend, database, auth or full-stack behavior is needed. code_create makes a NEW "
    "file (path like index.html or js/app.js + full content, then it opens in "
    "the editor), code_write replaces (or appends to) a file's content, "
    "code_edit swaps ONE exact snippet (find -> replace, first match wins), "
    "code_open focuses an existing file, code_delete removes one file, "
    "code_mkdir creates a folder, code_rmdir removes a folder tree, "
    "code_search highlights a query across every file, code_run rebuilds the live preview. "
    "For html_css_js frontend scaffolds (counter, todo, landing page, game): emit the full "
    "file set in ONE call — index.html + css/styles.css + js/app.js. Style "
    "with Tailwind utility classes by default (the preview loads the Tailwind "
    "CDN automatically); write REAL custom CSS into css/styles.css as well so "
    "both are connected. Only when the learner explicitly says vanilla/plain "
    "CSS do you skip Tailwind classes and style purely in the CSS file. "
    "For mernstack examples, emit a small client plus server structure and explain "
    "that this classroom preview runs the client only; keep server files visible for teaching. "
    "Keep code teaching-sized and runnable in a plain browser preview (HTML/CSS/"
    "vanilla JS — no imports, no build step, no backend: the preview runs the "
    "frontend only). After code moves, the tutor "
    "should point the learner at the preview. The OS snapshot names the "
    "open code file (code.file) plus the project listing (code.files): when the learner says 'this "
    "code', 'this file', or 'it' without naming a path, use that file for "
    "code_write/code_edit; use code.files to avoid recreating files that exist. lesson is the active curriculum lesson id — "
    "context only, never an action. open_app before acting on a "
    "closed app. Close or minimize a window only when it is in the way or the "
    "learner asked — they cannot restore it themselves. "
    "Reply ONLY via the tool call."
)


def should_direct(text: str) -> bool:
    """Gate: substantive turns only — never greetings/tiny acks."""
    clean = (text or "").strip()
    if len(clean) < 8:
        return False
    try:
        from server.llm.diagrams import _GREETING_ONLY_RE
        if _GREETING_ONLY_RE.search(clean):
            return False
    except Exception:
        pass
    return True


# Blocking path gate: the user is asking FOR a desktop move (open the
# browser, write a note, search something...). Broad on purpose — the
# director LLM is the real judge and returns no tool call when nothing fits.
# Multilingual by design (the director judges MEANING in any language): the
# fast path covers Hindi, English + 10 more (es/fr/de/pt/ta/te/kn/ml/bn/mr)
# with high-precision stems/nouns; every OTHER language still gets its moves
# via the zero-latency background sidecar (only the same-reply narration
# needs the fast path). Pure "what is X?" definitions are excluded so
# teaching turns never pay the blocking call's latency.
_OS_REQUEST_RE = re.compile(
    r"(ब्राउज़र|नोट|टैब|सर्च|खोज|खोल|बंद\s*कर|टाइल|लिखो?|मदद|हेल्प\s*सेंटर|"
    r"ओपन|साफ़?|बोर्ड|व्हाइटबोर्ड|कोड\s*(खोल|दिखा)|"
    r"कोर्स|लेसन|पाठ्यक्रम|पढ़ा|सिखा|ट्यूटर|"
    r"उघड|ब्राउझर|शोध|"
    r"খুল|বন্ধ|ব্রাউজার|নোট|খুঁজ|"
    r"திறக்க|மூடு|உலாவி|குறிப்பு|தேடு|"
    r"తెరువు|మూసి|బ్రౌజర్|గమనిక|వెతకు|శోధన|"
    r"ತೆರೆ|ಮುಚ್ಚು|ಬ್ರೌಸರ್|ಟಿಪ್ಪಣಿ|ಹುಡುಕು|"
    r"തുറക്ക|അടയ്ക്ക|ബ്രൗസർ|കുറിപ്പ്|തിരയു|"
    r"\bbrowser\b|\bnotes?\b|\btab\b|\bsearch\b|\bopen\b|\bclose\b|"
    r"\bclear\b|\bboard\b|\bwhiteboard\b|"
    r"\bcourse\b|\blesson\b|\btutor\b|\bteach\b|\bstart\s*(course|lesson)\b|"
    r"\babrir\b|\bnavegador\b|\bpestaña\b|\bbuscar\b|\bnota\b|\baba\b|\bpesquisar\b|"
    r"\bouvrir\b|\bouvre\b|\bfermer\b|\bferme\b|\bonglet\b|\brechercher\b|"
    r"\böffnen\b|\böffne\b|\bschließen\b|\bnotiz\b|\bsuchen\b|"
    r"\bfechar\b|\bfeche\b|"
    r"\bhelp\s*cent(re|er)\b|\bopen\s*help\b|"
    r"\breload\b|\brefresh\b|"
    r"side\s*by\s*side|\btile\b|\bgoogle\b|\byoutube\b|\bwebsite\b|\bdocs?\b|\bvideo\b|"
    r"\bcounter\b|\btodo(\s*app|\s*list)?\b|\blanding(\s*page)?\b|\bportfolio\b|"
    r"\bcalculator\b|\bquiz(\s*app)?\b|\bclone\b|"
    r"\b(create|make|build|bana)\b.{0,30}\b(counter|todo|app|page|site|website|game|ui|project)\b|"
    # Explicit code-write imperatives (verb + code/file noun, either order).
    # Bare "code" is deliberately NOT here: "explain this code / ye code kya
    # karta hai" are teaching/screen questions, not desktop moves.
    r"कोड.{0,20}(लिख|बना|एडिट|ठीक)|फाइल.{0,20}(बना|लिख|खोल)|"
    r"\bcode\b.{0,20}\b(write|create|edit|fix|bana|likh|khol|dikha)\b|"
    r"\b(bana|likh)\b.{0,20}\b(code|files?)\b|"
    r"\bwrite\b.{0,30}\bcode\b|"
    r"\bedit\b.{0,30}\b(code|files?)\b|"
    r"\bcreate\b.{0,30}\b(files?|code)\b|\b(files?|code)\b.{0,30}\b(create|edit)\b|"
    r"\bfix\b.{0,30}\bcode\b)",
    re.IGNORECASE,
)
_DEFINITION_RE = re.compile(
    r"(क्या\s*है|कया\s*है|kya\s*hai|मतलब|matlab)\s*[?।.]?\s*$",
    re.IGNORECASE,
)


def wants_os_action(text: str) -> bool:
    """True when the turn likely wants a desktop move NOW (blocking director
    + voice ack), as opposed to the zero-latency background sidecar."""
    clean = (text or "").strip()
    if len(clean) < 8:
        return False
    if _DEFINITION_RE.search(clean):
        return False
    return bool(_OS_REQUEST_RE.search(clean))


# Teaching words also live in _OS_REQUEST_RE (a lesson may still want the
# code editor / browser opened, so the blocking fast-path keeps them), but
# they must NOT suppress the board: "HTML सिखाओ" IS the lesson the Green
# Board is for. Only pure desktop moves ("notes kholo", "browser kholo")
# suppress diagram generation (the ack reply teaches nothing).
_TEACHING_RE = re.compile(
    r"(कोर्स|लेसन|पाठ्यक्रम|पढ़ा|सिखा|ट्यूटर|"
    r"\bcourse\b|\blesson\b|\btutor\b|\bteach\b|\bstart\s*(course|lesson)\b)",
    re.IGNORECASE,
)


def wants_desktop_move(text: str) -> bool:
    """Narrow gate for diagram suppression: True only when the turn asks for
    a desktop/window move with no teaching request attached.

    Teaching words are stripped before matching, so "React lesson shuru karo"
    (lesson request -> needs the board) returns False while "notes kholo"
    (window move -> ack reply needs no board) returns True. Compound turns
    ("browser kholo aur HTML sikhao") still match via the remaining
    desktop words and stay suppressed — the opened app owns the screen.
    """
    clean = (text or "").strip()
    if len(clean) < 8:
        return False
    if _DEFINITION_RE.search(clean):
        return False
    stripped = _TEACHING_RE.sub(" ", clean)
    return bool(_OS_REQUEST_RE.search(stripped))


# Subset gate: the turn wants the agent to WRITE code (bigger director token
# budget + same blocking narration as other desktop moves).
_CODE_WRITE_RE = re.compile(
    r"(कोड.{0,20}(लिख|बना|एडिट|ठीक)|फाइल.{0,20}(बना|लिख)|"
    r"\bcode\b.{0,20}\b(write|create|edit|fix|bana|likh|khol|dikha)\b|"
    r"\b(bana|likh)\b.{0,20}\b(code|files?)\b|"
    r"\bwrite\b.{0,30}\bcode\b|"
    r"\bedit\b.{0,30}\b(code|files?)\b|"
    r"\bcreate\b.{0,30}\b(files?|code)\b|\b(files?|code)\b.{0,30}\b(create|edit)\b|"
    r"\bfix\b.{0,30}\bcode\b|"
    r"\bcounter\b|\btodo(\s*app|\s*list)?\b|\blanding(\s*page)?\b|\bportfolio\b|"
    r"\b(create|make|build|bana)\b.{0,30}\b(counter|todo|app|page|site|website|game|ui|project)\b)",
    re.IGNORECASE,
)


def wants_code_action(text: str) -> bool:
    """True when the turn explicitly asks the tutor to write/create/edit code."""
    clean = (text or "").strip()
    if len(clean) < 8:
        return False
    return bool(_CODE_WRITE_RE.search(clean))


_CODING_TOPIC_RE = re.compile(
    r"(html|css|javascript|java\s*script|typescript|react|node(?:\.js)?|express|mongo(?:db)?|mern|"
    r"frontend|front\s*end|backend|back\s*end|full\s*stack|api|dom|कोड|एचटीएमएल|सीएसएस|"
    r"जावास्क्रिप्ट|रिएक्ट|नोड|एक्सप्रेस|मोंगो|फ्रंट.?एंड|बैक.?एंड|फुल.?स्टैक)", re.IGNORECASE
)
_MERN_MODULE_RE = re.compile(
    r"(mern|react|node(?:\.js)?|express|mongo(?:db)?|backend|back\s*end|full\s*stack|api|database|auth|"
    r"रिएक्ट|नोड|एक्सप्रेस|मोंगो|बैक.?एंड|फुल.?स्टैक|एपीआई|डेटाबेस|ऑथ)", re.IGNORECASE
)


def is_coding_topic(text: str) -> bool:
    """True for coding questions, including explanation-only turns."""
    return bool(_CODING_TOPIC_RE.search((text or "").strip()))


def select_code_module(text: str) -> str:
    """Pick the smallest practical environment for the requested example."""
    return "mernstack" if _MERN_MODULE_RE.search((text or "").strip()) else "html_css_js"


_APP_NAMES = {
    "tutor": "the Tutor courses",
    "whiteboard": "the Green Board",
    "browser": "the Browser",
    "notes": "Notes",
    "code": "the Code editor",
    "help": "the Help Center",
}
_ZONE_NAMES = {
    "left": "the left half", "right": "the right half",
    "tl": "the top-left quarter", "tr": "the top-right quarter",
    "bl": "the bottom-left quarter", "br": "the bottom-right quarter",
}


def describe_action(action: dict) -> str:
    """Human one-liner for an executed action (feeds the voice ack)."""
    if not isinstance(action, dict):
        return "did something on the desktop"
    op = action.get("op", "?")
    app = _APP_NAMES.get(action.get("app", ""), "")
    if op == "open_app":
        return f"opened {app}"
    if op == "focus_app":
        return f"focused {app}"
    if op == "close_app":
        return f"closed {app}"
    if op == "minimize_app":
        return f"minimized {app}"
    if op == "maximize_app":
        return f"maximized {app}"
    if op == "restore_app":
        return f"restored {app}"
    if op == "tile_app":
        return f"tiled {app} to {_ZONE_NAMES.get(action.get('zone', ''), 'a tile')}"
    if op == "tile_grid":
        return "tiled a 2x2 grid"
    if op == "float_app":
        return f"floated {app}"
    if op == "browser_navigate":
        return f"navigated the Browser to '{str(action.get('target', ''))[:80]}'"
    if op == "browser_back":
        return "went back in the Browser"
    if op == "browser_forward":
        return "went forward in the Browser"
    if op == "browser_new_tab":
        return "opened a new browser tab"
    if op == "browser_reload":
        return "reloaded the browser page"
    if op == "browser_close_tab":
        return "closed the browser tab"
    if op == "note_add":
        title = str(action.get("title", "")).strip()[:60]
        return f"added a note{f' {title!r}' if title else ''}"
    if op == "code_create":
        return f"created file '{action.get('path', '')}'"
    if op == "code_write":
        how = "appended code to" if action.get("mode") == "append" else "wrote code into"
        return f"{how} '{action.get('path', '')}'"
    if op == "code_edit":
        return f"edited '{action.get('path', '')}'"
    if op == "code_open":
        return f"opened '{action.get('path', '')}' in the editor"
    if op == "code_delete":
        return f"deleted file '{action.get('path', '')}'"
    if op == "code_mkdir":
        return f"created folder '{action.get('path', '')}'"
    if op == "code_rmdir":
        return f"removed folder '{action.get('path', '')}'"
    if op == "code_search":
        return f"searched the project for '{action.get('query', '')}'"
    if op == "code_set_module":
        return f"selected the {action.get('module', 'coding')} environment"
    if op == "code_run":
        return "ran the live preview"
    if op == "clear_board":
        return "cleared the board"
    return f"ran {op}"


def ack_block(actions) -> str:
    """System-prompt addendum so the tutor talks about its moves in the SAME
    reply — naming exactly what happened — or stays honest when nothing
    happened (never claim phantom window moves).

    No verbatim examples: the tutor used to parrot 'batao isme kya search
    karna hai?' even when the search had already run. The follow-up is now
    conditional on what actually executed.
    """
    acts = [a for a in (actions or []) if isinstance(a, dict)]
    if not acts:
        return (
            "OS_ACTIONS_DONE: none — no window moved this turn. "
            "Do NOT claim you opened, closed, searched, wrote or rearranged "
            "anything. If the learner asked for a window move and none happened, "
            "say in one short line that the screen could not be rearranged this "
            "time and answer normally. NEVER tell the learner to open, close or "
            "move a window themselves — they have no controls for that."
        )
    lines = "\n".join(f"- {describe_action(a)}" for a in acts)
    targets = [
        str(a.get("target", "")).strip()[:80]
        for a in acts
        if a.get("op") == "browser_navigate" and str(a.get("target", "")).strip()
    ]
    if targets:
        follow = (
            f"The Browser ALREADY shows '{targets[0]}' — name it in the ack "
            "(e.g. say youtube is open) and NEVER ask what to search or open. "
            "Then continue the answer."
        )
    else:
        follow = (
            "If the user named a site/search and it is NOT listed above, it did "
            "NOT happen — never claim it opened. Ask ONE short follow-up only "
            "when the user gave no target at all (bare 'open browser'). "
            "Then continue the answer."
        )
    return (
        "OS_ACTIONS_DONE (already executed on the user's screen — the user SEES "
        f"them):\n{lines}\nAcknowledge ONLY the listed moves by name, in 1-2 "
        f"short Hinglish lines in Devanagari script only. {follow} "
        "Never claim actions not listed here."
    )


def sanitize_os_snapshot(raw) -> dict:
    """Bound the client OS snapshot (never trust sizes)."""
    if not isinstance(raw, dict):
        return {}
    snap = {}
    app = str(raw.get("app") or "")[:24]
    if app in APPS:
        snap["app"] = app
    opened = [str(a) for a in (raw.get("open") or []) if str(a) in APPS][:8]
    if opened:
        snap["open"] = opened
    minimized = [str(a) for a in (raw.get("minimized") or []) if str(a) in APPS][:8]
    if minimized:
        snap["minimized"] = minimized
    url = str(raw.get("browserUrl") or "")[:500]
    if url:
        snap["browserUrl"] = url
    try:
        tabs = int(raw.get("browserTabs") if raw.get("browserTabs") is not None else raw.get("tabs") or 0)
    except (TypeError, ValueError):
        tabs = 0
    if tabs > 0:
        snap["browserTabs"] = min(tabs, 32)
    try:
        steps = int(raw.get("whiteboardSteps") or 0)
    except (TypeError, ValueError):
        steps = 0
    if steps > 0:
        snap["whiteboardSteps"] = min(steps, 999)
    # Open code file (what the learner looks at) + full project listing.
    # The director uses code.file to resolve "this code / this file / it"
    # without demanding a path, and code.files to avoid recreating files
    # that exist; lesson is context only, never an action.
    code = raw.get("code")
    if isinstance(code, dict):
        path = _clean_code_path(code.get("file"))
        lang = re.sub(r"[^A-Za-z#+_-]", "", str(code.get("lang") or ""))[:24]
        entry = {}
        if path:
            entry["file"] = path
            if lang:
                entry["lang"] = lang
        files = code.get("files")
        if isinstance(files, list):
            listed = []
            for f in files[:40]:
                cp = _clean_code_path(f)
                if cp and cp not in listed:
                    listed.append(cp)
            if listed:
                entry["files"] = listed
        module = str(code.get("module") or "").strip().lower()
        if module in {"html_css_js", "mernstack"}:
            entry["module"] = module
        entry["practice_allowed"] = bool(code.get("practice_allowed"))
        entry["practice_pending"] = bool(code.get("practice_pending"))
        if entry:
            snap["code"] = entry
    lesson = raw.get("lesson")
    if isinstance(lesson, dict):
        lid = str(lesson.get("id") or "").strip()[:80]
        if lid:
            snap["lesson"] = {"id": lid}
    return snap


def sanitize_action(raw) -> dict | None:
    """Validate one director action; None = drop it."""
    if not isinstance(raw, dict):
        return None
    op = str(raw.get("op") or "").strip()
    if op not in OPS:
        return None
    if op in _NOARG_OPS or op in _BROWSER_OPS or op == "clear_board":
        return {"op": op}
    if op in _APP_OPS:
        app = str(raw.get("app") or "").strip()
        if app not in APPS:
            return None
        action = {"op": op, "app": app}
        if op == "tile_app":
            zone = str(raw.get("zone") or "").strip()
            if zone not in ZONES:
                return None
            action["zone"] = zone
        return action
    if op == "browser_navigate":
        target = str(raw.get("target") or "").strip()[:500]
        if not target or _DANGEROUS_SCHEME_RE.match(target):
            return None
        return {"op": op, "target": target}
    if op == "note_add":
        title = str(raw.get("title") or "").strip()[:80]
        body = str(raw.get("body") or "").strip()[:2000]
        if not title and not body:
            return None
        action = {"op": op}
        if title:
            action["title"] = title
        if body:
            action["body"] = body
        return action
    if op in _CODE_OPS:
        if op == "code_search":
            query = str(raw.get("query") or raw.get("target") or "").strip()[:120]
            if not query:
                return None
            return {"op": op, "query": query}
        if op == "code_set_module":
            module = str(raw.get("module") or "").strip().lower()
            return {"op": op, "module": module} if module in {"html_css_js", "mernstack"} else None
        path = _clean_code_path(raw.get("path"))
        if not path:
            return None
        if op == "code_create":
            content = str(raw.get("content") or "")[:6000]
            action = {"op": op, "path": path}
            if content.strip():
                action["content"] = content
            return action
        if op == "code_write":
            content = str(raw.get("content") or "")[:6000]
            if not content.strip():
                return None
            mode = str(raw.get("mode") or "overwrite").strip().lower()
            return {"op": op, "path": path, "content": content,
                    "mode": "append" if mode == "append" else "overwrite"}
        if op == "code_edit":
            find = str(raw.get("find") or "")[:2000]
            replace = str(raw.get("replace") or "")[:6000]
            if not find.strip():
                return None
            return {"op": op, "path": path, "find": find, "replace": replace}
        if op in ("code_open", "code_delete"):
            return {"op": op, "path": path}
        if op in ("code_mkdir", "code_rmdir"):
            return {"op": op, "path": path.rstrip("/")}
    return None


_VALID_CODE_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/]{0,119}$")


def _clean_code_path(raw) -> str | None:
    """Relative in-project paths only (index.html, js/app.js). Rejects
    absolute paths, parent escapes, and overlong names."""
    p = str(raw or "").replace("\\", "/").strip().strip("/")[:120]
    if not p or p.endswith("/") or ".." in p.split("/"):
        return None
    if not _VALID_CODE_PATH_RE.match(p):
        return None
    return p


def plan_os_actions(
    key: str,
    user_text: str,
    snapshot: dict | None,
    *,
    client,
    url: str,
    model: str,
    thinking: dict | None = None,
    stop_evt=None,
    max_tokens: int = 400,
) -> list[dict]:
    """One fast tool-call: user text + OS snapshot -> validated actions.

    Best-effort: [] means 'no action', never an error. Single attempt, no
    retry — a dropped director call only skips window moves, never voice.
    """
    code_snapshot = snapshot.get("code") if isinstance(snapshot, dict) else {}
    practical_allowed = bool(code_snapshot.get("practice_allowed")) if isinstance(code_snapshot, dict) else False
    if not key or (not should_direct(user_text) and not practical_allowed):
        return []
    if stop_evt is not None and stop_evt.is_set():
        return []
    if not _OS_SEMAPHORE.acquire(blocking=False):
        return []
    try:
        import logging as _logging
        _log = _logging.getLogger("voice_api")
        snap_json = json.dumps(snapshot or {}, ensure_ascii=False)[:800]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _DIRECTOR_SYSTEM},
                {"role": "user", "content": f"USER: {(user_text or '')[:300]}\nOS: {snap_json}"},
            ],
            "tools": [OS_CONTROL_TOOL],
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if thinking is not None:
            payload["thinking"] = thinking  # DeepSeek V4: disabled = fast tool call
        try:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        except Exception as e:  # noqa: BLE001 — director must never break voice
            _log.info("OS director skipped (%s)", e)
            return []
        choice = (response.json().get("choices") or [{}])[0]
        message = choice.get("message") or {}
        arguments = None
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if function.get("name") == "control_os":
                arguments = function.get("arguments")
                break
        if not arguments:
            return []  # director decided: no action this turn
        try:
            parsed = json.loads(arguments)
        except (TypeError, ValueError):
            return []
        raw_actions = parsed.get("actions") if isinstance(parsed, dict) else None
        if not isinstance(raw_actions, list):
            return []
        out = []
        for raw in raw_actions[:MAX_ACTIONS]:
            # Same trailing-space key quirk as diagram tool calls — strip.
            if isinstance(raw, dict):
                raw = {str(k).strip(): v for k, v in raw.items()}
            action = sanitize_action(raw)
            if action:
                out.append(action)
        code_actions = [a for a in out if a.get("op") in _CODE_OPS]
        code = snapshot.get("code") if isinstance(snapshot, dict) else {}
        practice_allowed = bool(code.get("practice_allowed")) if isinstance(code, dict) else False
        code_window_actions = [a for a in out if a.get("app") == "code" and a.get("op") in _APP_OPS]
        if not practice_allowed and (code_actions or code_window_actions):
            # The tutor must ask before opening the editor. This second gate
            # keeps an over-eager director from mutating the learner's screen.
            return [
                a for a in out
                if a.get("op") not in _CODE_OPS
                and not (a.get("app") == "code" and a.get("op") in _APP_OPS)
            ]
        if code_actions and not any(a.get("op") == "code_set_module" for a in code_actions):
            out = [{"op": "code_set_module", "module": select_code_module(user_text)}, *out]
        elif code_actions:
            selected = select_code_module(user_text)
            module_action = {"op": "code_set_module", "module": selected}
            out = [module_action, *[a for a in out if a.get("op") != "code_set_module"]]
        return out
    finally:
        _OS_SEMAPHORE.release()
