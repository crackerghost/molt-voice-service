"""Intent-based diagram generation for the visual tutor surface."""

import json
import re
import threading

DIAGRAM_MAX_ELEMENTS = 40
DIAGRAM_MAX_TEXT = 180
# Overload guard for default-allow gating: at most this many concurrent
# planner calls per process. Long turns spawn one thread per audio window;
# beyond this the step is skipped (best-effort — voice is unaffected).
_MAX_PARALLEL_PLANNERS = 6
_PLANNER_SEMAPHORE = threading.Semaphore(_MAX_PARALLEL_PLANNERS)
# Board text is English-only. Devanagari is voice-only.
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]+")
DIAGRAM_INTENT_RE = re.compile(
    r"(?:draw|diagram|flowchart|visuali[sz]e|mind\s*map|architecture|timeline|process|relationship|"
    r"चित्र|डायग्राम|फ्लोचार्ट|दिखाओ|समझाने के लिए|तुलना|टाइमलाइन|प्रोसेस)",
    re.IGNORECASE,
)

DIAGRAM_TOOL = {
    "type": "function",
    "function": {
        "name": "draw_flowchart_or_diagram",
        "description": "Render concise concept nodes, comparison tables, quiz checks, notes, code snippets, and connecting arrows on the whiteboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "maxItems": DIAGRAM_MAX_ELEMENTS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "type": {"type": "string", "enum": ["rectangle", "ellipse", "diamond", "text", "arrow", "code", "note", "table", "quiz", "html"]},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                            "text": {"type": "string"},
                            "code": {"type": "string", "description": "Short exact code snippet (max ~10 lines) for type=code."},
                            "language": {"type": "string", "description": "Code label, e.g. HTML, JS, python."},
                            "side": {"type": "string", "enum": ["left", "right"], "description": "Compare steps only (X vs Y): which column this node belongs to."},
                            "tone": {"type": "string", "enum": ["core", "example", "warn"], "description": "Semantic color: core concept, example, warning/mistake."},
                            "backgroundColor": {"type": "string"},
                            "startNodeId": {"type": "string"},
                            "endNodeId": {"type": "string"},
                            "arrowLabel": {"type": "string"},
                            "trigger": {
                                "type": "string",
                                "description": "1-3 exact English words from the STEP that name this element (e.g. 'computer', 'query selector'). The board draws it the moment the tutor speaks them.",
                            },
                            "headers": {"type": "array", "items": {"type": "string"}, "description": "Table only: 2-4 short column headers."},
                            "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "Table only: up to 6 rows matching the headers, cells 1-4 words."},
                            "options": {"type": "array", "items": {"type": "string"}, "description": "Quiz only: 2-4 short answer options."},
                            "html": {"type": "string", "description": "Rich-visual only: self-contained HTML + inline <style> (max ~40 lines, light card). No scripts, no external files."},
                            "height": {"type": "integer", "description": "Rich-visual only: iframe height in px (120-420, default 220)."},
                            "answer": {"type": "integer", "description": "Quiz only: 0-based index of the correct option. Omit for a reflection question (no scoring)."},
                            "explanation": {"type": "string", "description": "Quiz only: one-line why, shown after the learner answers."},
                        },
                        # x/y required only for SHAPES. Arrows are defined by
                        # startNodeId/endNodeId (server computes their geometry),
                        # and Groq 400-rejects the whole call when the LLM omits
                        # arrow coordinates — the top planner failure in prod logs.
                        # code/note need no coordinates (rendered as blocks below).
                        "required": ["id", "type"],
                    },
                },
            },
            "required": ["elements"],
        },
    },
}


_GREETING_ONLY_RE = re.compile(
    r"^(नमस्ते|हेलो|हाय|हैलो|नमस्कार|कैसे\s+हो|क्या\s+हाल|hello|hi|hey|"
    r"good\s+(morning|afternoon|evening|night)|how\s+are\s+you|"
    r"हाँ|हां|अच्छा|ओके|ok|okay|thanks|thank\s+you(\s+(so|very)\s+much)?|thanks\s+a\s+lot|थैंक्स?|शुक्रिया|धन्यवाद|"
    r"समझ\s*गया|samajh\s*gaya|got\s*it|welcome|वेलकम|sorry|सॉरी|"
    r"bye|बाय|अलविदा|good\s*bye|good\s*night|shubh\s*(ratri|prabhat)|शुभ\s*रात्रि|फिर\s*मिलेंगे)\W*$",
    re.IGNORECASE,
)


def _board_text(value: object) -> str:
    """Strip Devanagari and collapse whitespace so the canvas stays English."""
    return DEVANAGARI_RE.sub(" ", str(value or "")).strip()


