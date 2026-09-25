"""Screen-context blocks + intent routing (pure, service-injected).

Combines the two screen layers (VLM visual summary + OCR text) into one
system-prompt block, with intent-based routing so greetings/general chat
don't pay hundreds of context tokens while sharing is active.
"""

from __future__ import annotations

import re
import time

SCREEN_CONTEXT_TMPL = (
    "स्क्रीन कॉन्टेक्स्ट — यूज़र अभी अपनी स्क्रीन शेयर कर रहा है और तुम उसे देख सकते हो।\n"
    "नियम:\n"
    "1) OCR text सबसे सटीक ground truth है — उसे १००% सच मानो। visual summary सिर्फ़ "
    "layout/मोटा अंदाज़ा है और ग़लत हो सकता है; अगर दोनों में टकराव हो तो OCR text को "
    "मानो और visual summary के हिसाब से चीज़ें मत गढ़ो।\n"
    "2) Active tutor बनो: स्क्रीन पर दिख रही चीज़ों को सीधे reference करो — "
    "'आपके कोड में ये undefined दिख रहा है', 'ये लाइन गलत है'। OCR text से exact "
    "शब्द/एरर quote करो।\n"
    "3) जो दिख नहीं रहा, यूज़र से action मांगो — 'ये file खोलकर दिखाओ', 'उस component "
    "तक scroll करो', 'terminal का output दिखाओ'।\n"
    "4) यूज़र fix करके दिखाए तो बदलाव notice करके confirm करो — 'अब सही दिख रहा है'।\n"
    "5) OCR text में menus/notifications का noise हो सकता है — सिर्फ relevant हिस्सा उठाओ।\n"
    "6) 'स्क्रीन कॉन्टेक्स्ट' जैसे शब्द कभी यूज़र से मत बोलो — सीधे 'आपकी स्क्रीन पर …' कहो।\n"
    "7) कोई दिक्कत दिखे तो पहले बताओ क्या गड़बड़ है, फिर २-३ आसान कदम।"
)

SCREEN_PENDING_TMPL = (
    "स्क्रीन स्थिति — यूज़र अभी स्क्रीन शेयर कर रहा है, पर स्क्रीन का विश्लेषण अभी "
    "तैयार नहीं हुआ (कुछ सेकंड लगेंगे)।\n"
    "नियम:\n"
    "1) कभी मत बोलो कि स्क्रीन शेयर नहीं हुई या शेयर बटन दबाओ — स्क्रीन शेयर हो रही है।\n"
    "2) स्क्रीन शेयर की पुष्टि यूज़र से कभी माँगो नहीं — 'स्क्रीन शेयर बटन दबाया है?', "
    "'शेयर चालू करो', 'स्क्रीन दिखाओ' जैसा कुछ भी नहीं। शेयर पहले से चालू है, बस "
    "विश्लेषण लोड हो रहा है।\n"
    "3) स्क्रीन देखने की बात सिर्फ एक छोटी सी लाइन में निपटाओ — जैसे 'मैं स्क्रीन "
    "लोड कर रहा हूँ' — और उसके तुरंत बाद यूज़र के सवाल से जुड़ी कोई दूसरी बात जोड़ो "
    "या एक छोटा सवाल पूछो। इंतज़ार की बात कभी पूरा जवाब नहीं होनी चाहिए।\n"
    "4) अगर यूज़र का सवाल स्क्रीन के बिना भी answer हो सकता है तो पहले पूरा answer दो।\n"
    "5) स्क्रीन विश्लेषण अगले कुछ सेकंड में तैयार हो जाएगा — यूज़र दोबारा पूछे तो "
    "तब स्क्रीन पूरी तरह दिखेगी।"
)