def should_generate(text: str, history: list[dict] | None, enabled: bool) -> bool:
    """Auto-decide: every teaching turn gets an LLM judge call.

    DIAGRAM_GATE=auto (default, paid tier): default-allow, judge decides.
    DIAGRAM_GATE=explicit (dev tier, 8k TPM): only explicit draw-intent
    ("draw/diagram/दिखाओ...") triggers the planner, saving ~10 Groq calls/turn.
    Voice never waits: the judge runs parallel to TTS, diagram pops when ready.
    Only pure greetings / tiny acks are skipped to save the extra LLM call.
    """
    if not enabled:
        return False
    clean_text = (text or "").strip()
    if not clean_text or len(clean_text) < 8:
        return False
    if _GREETING_ONLY_RE.search(clean_text):
        return False
    # OS-control turns ("open notes", "browser kholo") must never draw:
    # the ack reply ("notes open kar diya...") is not a lesson, and any
    # board delta would yank the green board over the app the user asked
    # for. Lazy import: os_control imports this module's greeting regex.
    try:
        from server.llm.os_control import wants_os_action as _wants_os
        if _wants_os(clean_text):
            return False
    except Exception:  # noqa: BLE001 — gate must never break
        pass
    # Explicit ask always wins (no LLM judgement needed to trigger).
    if DIAGRAM_INTENT_RE.search(clean_text):
        return True
    import os as _os
    if _os.environ.get("DIAGRAM_GATE", "auto").strip().lower() == "explicit":
        return False
    # Everything else: let the judge decide (explain html, क्या है, कैसे...).
    return True


def _step_prompt(step_text: str, topic: str, tag: str = "w") -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a visual teaching assistant drawing ONE step of an explanation "
                "on a shared whiteboard. DEFAULT TO DRAWING: any explanation with "
                "parts, steps, sequence, cause-effect, comparison, timeline, "
                "hierarchy, a system, a definition with 2+ components, or how "
                "something works deserves a board — processes, frontend/backend/"
                "data flow, architectures included. When in doubt, DRAW; a visual "
                "almost always helps grounding. Return no tool call for pure "
                "greetings, thanks, acks, confirmations, goodbyes, small talk, "
                "bare yes/no answers with no explanation, unstructured "
                "opinions, jokes, meta talk, or narration of a window/app move "
                "('open kar diya', 'note add ho gaya') with no new concept — "
                "none of these need a visual. When drawing, return a draw_flowchart_or_diagram "
                "tool call for THIS step only, mixing whatever explains best: "
                "3-6 compact nodes with arrows, PLUS at most ONE short code "
                "snippet (type=code, exact code/tags as-is, max ~10 lines, with "
                "a language label) when the step shows code, and at most ONE "
                "takeaway note (type=note): one line for the key insight — or, "
                "when the step WRAPS UP or summarizes, 'Takeaways: • a • b • c' "
                "(max 3 short bullets) with a trigger from the spoken summary "
                "words. CONTINUITY: this is ONE step of a longer explanation — "
                "draw ONLY this step's new idea (1-3 nodes). NEVER redraw "
                "parent or overview nodes from earlier steps; repeats are "
                "dropped and leave the board emptier. ORDER elements in the "
                "exact order the step speaks them, so each shape appears the "
                "moment its words are spoken. SHAPE VARIETY — an all-rectangle "
                "board is banned: mix shapes by MEANING in every step. Ellipse "
                "for start points, key entities, and end outcomes. Diamond for "
                "EVERY decision, branch, or either/or comparison "
                "(visible-vs-hidden like head-vs-body IS a diamond). Rectangle "
                "for parts and steps. DRAW THE THING, not just a chain: when "
                "the topic is a concrete object (a page, browser, phone, map, "
                "house), compose the object itself from labeled parts arranged "
                "as the object looks (a browser = url-bar box above a viewport "
                "box; a page = head box above body sections) instead of an "
                "abstract chain. Abstract chains are the LAST resort, only for "
                "pure sequences with nothing concrete to show. Use type=text "
                "for free-floating annotations (no box). Labels are SHORT — max "
                "5-6 words per node (e.g. 'h1-h6: headings, h1 biggest'). "
                "COMPARISONS (X vs Y, differences, before/after, right/wrong): "
                "set side=left on every X node and side=right on every Y node, "
                "with NO arrows crossing sides — the board renders two columns "
                "with a VS divider. TABLES: a comparison with 2+ rows of "
                "parallel facts goes in ONE type=table (headers 2-4 cols, rows "
                "up to 6, cells 1-4 words, text=short table title) INSTEAD of "
                "side-by-side nodes. QUIZ: if the STEP asks the learner a "
                "question, attach ONE type=quiz (text=the question, options=2-4 "
                "short options, answer=0-based correct index, explanation=one "
                "line why, trigger=the spoken question words). Max one quiz "
                "per step. TONE every node: core = the key concept, "
                "example = an illustration, warn = a common mistake — the board "
                "colors them coral / teal / amber so importance reads instantly."
                "RICH VISUALS (type=html): when the step uses a real-life "
                "analogy or numbers worth charting, draw it as ONE "
                "self-contained HTML snippet with inline <style> (max ~40 "
                "lines): a browser or phone mockup, a div-based bar chart, an "
                "analogy scene (house, shop, map). Light card only — white "
                "background, dark text, rounded corners — so it reads on the "
                "dark board. NO <script>, NO external files, fonts, images, or "
                "links, NO event handlers — pure HTML + inline CSS; anything "
                "executable is stripped and the visual is dropped if empty. "
                "Max ONE html per step. "
                "Every rectangle/ellipse/diamond MUST carry non-empty "
                "text naming the concrete thing from the STEP (tag names, file names, "
                "exact terms — never blank labels). Language rule: the BOARD is "
                "always ENGLISH — short English labels, code/tag/ "
                "attribute/file names exactly as-is (HTML, h1, href, index.html). "
                "Never Devanagari on the board; Hindi is voice-only. "
                "Node ids: ASCII ONLY (a-z, 0-9, hyphen), prefixed with the given "
                "TAG (e.g. TAG-n1, TAG-n2). Never Devanagari or invented words in "
                "ids. Every element ALSO gets a trigger: the 1-3 exact English "
                "words from the STEP that name it (label 'Computer' -> trigger "
                "'computer'; 'query selector' -> 'query selector'). The board "
                "draws each element the instant the tutor speaks its trigger, "
                "so triggers must be words the STEP actually says. Shapes give x/y/width/height; ARROWS give ONLY id, type, "
                "startNodeId, endNodeId — never x/y on arrows; code/note/table/quiz/html give "
                "ONLY id, type, content fields — never x/y. Shapes: "
                "rectangle = component/step/part, ellipse = start/end/entity/outcome, "
                "diamond = decision/branch/comparison, text = free annotation, arrow = flow."
            ),
        },
        {"role": "user", "content": f"TAG: {tag}\nTOPIC: {topic[:200]}\nSTEP: {step_text[:600]}"},
    ]


# Production policy: DEFAULT-ALLOW. Any explaining counts as drawable until
# proven otherwise — the LLM judge is far better at "does this need a
# visual?" than any keyword list. This regex blocks ONLY windows that are
# certainly not explanations (greetings, thanks, acks, confirmations,
# goodbyes, praise). Anchored full-string: any trailing teaching content
# ("samajh gaya, lekin ek doubt hai") still draws normally.
_NONVISUAL_RE = re.compile(
    r"^(नमस्ते|नमस्कार|हेलो|हाय|हैलो|hello|hi|hey|thanks|thank\s+you(\s+(so|very)\s+much)?|thanks\s+a\s+lot|थैंक्स?|शुक्रिया|"
    r"धन्यवाद|ओके|ok(ay)?|अच्छा|हाँ|हां|yes|no|नहीं|bye|बाय|अलविदा|good\s*bye|"
    r"good\s+(morning|afternoon|evening|night)|shubh\s*(ratri|prabhat)|शुभ\s+(प्रभात|रात्रि)|"
    r"समझ\s*गया|samajh\s*gaya|got\s*it|sorry|सॉरी|कोई\s*बात\s*नहीं|no\s*problem|"
    r"बिल्कुल सही|बहुत बढ़िया|शाबाश|congrats|welcome|वेलकम)"
    r"[!।.\s?]*$",
    re.IGNORECASE,
)


# Dynamic course layer: the course compiler fills these per course/module.
# The static gate above stays fully generic. Keywords are indexed in BOTH
# scripts because the gate reads raw LLM text (Devanagari) while authors
# write Latin: each Latin keyword also indexes its phonetic rendering, and
# every glossary key AND value is indexed (values are the exact Devanagari
# the tutor actually speaks, e.g. फोटोसिन्थेसिस).
_COURSE_KEYWORDS: frozenset = frozenset()


def set_course_keywords(words) -> None:
    """Install this course's domain keywords (feeds the visual gate)."""
    from server.speech.normalization import _phonetic
    forms: set[str] = set()
    for w in (words or []):
        w = str(w).strip()
        if not w:
            continue
        forms.add(w.lower())
        if re.search(r"[A-Za-z]", w):
            try:
                forms.add(_phonetic(w))
            except Exception:  # noqa: BLE001 — gate must never break
                pass
    global _COURSE_KEYWORDS
    _COURSE_KEYWORDS = frozenset(f for f in forms if len(f) > 2)


def set_course_context(glossary: dict | None = None, keywords=None) -> None:
    """One call the roadmap integration makes per module/topic.

    Glossary values (exact Devanagari terms) join the keyword index, so a
    window saying फोटोसिन्थेसिस matches even though the author wrote
    'photosynthesis'. Also installs the TTS glossary overlay.
    """
    from server.speech import normalization as _norm
    _norm.set_course_glossary(glossary)
    forms: set[str] = set()
    for w in (keywords or []):
        w = str(w).strip()
        if w:
            forms.add(w.lower())
    for k, v in (glossary or {}).items():
        if str(k).strip():
            forms.add(str(k).lower())
        if str(v).strip():
            forms.add(str(v))
    set_course_keywords(forms)