_SCREEN_INTENT_RE = re.compile(
    r"("
    r"स्क्रीन|screen|विंडो|window|डिस्प्ले|display|टैब|tab\b|"
    r"देख|देखो|देखना|दिखा|दिख रहा|दिखाई|देखा|देखकर|look|see|show|visible|watch\b|"
    r"dekho|dekhiye|dekh|dikhao|dikh\s+raha|"
    r"ये\s+क्या|यह\s+क्या|यहाँ|इधर|इसमें|इसपर|is\s+par|isme|what\s+is\s+this|what\'?s\s+this|look\s+at\s+this|"
    r"यहाँ\s+क्या|idhar|yahan|here\b|"
    r"एरर|error|बग|bug|इशू|issue|प्रॉब्लम|problem|दिक्कत|dikkat|गड़बड़|gadbad|मिस्टेक|mistake|गलत|galat|wrong|"
    r"एक्सेप्शन|exception|क्रैश|crash|वार्निंग|warning|fail|"
    r"चल\s+नहीं\s+रहा|काम\s+नहीं\s+कर\s+रहा|nahi\s+chal\s+raha|chal\s+nahi\s+raha|kam\s+nahi\s+kar\s+raha|not\s+working|अटक\s+गया|stuck|"
    r"कोड|code|लाइन|line\b|सिंटैक्स|syntax|फ़ाइल|file\b|टर्मिनल|terminal|कंसोल|console|आउटपुट|output|लॉग|logs?\b|"
    r"चेक|check|इंस्पेक्ट|inspect|रिव्यू|review|फिक्स|fix|सॉल्व|solve|सुधार|सुधारो|पढ़|read|"
    r"बटन|button|फॉर्म|form|कंपोनेंट|component|वेबसाइट|website|पेज|page\b|यूआई|ui\b"
    r")",
    re.IGNORECASE,
)

_SCREEN_FOLLOWUP_RE = re.compile(
    r"^(तो\s+फिर|अब\s+क्या|आगे\s+क्या|कैसे\s+करूँ|कैसे\s+होगा|क्या\s+करूँ|फिक्स\s+कैसे|how\s+to\s+fix|what\s+next|and\s+now\??$)",
    re.IGNORECASE,
)

_GREETING_FALLBACK_RE = re.compile(
    r"^(नमस्ते|हेलो|हाय|हैलो|नमस्कार|hello|hi|hey|good\s+(morning|afternoon|evening|night)|how\s+are\s+you|who\s+are\s+you)",
    re.IGNORECASE,
)


def screen_context_block(layers: dict) -> str | None:
    parts = []
    if layers.get("desc"):
        parts.append("स्क्रीन का visual summary:\n" + layers["desc"])
    if layers.get("ocr"):
        parts.append("स्क्रीन पर अभी दिख रहा text (OCR):\n" + layers["ocr"][:1500])
    if not parts:
        return None
    return SCREEN_CONTEXT_TMPL + "\n\n" + "\n\n".join(parts)


def recent_screen_block(*, last_activity: float, recent_s: float, peek_desc, peek_ocr) -> str | None:
    """Best-effort warm-cache context for turns arriving WITHOUT a frame."""
    if time.monotonic() - last_activity > recent_s:
        return None
    layers: dict = {"ocr": "", "desc": peek_desc() or "", "ocr_text": ""}
    layers["ocr"] = peek_ocr() or ""
    return screen_context_block(layers)


def should_include_screen_context(
    text: str, history: list[dict] | None = None, *, routing_mode: str = "auto"
) -> bool:
    if routing_mode == "always":
        return True
    clean = (text or "").strip()
    if not clean:
        return False
    if _SCREEN_INTENT_RE.search(clean):
        return True
    if _GREETING_FALLBACK_RE.search(clean):
        return False
    if history and len(clean) < 40 and _SCREEN_FOLLOWUP_RE.search(clean):
        user_msgs = [m.get("content", "") for m in history if m.get("role") == "user"]
        if user_msgs and _SCREEN_INTENT_RE.search(user_msgs[-1]):
            return True
    return False