def is_visual_step(step_text: str) -> bool:
    """Default-allow: every substantive window earns a planner call.

    Only obvious non-explanations are filtered; the LLM judge makes the
    final draw/no-draw call per step. Course keywords now act as a recall
    BOOST (log boost below) rather than a requirement.
    """
    text = (step_text or "").strip()
    if len(text) < 24:
        return False
    if _NONVISUAL_RE.search(text):
        return False
    return True


def generate_for_step(
    key: str,
    step_text: str,
    topic: str,
    stop_evt: threading.Event,
    *,
    client,
    url: str,
    model: str,
    reasoning_effort: str = "",
    max_tokens: int = 700,
    id_prefix: str = "w",
    thinking: dict | None = None,
    turn_id: str = "",
) -> dict | None:
    """Watcher planner: one small board delta for ONE spoken window.

    Best-effort by design — None means 'nothing drawable this step', never an
    error. Voice never waits for this; the caller tags the result with window_n
    and the client merges it on arrival.

    Latency design: NO reasoning param is ever sent here (a 3-6 node board
    needs zero thinking; gpt-oss thinking is the biggest chunk of the old
    2-5 s per-window cost). reasoning_effort is accepted for backward
    compat but ignored. max_tokens is env-tunable (DIAGRAM_MAX_TOKENS).

    Overload guard: at most _MAX_PARALLEL_PLANNERS concurrent Groq calls;
    beyond that the step is skipped (best-effort — voice is unaffected).
    With default-allow gating every window calls the planner, so one long
    turn must not open unbounded parallel requests.
    """
    if stop_evt.is_set() or not (step_text or "").strip():
        return None
    if not is_visual_step(step_text):
        return None
    if not _PLANNER_SEMAPHORE.acquire(blocking=False):
        return None
    try:
        import logging as _logging
        _log = _logging.getLogger("voice_api")
        # Two budgets: the configured one, then +50% once. Truncated tool
        # JSON (Groq 400 tool_use_failed / finish_reason "length") is the
        # top planner failure in prod — a bigger second attempt usually
        # completes the same board instead of dropping the whole step.
        budgets = [max_tokens, int(max_tokens * 1.5)]
        arguments = None
        for attempt, budget in enumerate(budgets):
            payload = {
                "model": model,
                "messages": _step_prompt(step_text, topic, id_prefix),
                "tools": [DIAGRAM_TOOL],
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": budget,
            }
            if thinking is not None:
                payload["thinking"] = thinking  # DeepSeek V4: disabled = fast tool call
            # Deliberately no reasoning_effort: see docstring.
            response = None
            try:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
            except Exception as e:
                try:
                    body = response.text[:300] if response is not None else ""
                except Exception:
                    body = ""
                # Truncation 400 -> retry once with the bigger budget.
                if attempt == 0 and ("tool_use_failed" in body or "Failed to parse tool call" in body):
                    _log.info("Diagram planner retrying window %s with %d tokens (truncated JSON)", id_prefix, budgets[1])
                    continue
                # Log the body once — Groq 400s carry the real reason (bad tool
                # payload, token budget, model capability). Voice is unaffected.
                _log.warning("Diagram planner skipped (%s) %s", e, body)
                return None
            choice = (response.json().get("choices") or [{}])[0]
            message = choice.get("message") or {}
            arguments = None
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                if function.get("name") == "draw_flowchart_or_diagram":
                    arguments = function.get("arguments")
                    break
            if not arguments:
                return None  # judge decided: nothing drawable this step
            try:
                json.loads(arguments)
                break  # valid JSON — stop retrying
            except (TypeError, ValueError):
                if attempt == 0:
                    _log.info("Diagram planner retrying window %s with %d tokens (bad JSON)", id_prefix, budgets[1])
                    arguments = None
                    continue
                return None
        if not arguments:
            return None
        try:
            diagram = normalize(json.loads(arguments))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not diagram or stop_evt.is_set():
            return None
        # Namespace ids per window so deltas merge without collisions.
        # The model is told to prefix with TAG already — don't double it.
        nodes = {}
        out = []
        for item in diagram["elements"]:
            old_id = item["id"]
            new_id = old_id if old_id.startswith(f"{id_prefix}-") else f"{id_prefix}-{old_id}"
            new_id = new_id[:80]
            nodes[old_id] = new_id
            item["id"] = new_id
            out.append(item)
        for item in out:
            if item["type"] == "arrow":
                if item.get("startNodeId") in nodes:
                    item["startNodeId"] = nodes[item["startNodeId"]]
                if item.get("endNodeId") in nodes:
                    item["endNodeId"] = nodes[item["endNodeId"]]
        # Same-turn repetition guard: each window draws only its NEW idea —
        # repeats of earlier windows' nodes are dropped here (dangling arrows
        # are cleaned by the keep-set filter below).
        out = _dedupe_turn(turn_id, out)
        # Blank-label nodes render as empty boxes — worse than no board. Drop
        # shapes with no text (code/note survive on snippet/takeaway), then
        # re-drop arrows left dangling by that.
        out = [it for it in out
               if it["type"] == "arrow"
               or str(it.get("text", "")).strip()
               or (it["type"] == "code" and str(it.get("code", "")).strip())]
        keep = {it["id"] for it in out if it["type"] in {"rectangle", "ellipse", "diamond", "text"}}
        out = [it for it in out
               if it["type"] != "arrow"
               or (it.get("startNodeId") in keep and it.get("endNodeId") in keep)]
        # Compare steps: no arrow may cross the VS divider — the model is
        # told this, but prod logs show it does it anyway. Enforce here.
        side_of = {it["id"]: it.get("side") for it in out if it["type"] != "arrow"}
        if any(s == "left" for s in side_of.values()) and any(s == "right" for s in side_of.values()):
            out = [it for it in out
                   if it["type"] != "arrow"
                   or side_of.get(it.get("startNodeId")) == side_of.get(it.get("endNodeId"))]
        if not any(it["type"] in {"rectangle", "ellipse", "diamond", "text", "code", "note", "table", "quiz", "html"} for it in out):
            return None
        # Deterministic binary-tree layout (model coordinates are NOT trusted —
        # prod boards showed boxes piled on top of each other, then one
        # cramped horizontal strip). See _layout_board.
        _layout_board(out)
        _turn_shift(turn_id, out)
        return {"elements": out}
    finally:
        _PLANNER_SEMAPHORE.release()



def _prompt(text: str, history: list[dict]) -> list[dict]:
    recent = "\n".join(
        f"{m.get('role', 'user')}: {str(m.get('content', ''))[:500]}"
        for m in history[-4:]
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a visual teaching assistant. Decide whether a diagram materially improves "
                "this explanation. If yes, call draw_flowchart_or_diagram. If no, return no tool call. "
                "Use 3-10 concise nodes, max 6 words per node, and connect related nodes with arrows. "
                "Use logical coordinates, top-to-bottom for sequences and side-by-side for comparisons. "
                "Board text is always English — short English labels, code/tag/file names exactly "
                "as-is. Never Devanagari on the board; Hindi is voice-only."
            ),
        },
        {"role": "user", "content": f"Recent context:\n{recent}\n\nCurrent question:\n{text}"},
    ]


def _arrow_geometry(item: dict, boxes: dict[str, tuple]) -> None:
    """Set an arrow's x/y/width/height/points from its endpoint boxes.

    Orthogonal elbow connectors (vertical bus + horizontal jog) instead of
    straight diagonals: the line leaves one box edge, travels through the
    empty row gap, and enters the opposite edge — so it can never slice
    through a third box's text (the old straight fallback drew diagonals
    straight across labels). Same-row links stay flat horizontals through
    the column gap; same-column links stay flat verticals. The client
    renders every point of the polyline. No-op when an endpoint is unknown.
    """
    s = boxes.get(item.get("startNodeId", ""))
    e = boxes.get(item.get("endNodeId", ""))
    if not s or not e:
        return
    sx, sy, sw, sh = s
    ex, ey, ew, eh = e
    scx, scy = sx + sw / 2, sy + sh / 2
    ecx, ecy = ex + ew / 2, ey + eh / 2
    s_bot, s_top, s_right, s_left = sy + sh, sy, sx + sw, sx
    e_bot, e_top, e_right, e_left = ey + eh, ey, ex + ew, ex
    pts = None
    if ey >= sy + sh - 10 and abs(ecx - scx) <= 4:
        pts = [(scx, s_bot), (ecx, e_top)]                      # straight down
    elif ey + eh <= sy + 10 and abs(ecx - scx) <= 4:
        pts = [(scx, s_top), (ecx, e_bot)]                      # straight up
    elif ey >= sy + sh - 10:
        bus = e_top - 10                                        # elbow down
        pts = [(scx, s_bot), (scx, bus), (ecx, bus), (ecx, e_top)]
    elif ey + eh <= sy + 10:
        bus = e_bot + 10                                        # elbow up
        pts = [(scx, s_top), (scx, bus), (ecx, bus), (ecx, e_bot)]
    elif ex >= sx + sw - 10 and abs(ecy - scy) <= sh:
        pts = [(s_right, scy), (e_left, ecy)]                   # straight right
    elif ex + ew <= sx + 10 and abs(ecy - scy) <= sh:
        pts = [(s_left, scy), (e_right, ecy)]                   # straight left
    elif abs(ecx - scx) > abs(ecy - scy):
        # Overlapping rows: connect along the dominant axis by centers.
        if ecx >= scx:
            pts = [(s_right, scy), (e_left, ecy)]
        else:
            pts = [(s_left, scy), (e_right, ecy)]
    elif ecy >= scy:
        pts = [(scx, s_bot), (ecx, e_top)]
    else:
        pts = [(scx, s_top), (ecx, e_bot)]
    x = min(p[0] for p in pts)
    y = min(p[1] for p in pts)
    item["x"], item["y"] = x, y
    item["width"] = max(1, max(p[0] for p in pts) - x)
    item["height"] = max(1, max(p[1] for p in pts) - y)
    item["points"] = [[p[0] - x, p[1] - y] for p in pts]


# ---------- Deterministic board layout (model coordinates are NOT trusted) ----------
# Each audio window is its own SVG section, so coordinates only arrange shapes
# WITHIN the step. Binary-tree flow: the first shape is the root, centered on
# the top row; the rest fill rows of two. Hierarchies read as trees, sequences
# read as top-to-bottom timelines, and wide boxes use the full canvas instead
# of one cramped horizontal strip. Compare steps (side=left/right) keep two
# columns with a VS divider; tiny steps (<=2 shapes) stay a compact row.
_TREE_X0, _TREE_W = 40.0, 1040.0
_TREE_GAP_X, _TREE_GAP_Y = 48.0, 76.0


def _node_size(item):
    label = str(item.get("text", ""))
    if item["type"] == "text":
        return max(200, min(560, 90 + 7.5 * len(label))), 32
    return max(220, min(460, 140 + 7 * len(label))), (72 if item["type"] == "diamond" else 64)


def _place(item, x, y):
    w, h = _node_size(item)
    item["width"], item["height"] = w, h
    item["x"] = max(-2000, min(2000, x))
    item["y"] = max(-2000, min(2000, y))
    return y + h


def _layout_board(out):
    """Position every shape + recompute every arrow. Mutates and returns out."""
    shapes = [it for it in out if it["type"] in {"rectangle", "ellipse", "diamond", "text"}]
    left = [s for s in shapes if s.get("side") == "left"]
    right = [s for s in shapes if s.get("side") == "right"]
    center = [s for s in shapes if not s.get("side")]
    if left and right:
        # Comparison columns, then unsided shapes full-width underneath.
        for col, cx in ((left, _TREE_X0), (right, _TREE_X0 + 560)):
            y = 40.0
            for item in col:
                y = _place(item, cx, y) + _TREE_GAP_Y
        if center:
            top = max(
                [it["y"] + it["height"] for it in left + right] or [40.0]
            )
            y = top + _TREE_GAP_Y
            for item in center:
                y = _place(item, _TREE_X0, y) + _TREE_GAP_Y
    elif len(shapes) <= 2:
        # Tiny step: compact left-to-right row.
        x, y, row_h = _TREE_X0, 40.0, 0.0
        for item in shapes:
            w, h = _node_size(item)
            item["width"], item["height"] = w, h
            item["x"], item["y"] = x, y
            x += w + _TREE_GAP_X
            row_h = max(row_h, float(h))
    else:
        # Binary tree: root centered on top, children in rows of two.
        root, rest = shapes[0], shapes[1:]
        rw, rh = _node_size(root)
        _place(root, _TREE_X0 + (_TREE_W - rw) / 2, 40.0)
        y = 40.0 + rh + _TREE_GAP_Y
        cell = (_TREE_W - _TREE_GAP_X) / 2
        for i in range(0, len(rest), 2):
            row = rest[i:i + 2]
            if len(row) == 2:
                _, h0 = _node_size(row[0])
                _, h1 = _node_size(row[1])
                row_h = max(h0, h1)
                for item, cx in zip(row, (_TREE_X0, _TREE_X0 + cell + _TREE_GAP_X)):
                    _, h = _node_size(item)
                    item["width"], item["height"] = cell, h
                    item["x"] = max(-2000, min(2000, cx))
                    item["y"] = max(-2000, min(2000, y + (row_h - h) / 2))
                y += row_h + _TREE_GAP_Y
            else:
                w, h = _node_size(row[0])
                _place(row[0], _TREE_X0 + (_TREE_W - w) / 2, y)
                y += h + _TREE_GAP_Y
    boxes = {it["id"]: (it["x"], it["y"], it["width"], it["height"]) for it in shapes}
    for item in out:
        if item["type"] == "arrow":
            _arrow_geometry(item, boxes)
    return out


# ---------- Cross-window repetition guard ----------
# Every audio window plans independently, so without memory each window redraws
# the same parent nodes (three "<head>" sections in one answer). Track emitted
# shape labels per turn and skip repeats — each window then draws only its NEW
# idea, and the board stops scrolling through duplicates.
_TURN_LABELS: dict[str, set[str]] = {}
_TURN_LOCK = threading.Lock()
_TURN_CACHE_MAX = 64


def _label_key(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())[:60]


def _dedupe_turn(turn_id: str, out: list[dict]) -> list[dict]:
    """Drop shapes whose label already appeared this turn. Extras
    (code/note/table/quiz) and arrows always survive — dangling arrows are
    cleaned by the caller's keep-set filter right after."""
    if not turn_id:
        return out
    with _TURN_LOCK:
        seen = _TURN_LABELS.get(turn_id)
        if seen is None:
            seen = set()
            _TURN_LABELS[turn_id] = seen
            while len(_TURN_LABELS) > _TURN_CACHE_MAX:
                _TURN_LABELS.pop(next(iter(_TURN_LABELS)))
        fresh = []
        for it in out:
            if it["type"] in {"rectangle", "ellipse", "diamond", "text"}:
                k = _label_key(it.get("text", ""))
                if k and k in seen:
                    continue
                if k:
                    seen.add(k)
            fresh.append(it)
        return fresh


def _sanitize_html(markup: object) -> str:
    """Strip everything executable from LLM-authored board markup.

    The client renders it in a scriptless sandboxed iframe (defense in
    depth), but we still remove scripts, frames, forms, event handlers, and
    dangerous URLs here so a prompt-injected payload can never execute.
    Pure HTML + inline <style> survives; an emptied snippet returns "".
    """
    s = str(markup or "")
    if not s.strip():
        return ""
    s = re.sub(r"(?is)<script\b.*?</script\s*>", "", s)
    s = re.sub(r"(?is)<(iframe|object|embed|link|meta|base|form|input|button|select|textarea|video|audio|source)\b[^>]*?(?:/)?>", "", s)
    s = re.sub(r"(?is)</(iframe|object|embed|form|select|textarea|video|audio)\s*>", "", s)
    s = re.sub(r'''(?i)\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)''', "", s)
    s = re.sub(r"""(?i)(href|src|xlink:href)\s*=\s*(["']?)\s*(javascript|data|vbscript)\s*:[^"'<>\s]*\2""", r"\1=#", s)
    s = re.sub(r"(?is)<style\b[^>]*>", "<style>", s)
    return s.strip()[:2000]


# ---------- Continuous-board stacking ----------
# Layout always starts at y=40, so without memory every window of a turn
# would pile onto the same spot (the old per-window sections hid this by
# rendering each window as its own SVG). The board is ONE continuous canvas
# per explanation now: shift each window's block below the turn's running
# bottom edge (+96 gap). Completion order across parallel planner threads
# may differ from spoken order — cosmetic only, the client still reveals in
# audio order. Evicted with the label cache (same cap).
_TURN_BOTTOM: dict[str, float] = {}


def _turn_shift(turn_id: str, out: list[dict]) -> None:
    """Stack this window's block below earlier windows of the same turn.
    Mutates out in place. No-op without a turn id (legacy whole-board path)
    or when the window holds no shapes."""
    if not turn_id:
        return
    shapes = [it for it in out if it["type"] in {"rectangle", "ellipse", "diamond", "text"}]
    if not shapes:
        return
    block_bottom = max(it["y"] + it["height"] for it in shapes)
    with _TURN_LOCK:
        prev = _TURN_BOTTOM.get(turn_id)
        dy = 0.0 if prev is None else (prev + 96.0) - 40.0
        _TURN_BOTTOM[turn_id] = block_bottom if prev is None else block_bottom + dy
        while len(_TURN_BOTTOM) > _TURN_CACHE_MAX:
            _TURN_BOTTOM.pop(next(iter(_TURN_BOTTOM)))
    if not dy:
        return
    for it in out:
        if it["type"] in {"rectangle", "ellipse", "diamond", "text", "arrow"}:
            it["y"] = max(-2000, min(6000, it["y"] + dy))


def normalize(raw: object) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("elements"), list):
        return None
    allowed = {"rectangle", "ellipse", "diamond", "text", "arrow", "code", "note", "table", "quiz", "html"}
    elements = []
    seen = set()
    for item in raw["elements"][:DIAGRAM_MAX_ELEMENTS]:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()[:80]
        item_type = str(item.get("type", "")).strip()
        if not item_id or item_id in seen or item_type not in allowed:
            continue
        seen.add(item_id)
        try:
            x = max(-2000, min(2000, float(item.get("x", 80))))
            y = max(-2000, min(2000, float(item.get("y", 80))))
        except (TypeError, ValueError):
            x, y = 80.0, 80.0
        normalized = {"id": item_id, "type": item_type, "x": x, "y": y}
        for key, default in (("width", 180), ("height", 84)):
            try:
                normalized[key] = max(40, min(600, float(item.get(key, default))))
            except (TypeError, ValueError):
                normalized[key] = default
        if item_type in {"rectangle", "ellipse", "diamond", "text", "code", "note", "table", "quiz", "html"}:
            # Recap notes hold 3 short bullets — roomier cap so takeaways fit.
            cap = 600 if item_type == "code" else (420 if item_type == "note" else DIAGRAM_MAX_TEXT)
            normalized["text"] = _board_text(item.get("text", ""))[:cap]
            side = str(item.get("side", "")).strip().lower()[:8]
            if side in ("left", "right"):
                normalized["side"] = side
            tone = str(item.get("tone", "")).strip().lower()[:8]
            if tone in ("core", "example", "warn"):
                normalized["tone"] = tone
            if item_type == "code":
                # Exact snippet, Devanagari-stripped text stays in "text" too.
                snippet = str(item.get("code", "") or "").strip()[:600]
                if snippet:
                    normalized["code"] = snippet
                lang = re.sub(r"[^A-Za-z0-9#+_-]", "", str(item.get("language", ""))).strip()[:16]
                if lang:
                    normalized["language"] = lang
            trigger = re.sub(r"[^A-Za-z0-9 ]+", "", str(item.get("trigger", ""))).strip()[:60]
            if item_type == "html":
                markup = _sanitize_html(item.get("html", ""))
                if markup:
                    normalized["html"] = markup
                try:
                    normalized["height"] = max(120, min(420, int(item.get("height", 220))))
                except (TypeError, ValueError):
                    normalized["height"] = 220
            if item_type == "table":
                # headers 2-4 cols, rows up to 6, cells short; pad ragged rows.
                def _cell(v):
                    return _board_text(v)[:60]
                headers = [_cell(h) for h in (item.get("headers") or []) if _cell(h)][:4]
                raw_rows = item.get("rows") or []
                rows = []
                for r in raw_rows[:6]:
                    cells = [_cell(c) for c in (list(r) if isinstance(r, (list, tuple)) else [r])]
                    if any(cells):
                        rows.append(cells)
                width = max([len(headers)] + [len(r) for r in rows] + [1])
                width = min(width, 4)
                headers = (headers + [""] * width)[:width]
                rows = [(r + [""] * width)[:width] for r in rows]
                if headers or rows:
                    normalized["headers"] = headers
                    normalized["rows"] = rows
            if item_type == "quiz":
                opts = [_board_text(o)[:60] for o in (item.get("options") or [])]
                opts = [o for o in opts if o][:4]
                if opts:
                    normalized["options"] = opts
                try:
                    ans = int(item.get("answer", -1))
                except (TypeError, ValueError):
                    ans = -1
                # Valid index -> scored quiz; missing/invalid -> reflection
                # question (tap to reveal the explanation, no right/wrong).
                normalized["answer"] = ans if 0 <= ans < len(opts) else None
                expl = _board_text(item.get("explanation", ""))[:200]
                if expl:
                    normalized["explanation"] = expl
            if trigger:
                normalized["trigger"] = trigger
                # Bilingual sync: the client matches triggers against the SPOKEN
                # caption, which is Devanagari-only ("क्वेरी सेलेक्टर"), while
                # the LLM returns English ("query selector"). Precompute the
                # spoken form so App.jsx can match without transliterating.
                try:
                    from server.speech.normalization import _devanagari_only as _to_hi
                    hi = _to_hi(trigger).strip()[:60]
                    if hi and hi.lower() != trigger.lower():
                        normalized["trigger_hi"] = hi
                except Exception:
                    pass
        if item_type == "arrow":
            normalized["startNodeId"] = str(item.get("startNodeId", "")).strip()[:80]
            normalized["endNodeId"] = str(item.get("endNodeId", "")).strip()[:80]
        color = str(item.get("backgroundColor", "")).strip()
        if color == "transparent" or re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            normalized["backgroundColor"] = color
        elements.append(normalized)
    boxes = {
        item["id"]: (item["x"], item["y"], item["width"], item["height"])
        for item in elements
        if item["type"] in {"rectangle", "ellipse", "diamond", "text"} and str(item.get("text", "")).strip()
    }
    for item in elements:
        # Arrow geometry is computed HERE from the endpoint boxes — never
        # trusted from the LLM (it omits arrow x/y, which used to pile every
        # arrow at 80,80 as floating lines detached from the boxes).
        if item["type"] == "arrow":
            _arrow_geometry(item, boxes)
    nodes = set(boxes)
    def _kept(item):
        if item["type"] == "arrow":
            return item.get("startNodeId") in nodes and item.get("endNodeId") in nodes
        if item["type"] in ("code", "note"):
            return bool(str(item.get("text", "")).strip() or str(item.get("code", "")).strip())
        if item["type"] == "table":
            return bool(item.get("headers") or item.get("rows"))
        if item["type"] == "quiz":
            return bool(str(item.get("text", "")).strip() and len(item.get("options") or []) >= 2)
        if item["type"] == "html":
            return bool(str(item.get("html", "")).strip())
        return bool(str(item.get("text", "")).strip())
    elements = [item for item in elements if _kept(item)]
    return {"elements": elements} if elements else None


def generate(
    key: str,
    text: str,
    history: list[dict],
    stop_evt: threading.Event,
    *,
    client,
    url: str,
    model: str,
    reasoning_effort: str,
) -> dict | None:
    if stop_evt.is_set():
        return None
    payload = {
        "model": model,
        "messages": _prompt(text, history),
        "tools": [DIAGRAM_TOOL],
        "tool_choice": "auto",
        "temperature": 0.2,
        "max_tokens": 900,
    }
    if reasoning_effort and "gpt-oss" in model:
        payload["reasoning_effort"] = reasoning_effort
    response = client.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    message = (response.json().get("choices") or [{}])[0].get("message") or {}
    arguments = None
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name") == "draw_flowchart_or_diagram":
            arguments = function.get("arguments")
            break
    if not arguments:
        return None
    try:
        diagram = normalize(json.loads(arguments))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return diagram if diagram and not stop_evt.is_set() else None
