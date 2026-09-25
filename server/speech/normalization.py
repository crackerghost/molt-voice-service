"""Speech text cleanup and Hindi pronunciation normalization."""

import re

def _preserve_code_tokens(text: str) -> str:
    """Keep code/HTML tokens speakable BEFORE _speechify strips markup.

    <html> / </head> / <a href="..."> -> " html टैग " (later maps to
    एचटीएमएल टैग via HINGLISH_TO_DEVANAGARI). Without this, teaching HTML
    speaks as "टैग्स – आदि" with every tag name eaten by the <tag> stripper,
    and attribute tags leak raw "<" into speech ("<ए एचरेफ..." in prod logs).
    """
    if not text or "<" not in text:
        return text

    def _tag_repl(m):
        name = m.group(1)
        # Single-letter tag (<a>, <p>): speak the LETTER name (ए टैग),
        # not the article/vowel (अ टैग). Longer names pass through for
        # dict mapping (html -> एचटीएमएल).
        if len(name) == 1:
            spoken = LATIN_TO_DEVANAGARI.get(name.lower(), name)
            return f" {spoken} टैग "
        return f" {name} टैग "

    # Tags WITH attributes first (<a href="x">), then bare tags (<html>).
    text = re.sub(r"</?\s*([A-Za-z][A-Za-z0-9]*)(\s[^<>]*)?>", _tag_repl, text)
    return re.sub(r"[<>]", " ", text)  # any leftover brackets -> space, never spoken


def _speechify(text: str) -> str:
    """Strip markdown/symbols/emoji and flatten to plain spoken sentences."""
    text = re.sub(r"<[^>]+>", " ", text)                    # <tag> leftovers
    text = re.sub(r"[\"'\u201c\u201d\u2018\u2019]+", "", text)  # quotes
    text = re.sub(r"[:\uFF1A]+", " ", text)  # colons are unreadable aloud ("कैसे:।" -> "कैसे।")
    text = re.sub(r"&", " और ", text)  # AT&T -> ए टी और टी
    text = re.sub(r"\+", " प्लस ", text)  # C++ -> सी प्लस प्लस
    text = re.sub(r"[()\[\]{}]+", " ", text)                 # ( ) [ ] { } break the spoken flow
    text = re.sub(r"\*+|_+|`+|#+", "", text)                # *, _, `, #
    text = re.sub(r"^\s*[-=~]{3,}\s*$", " ", text, flags=re.M)  # --- lines
    text = re.sub(r"^\s*(?:[-•]|\d+[.)]|[१२३४५६७८९०]+[.)])\s*", " ", text, flags=re.M)  # bullets/numbers
    text = re.sub(
        r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2190-\u21FF\u2B00-\u2BFF]+",
        " ",
        text,
    )  # emoji/symbols
    text = re.sub(r"[\r\n]+", " ", text)                   # newlines -> space
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


# English words the LLM may still slip into -> Devanagari, so the TTS keeps the
# Hindi voice/accent everywhere (Latin letters would be read English-accented).
HINGLISH_TO_DEVANAGARI = {
    "ai": "एआई", "app": "ऐप", "apps": "ऐप्स", "game": "गेम", "games": "गेम्स",
    "cool": "कूल", "basically": "बेसिकली", "like": "लाइक", "simple": "सिंपल",
    "fun": "फन", "data": "डेटा", "click": "क्लिक", "code": "कोड",
    "website": "वेबसाइट", "button": "बटन", "message": "मैसेज", "messages": "मैसेज",
    "tension": "टेंशन", "scene": "सीन", "chill": "चिल", "smart": "स्मार्ट",
    "think": "थिंक", "learn": "लर्न", "decision": "डिसीज़न", "example": "एग्ज़ाम्पल",
    "friend": "फ्रेंड", "google": "गूगल", "siri": "सिरी", "assistant": "असिस्टेंट",
    "question": "क्वेश्चन", "answer": "आंसर", "computer": "कंप्यूटर",
    "internet": "इंटरनेट", "online": "ऑनलाइन", "photo": "फोटो", "type": "टाइप",
    "search": "सर्च", "program": "प्रोग्राम", "programming": "प्रोग्रामिंग",
    "best": "बेस्ट", "easy": "ईज़ी", "yaar": "यार", "bhai": "भाई",
    "na": "ना", "bas": "बस", "matlab": "मतलब", "info": "इंफो",
    "power": "पावर", "capability": "कैपेबिलिटी", "super": "सुपर",
    # whole-word tech terms — exact pronunciations the letter-name fallback
    # can't know (acronyms said as words, brand names, etc.)
    "html": "एचटीएमएल", "css": "सीएसएस", "api": "एपीआई", "gpu": "जीपीयू",
    "cpu": "सीपीयू", "ui": "यूआई", "ux": "यूएक्स", "sql": "एसक्यूएल",
    "usb": "यूएसबी", "pdf": "पीडीएफ", "url": "यूआरएल", "wifi": "वाईफाई",
    "json": "जेसन", "java": "जावा", "python": "पायथन",
    "javascript": "जावास्क्रिप्ट", "linux": "लिनक्स", "whatsapp": "व्हाट्सऐप",
    "github": "गिटहब", "git": "गिट", "openai": "ओपन एआई",
    "react": "रीऐक्ट", "reactjs": "रीऐक्ट जेएस",    "chatgpt": "चैटजीपीटी", "youtube": "यूट्यूब", "android": "एंड्रॉइड",
    "npm": "एनपीएम", "aws": "एडब्ल्यूएस", "kaggle": "कैगल",
    # everyday words that slip through as Latin — say them, don't spell them
    "markup": "मार्कअप", "language": "लैंग्वेज", "languages": "लैंग्वेजेस",
    "software": "सॉफ्टवेयर", "hardware": "हार्डवेयर", "browser": "ब्राउज़र",
    "file": "फाइल", "folder": "फ़ोल्डर", "download": "डाउनलोड",
    "update": "अपडेट", "version": "वर्ज़न", "server": "सर्वर",
    "keyboard": "कीबोर्ड", "screen": "स्क्रीन", "laptop": "लैपटॉप",
    "mobile": "मोबाइल", "developer": "डेवलपर", "design": "डिज़ाइन",
    "practice": "प्रैक्टिस", "english": "इंग्लिश", "science": "साइंस",
    "teacher": "टीचर", "student": "स्टूडेंट", "college": "कॉलेज",
    "class": "क्लास", "time": "टाइम", "video": "वीडियो",
    # ---- daily courtesy / reactions (rose-roz wale) ----
    "hello": "हेलो", "hey": "हे", "hi": "हाय", "bye": "बाय",
    "thanks": "थैंक्स", "thank": "थैंक", "thankyou": "थैंक्यू",
    "sorry": "सॉरी", "please": "प्लीज़", "welcome": "वेलकम",
    "ok": "ओके", "okay": "ओके", "sure": "श्योर", "great": "ग्रेट",
    "nice": "नाइस", "awesome": "ऑसम", "perfect": "परफेक्ट",
    "done": "डन", "good": "गुड", "cool": "कूल",
    "congrats": "कॉन्ग्रैट्स", "allright": "ऑलराइट", "alright": "ऑलराइट",
    # ---- tutor classroom (tution wale) ----
    "learn": "लर्न", "teach": "टीच", "lesson": "लेसन",
    "topic": "टॉपिक", "topics": "टॉपिक्स", "chapter": "चैप्टर",
    "subject": "सब्जेक्ट", "exam": "एग्ज़ाम", "exams": "एग्ज़ाम्स",
    "test": "टेस्ट", "marks": "मार्क्स", "homework": "होमवर्क",
    "doubt": "डाउट", "doubts": "डाउट्स", "explain": "एक्सप्लेन",
    "concept": "कॉन्सेप्ट", "concepts": "कॉन्सेप्ट्स",
    "revision": "रिविज़न", "syllabus": "सिलेबस",
    "notes": "नोट्स", "note": "नोट", "home": "होम",
    "school": "स्कूल", "homeworkdone": "होमवर्क डन",
    # hinglish postpositions (latin slip -> sahi hindi word)
    "se": "से", "tak": "तक", "par": "पर", "ko": "को",
    "ka": "का", "ki": "की", "mein": "में", "me": "में",
    "ne": "ने",
    # ---- daily verbs (bol-chaal wale) ----
    "help": "हेल्प", "try": "ट्राई", "check": "चेक",
    "start": "स्टार्ट", "stop": "स्टॉप", "wait": "वेट",
    "hold": "होल्ड", "see": "सी", "look": "लुक", "show": "शो",
    "tell": "टेल", "talk": "टॉक", "speak": "स्पीक",
    "listen": "लिसन", "understand": "अंडरस्टैंड",
    "clear": "क्लियर", "confirm": "कन्फर्म", "share": "शेयर",
    "open": "ओपन", "close": "क्लोज़", "save": "सेव",
    "delete": "डिलीट", "edit": "एडिट", "send": "सेंड",
    "receive": "रिसीव", "use": "यूज़", "using": "यूज़िंग",
    "work": "वर्क", "working": "वर्किंग", "donework": "डन वर्क",
    "thinkthink": "थिंक", "manage": "मैनेज",
    # ---- adjectives / fillers ----
    "hard": "हार्ड", "difficult": "डिफिकल्ट", "fast": "फास्ट",
    "slow": "स्लो", "right": "राइट", "wrong": "रॉन्ग",
    "actually": "एक्चुअली", "generally": "जनरली",
    "normally": "नॉर्मली", "usually": "यूज़ुअली",
    "seriously": "सीरियसली", "obviously": "ऑब्वियसली",
    "definitely": "डेफिनेटली", "problem": "प्रॉब्लम",
    "solution": "सॉल्यूशन", "idea": "आइडिया",
    "moment": "मोमिंट", "second": "सेकंड", "minute": "मिनट",
    # ---- extra tech (code-debug wale) ----
    "error": "एरर", "errors": "एरर्स", "bug": "बग", "bugs": "बग्स",
    "debug": "डिबग", "deploy": "डिप्लॉय", "frontend": "फ्रंटएंड",
    "backend": "बैकएंड", "database": "डेटाबेस", "client": "क्लाइंट",
    "login": "लॉगिन", "logout": "लॉगआउट", "password": "पासवर्ड",
    "account": "अकाउंट", "profile": "प्रोफाइल", "settings": "सेटिंग्स",
    "notification": "नोटिफिकेशन", "link": "लिंक",     "tag": "टैग",
    "tags": "टैग्स", "element": "एलिमेंट", "elements": "एलिमेंट्स",
    "attribute": "एट्रिब्यूट", "attributes": "एट्रिब्यूट्स",
    # HTML tag names as spoken (so <head> says हेड, not एच ई ए डी)
    "head": "हेड", "body": "बॉडी", "title": "टाइटल", "div": "डिव",
    "span": "स्पैन", "para": "पैरा", "image": "इमेज", "img": "इमेज",
    "script": "स्क्रिप्ट", "style": "स्टाइल", "href": "एचरेफ",
    # web-dev vocabulary the tutor speaks daily (missing = letter-spelled)
    "hypertext": "हाइपरटेक्स्ट", "hyper": "हाइपर", "text": "टेक्स्ट",
    "heading": "हेडिंग", "headings": "हेडिंग्स",
    "paragraph": "पैराग्राफ", "paragraphs": "पैराग्राफ्स",
    "list": "लिस्ट", "lists": "लिस्ट्स", "hyperlink": "हाइपरलिंक",
    "src": "सोर्स", "alt": "ऑल्ट", "index": "इंडेक्स",
    "h1": "एच वन", "h2": "एच टू", "h3": "एच थ्री",
    "h4": "एच फोर", "h5": "एच फाइव", "h6": "एच सिक्स",
    "ul": "यू एल", "ol": "ओ एल", "li": "एल आई",
    "doctype": "डॉकटाइप", "meta": "मेटा", "footer": "फुटर",
    "header": "हेडर", "section": "सेक्शन", "article": "आर्टिकल",
    # ---- JS / programming keywords (were spelled एल ई टी, सी ओ एन एस टी...) ----
    "let": "लेट", "const": "कॉन्स्ट", "var": "वार",
    "function": "फंक्शन", "functions": "फंक्शन्स",
    "condition": "कंडीशन", "conditions": "कंडीशन्स",
    "conditional": "कंडीशनल",
    "if": "इफ", "else": "एल्स", "elseif": "एल्स इफ",
    "loop": "लूप", "loops": "लूप्स",
    "for": "फॉर", "while": "व्हाइल", "do": "डू",
    "foreach": "फॉर ईच", "map": "मैप", "filter": "फ़िल्टर",
    "return": "रिटर्न", "break": "ब्रेक", "continue": "कंटिन्यू",
    "new": "न्यू", "class": "क्लास", "classes": "क्लासेस",
    "object": "ऑब्जेक्ट", "objects": "ऑब्जेक्ट्स",
    "array": "अरे", "arrays": "अरेज़",
    "string": "स्ट्रिंग", "strings": "स्ट्रिंग्स",
    "number": "नंबर", "numbers": "नंबर्स",
    "boolean": "बूलियन", "null": "नल", "undefined": "अनडिफाइंड",
    "true": "ट्रू", "false": "फॉल्स",
    "variable": "वेरिएबल", "variables": "वेरिएबल्स",
    "declare": "डिक्लेयर", "assign": "असाइन",
    "parameter": "पैरामीटर", "parameters": "पैरामीटर्स",
    "argument": "आर्गुमेंट", "arguments": "आर्गुमेंट्स",
    "callback": "कॉलबैक", "promise": "प्रॉमिस",
    "async": "एसिंक", "await": "अवेट",
    "import": "इम्पोर्ट", "export": "एक्सपोर्ट",
    "fetch": "फेच", "response": "रिस्पॉन्स",
    "request": "रिक्वेस्ट", "event": "इवेंट", "events": "इवेंट्स",
    "listener": "लिसनर", "handler": "हैंडलर",
    "animation": "एनिमेशन", "animations": "एनिमेशन्स",
    "dynamic": "डायनामिक", "static": "स्टैटिक",
    "syntax": "सिंटैक्स", "logic": "लॉजिक",
    "iterate": "इटरेट", "iteration": "इटरेशन",
    "manipulation": "मैनिपुलेशन", "manipulate": "मैनिपुलेट",
    "select": "सेलेक्ट", "selector": "सेलेक्टर",
    "query": "क्वेरी", "submit": "सबमिट",
    "input": "इनपुट", "output": "आउटपुट",
    "create": "क्रिएट", "change": "चेंज", "update": "अपडेट",
    "content": "कंटेंट", "contents": "कंटेंट्स",
    "structure": "स्ट्रक्चर", "structures": "स्ट्रक्चर्स",
    "etc": "एटसेटरा",
    # ---- DOM API (split camelCase first, so these hit as words) ----
    "dom": "डॉम", "document": "डॉक्यूमेंट", "window": "विंडो",
    "get": "गेट", "set": "सेट", "by": "बाय", "id": "आईडी",
    "getelementbyid": "गेट एलिमेंट बाय आईडी",
    "queryselector": "क्वेरी सेलेक्टर",
    "queryselectorall": "क्वेरी सेलेक्टर ऑल",
    "addeventlistener": "ऐड इवेंट लिसनर",
    "removeeventlistener": "रिमूव इवेंट लिसनर",
    "innerhtml": "इनर एचटीएमएल", "innertext": "इनर टेक्स्ट",
    "textcontent": "टेक्स्ट कंटेंट", "classname": "क्लास नेम",
    "createelement": "क्रिएट एलिमेंट",
    "appendchild": "अपेंड चाइल्ड",
    # ---- closed-class function words (finite set, domain-independent) ----
    # These are the commonest Latin slips and the phonetic fallback mangles
    # several (the->थे, of->ओफ, to->टो), so they live in the static core.
    "the": "द", "a": "अ", "an": "ऐन",
    "to": "टू", "two": "टू", "do": "डू", "does": "डज़",
    "be": "बी", "he": "ही", "she": "शी", "me": "मी", "we": "वी", "who": "हू",
    "that": "दैट", "this": "दिस", "these": "दीज़", "those": "दोज़",
    "they": "दे", "them": "देम", "then": "देन", "there": "देयर",
    "than": "दैन", "their": "देअर",
    "of": "ऑफ़", "on": "ऑन", "not": "नॉट", "yes": "यस",
    "here": "हियर", "there": "देयर", "where": "वेयर", "fact": "फैक्ट",
    "now": "नाउ", "how": "हाउ", "cow": "काउ", "down": "डाउन", "town": "टाउन",
    "can": "कैन", "cannot": "कैनॉट", "could": "कुड",
    "would": "वुड", "should": "शुड",
    "has": "हैज़", "have": "हैव", "had": "हैड",
    "was": "वॉज़", "were": "वर", "got": "गॉट",
    "took": "टुक", "look": "लुक",
    # ---- connectors / helpers (missed = letter-spell, so keep explicit) ----
    "need": "नीड", "needs": "नीड्स", "and": "एंड", "or": "ऑर",
    "but": "बट", "because": "बिकॉज़", "with": "विद",
    "without": "विदाउट", "for": "फॉर", "from": "फ्रॉम",
    "you": "यू", "your": "योर", "we": "वी", "they": "दे",
    "this": "दिस", "that": "दैट", "what": "व्हाट", "when": "व्हेन",
    "how": "हाउ", "why": "व्हाई",
}

# Shuddh Hindi -> roz-marra bol-chaal (robotic feel ka root cause).
# LLM shuddh likh bhi de to TTS natural bolega. Longest-first apply.
SHUDDH_TO_BOLCHAAL = {
    "मैं आपकी क्या सहायता कर सकता हूँ": "बोलो, मेरी क्या हेल्प चाहिए",
    "मैं आपकी क्या सहायता कर सकती हूँ": "बोलो, मेरी क्या हेल्प चाहिए",
    "क्या सहायता कर सकता हूँ": "क्या हेल्प चाहिए",
    "सहायता": "हेल्प",
    "आवश्यकता": "ज़रूरत",
    "आवश्यक": "ज़रूरी",
    "जानकारी": "इंफो",
    "उदाहरण": "एग्ज़ाम्पल",
    "कृपया": "प्लीज़",
    "क्षण": "सेकंड",
    "निश्चित": "पक्का",
    "निश्चित रूप से": "पक्का",
    "शुभ": "अच्छा",
    "क्षमता": "पावर",
    "उपयोग": "यूज़",
    "प्रयोग": "ट्राई",
    "समस्या": "प्रॉब्लम",
    "ढांचा": "स्ट्रक्चर",
    "ढाँचा": "स्ट्रक्चर",
    "ढाचा": "स्ट्रक्चर",
    "समाधान": "सॉल्यूशन",
    "प्रश्न": "क्वेश्चन",
    "विषय": "सब्जेक्ट",
    "विषयों": "सब्जेक्ट्स",
    "अध्याय": "चैप्टर",
    "अध्यायों": "चैप्टर्स",
    "पाठ": "लेसन",
    "उत्तर": "आंसर",
    "शिक्षक": "टीचर",
    "विद्यार्थी": "स्टूडेंट",
    "पुस्तक": "बुक",
    "प्रतीक्षा": "वेट",
    "तुरंत": "जल्दी से",
    "शीघ्र": "जल्दी",
    "वार्तालाप": "बातचीत",
    "प्रतिक्रिया": "रिएक्शन",
    "अनुभव": "एक्सपीरियंस",
    "महत्वपूर्ण": "इम्पॉर्टेंट",
    "अत्यंत": "बहुत",
    # Spelling correction the LLM keeps making: बधिया/बढिया (with ध) said
    # as "ba-dhi-ya" — correct is बढ़िया (with ढ़). Fixes caption + speech.
    "बधिया": "बढ़िया",
    "बढिया": "बढ़िया",
    "बधीया": "बढ़िया",
    "माफ़ करना": "सॉरी",
    "माफ करना": "सॉरी",
    "माफ़ी": "सॉरी",
    "माफी": "सॉरी",
    "माफ़": "सॉरी",
    "माफ": "सॉरी",
    "क्षमा": "सॉरी",
    "एवं": "और",
    "तथा": "और",
    "आदि": "एटसेटरा",
    "सामग्री": "कंटेंट",
    "सामग्रियों": "कंटेंट्स",
    "संरचना": "स्ट्रक्चर",
    "सिर से जवाब": "सीधा जवाब",
    "किंतु": "लेकिन",
    "परंतु": "लेकिन",
    "अतः": "इसलिए",
    "यथाशीघ्र": "जल्दी से",
}
_SHUDDH_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(SHUDDH_TO_BOLCHAAL, key=len, reverse=True))
)


def _naturalize(text: str) -> str:
    """Shuddh Hindi -> daily bol-chaal before TTS (sounds identical in meaning)."""
    if not text:
        return text
    return _SHUDDH_RE.sub(lambda m: SHUDDH_TO_BOLCHAAL[m.group(0)], text)

# Letter NAMES (not bare consonants) so ANY leftover Latin text spells out
# correctly: "vpn" -> "वी पी एन", not "वपन". This is the root-cause fix for
# TTS reading acronyms as words ("HTML" -> "हटमल").
LATIN_TO_DEVANAGARI = {
    "a": "ए", "b": "बी", "c": "सी", "d": "डी", "e": "ई", "f": "एफ", "g": "जी",
    "h": "एच", "i": "आई", "j": "जे", "k": "के", "l": "एल", "m": "एम", "n": "एन",
    "o": "ओ", "p": "पी", "q": "क्यू", "r": "आर", "s": "एस", "t": "टी", "u": "यू",
    "v": "वी", "w": "डब्ल्यू", "x": "एक्स", "y": "वाई", "z": "ज़ी",
}

# Words the TTS (OmniVoice) misreads even in pure Devanagari — usually conjunct
# clusters with stacked matras (जिससे -> model merges ि+स+े and says "jisse"
# wrong / skips the double स). Fix by respelling at the SYLLABLE SEAM: a space
# spoken aloud is identical to the correct pronunciation, but the model
# segments each part cleanly. Order matters: longest keys first.
PRONUNCIATION_FIXES = {
    # double-स family (स+स conjunct with matras — the model merges them)
    "जिससे": "जिस से",
    "इससे": "इस से",
    "उससे": "उस से",
    "किससे": "किस से",
    "बससे": "बस से",
    # double-च conjunct (च्छ) — the most frequent word in spoken Hindi
    "अच्छा": "अच छा",
    "अच्छी": "अच छी",
    "अच्छे": "अच छे",
    "अच्छाः": "अच छाः",
    # conjunct + matra clusters the model reads as one garbled syllable
    "क्योंकि": "क्यों कि",
    "इसलिए": "इस लिए",
    # conversational Hinglish the LLM now uses — respelled at syllable seams
    # so OmniVoice says them like a speaker, not a textbook
    "एक्चुअली": "एक चुआ ली",
    "बेसिकली": "बे सिक ली",
    "समस्या": "सम स्या",
    "इस्तेमाल": "इस्ते माल",
    "क्षमा": "क्ष मा",
}
_PRONUNCIATION_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(PRONUNCIATION_FIXES, key=len, reverse=True))
)


def _fix_pronunciation(text: str) -> str:
    """Respell problem words so the TTS says them correctly (sounds identical)."""
    if not PRONUNCIATION_FIXES or not text:
        return text
    return _PRONUNCIATION_RE.sub(
        lambda m: PRONUNCIATION_FIXES[m.group(0)], text
    )


HAS_LATIN = re.compile(r"[A-Za-z]")

_DIGIT_HINDI = {
    "0": "शून्य", "1": "वन", "2": "टू", "3": "थ्री", "4": "फोर",
    "5": "फाइव", "6": "सिक्स", "7": "सेवन", "8": "एट", "9": "नाइन",
}


# ---------- Dynamic course layer: per-course glossary ----------
# Empty by default. The course compiler (or roadmap integration later) calls
# set_course_glossary() once per course/module — checked BEFORE the phonetic
# fallback, AFTER the static core. No code edits per subject, ever.
_COURSE_GLOSSARY: dict[str, str] = {}


def set_course_glossary(mapping: dict[str, str] | None) -> None:
    """Install this course's term -> Devanagari pronunciations.

    Example: {"photosynthesis": "फोटोसिन्थेसिस"}. Pass {} / None to clear
    (free-chat mode with no course). Realtime-safe: single dict swap.
    """
    global _COURSE_GLOSSARY
    _COURSE_GLOSSARY = {str(k).lower(): str(v) for k, v in (mapping or {}).items()}


def get_course_glossary() -> dict[str, str]:
    return dict(_COURSE_GLOSSARY)


def _lookup(word: str) -> str | None:
    """Static core first, then this course's glossary. Both exact-lowercase."""
    hit = HINGLISH_TO_DEVANAGARI.get(word)
    if hit:
        return hit
    return _COURSE_GLOSSARY.get(word)


# ---------- Generic phonetic fallback: ANY Latin word -> Devanagari ----------
# Rule-based English G2P. Approximate BY DESIGN — exact key terms belong in
# the course glossary (one compiler pass at course creation). Emits proper
# orthography (matras, halants, rakar) so speech flows with a Hindi accent.
# Letter-spelling survives ONLY for true acronyms (ALL-CAPS / vowelless).
# Each entry: (latin, sign-if-open-consonant, standalone, leaves-syllable-open?).
# open-after matters only for rules ending in र (start -> स्टार्ट needs the
# halant on the NEXT consonant).
_PHONETIC_VOWEL = sorted([
    ("igh", "ाइ", "आइ", False), ("eigh", "े", "ए", False), ("eau", "्यू", "यू", False),
    ("ee", "ी", "ई", False), ("ea", "ी", "ई", False), ("ei", "े", "ए", False),
    ("ie", "ी", "ई", False),
    ("oa", "ो", "ओ", False), ("oe", "ो", "ओ", False),
    ("oi", "ॉइ", "ऑइ", False), ("oy", "ॉय", "ऑय", False),
    ("ou", "ाउ", "आउ", False), ("ow", "ो", "ओ", False),
    ("ook", "ुक", "उक", False), ("ood", "ुड", "उड", False),
    ("oot", "ुट", "उट", False),
    ("oo", "ू", "ऊ", False),
    ("au", "ौ", "औ", False), ("aw", "ॉ", "ऑ", False),
    ("ai", "े", "ए", False), ("ay", "े", "ए", False), ("ey", "े", "ए", False),
    ("ew", "्यू", "यू", False), ("ue", "ू", "ऊ", False),
    ("ution", "्यूशन", "यूशन", False),
    ("ia", "िया", "इया", False), ("io", "ियो", "इयो", False),
    ("ar", "ार", "आर", True), ("oor", "ोर", "ओर", True),
    ("and", "ैन्ड", "ऐन्ड", False), ("andard", "ैन्डर्ड", "ऐन्डर्ड", False),
    ("oid", "ॉयड", "ऑयड", False),
    ("ashion", "ैशन", "ऐशन", False),
    ("ash", "ॉश", "ऑश", False),
], key=lambda kv: -len(kv[0]))
_PHONETIC_CLUSTER = sorted([
    ("tion", "शन"), ("sion", "शन"), ("ture", "चर"), ("sure", "शर"),
    ("th", "थ"), ("dh", "ध"), ("bh", "भ"), ("gh", "घ"), ("kh", "ख"),
    ("ch", "च"), ("sh", "श"), ("ph", "फ"), ("wh", "व्ह"),
    ("kn", "न"), ("wr", "र"), ("qu", "क्व"), ("ck", "क"),
    ("tch", "च"), ("dge", "ज"), ("ng", "ंग"), ("nk", "ंक"),
], key=lambda kv: -len(kv[0]))
_PHONETIC_CONS = {
    "b": "ब", "c": "क", "d": "ड", "f": "फ", "g": "ग", "h": "ह",
    "j": "ज", "k": "क", "l": "ल", "m": "म", "n": "न", "p": "प",
    "q": "क", "r": "र", "s": "स", "t": "ट", "v": "व", "w": "व",
    "x": "क्स", "y": "य", "z": "ज़",
}
_PHONETIC_VOWELS = frozenset("aeiou")
_PHONETIC_CONS_LETTERS = frozenset("bcdfghjklmnpqrstvwxz")
_PHONETIC_MAGIC_RE = re.compile(r"[^aeiou]{0,2}e[ds]?$")  # a/i/u + <=2 cons + (e|ed|es)


def _phonetic(word: str) -> str:
    """Approximate English word -> Devanagari. Pure function, microseconds."""
    w = word.lower()
    if not w:
        return ""
    # Word-final tails parsed as units: -ther (father/mother -> दर),
    # -ren (children -> ्रेन), -ed verbs (started/played).
    tail = ""
    if len(w) > 5 and w.endswith("ther"):
        w, tail = w[:-4], "दर"
    elif len(w) > 4 and w.endswith("ren"):
        w, tail = w[:-3], "्रेन"
    elif len(w) > 3 and w.endswith("ed") and w[-3] not in _PHONETIC_VOWELS:
        w = w[:-2]
        # Tail decided AFTER parsing the stem (needs its final sound):
        # wanted (ट) -> ेड, played (vowel) -> ड, rendered (consonant) -> nothing.
        tail = "ed"
    # word-final 'mb': b is silent (comb, bomb).
    if len(w) > 3 and w.endswith("mb"):
        w = w[:-1]
    n = len(w)
    out: list[str] = []
    open_c = False
    open_hard = False  # open on a SINGLE consonant (rakar-safe); clusters aren't
    ends_vowel = False  # last sound was a vowel (drives the -ed tail)

    def put_cons(base: str, nxt: str | None, nxt2: str | None) -> None:
        nonlocal open_c, open_hard, ends_vowel
        if open_c:
            out[-1] += "्"
        out.append(base)
        ends_vowel = False
        # Rakar / y-glide attach to this consonant: no halant now.
        if nxt == "r" and nxt2 in _PHONETIC_VOWELS:
            open_c, open_hard = True, True
        elif nxt == "y":
            open_c, open_hard = True, True
        elif nxt in _PHONETIC_CONS_LETTERS:
            out[-1] += "्"
            open_c, open_hard = False, False
        else:
            open_c, open_hard = True, True

    def put_vowel(sign: str, indep: str, leave_open: bool = False) -> None:
        nonlocal open_c, open_hard, ends_vowel
        if open_c:
            out[-1] += sign
        else:
            out.append(indep)
        open_c = leave_open
        open_hard = False
        ends_vowel = True

    def put_cluster(text: str, leave_open: bool = True) -> None:
        # Clusters end in a consonant sound (फ, थ, शन) — the next vowel
        # attaches as a matra, so they stay open by default (but never
        # rakar-hard: bathroom's थ must not become थ्र).
        nonlocal open_c, open_hard, ends_vowel
        if open_c:
            out[-1] += "्"
        out.append(text)
        open_c = leave_open
        open_hard = False
        ends_vowel = False

    i = 0
    while i < n:
        for key, sign, indep, stay_open in _PHONETIC_VOWEL:
            if w.startswith(key, i):
                put_vowel(sign, indep, stay_open)
                i += len(key)
                break
        else:
            for key, text in _PHONETIC_CLUSTER:
                if w.startswith(key, i):
                    put_cluster(text)
                    i += len(key)
                    break
            else:
                ch = w[i]
                nxt = w[i + 1] if i + 1 < n else None
                # Geminate collapse (butter/taller/dinner -> single), except
                # pp after an ऐ/ए sound (apple/happy -> प्प).
                if (ch in _PHONETIC_CONS_LETTERS and nxt == ch
                        and not (ch == "p" and out and out[-1][-1:] in ("ै", "े", "ऐ", "ए"))):
                    i += 1
                    continue
                if ch == "a":
                    rest = w[i + 1:]
                    if _PHONETIC_MAGIC_RE.fullmatch(rest):
                        put_vowel("े", "ए")
                    elif i == n - 1:
                        put_vowel("ा", "आ")  # china/idea/fa
                    elif w.startswith("all", i) and i > 0:
                        # call/ball/hall: ॉ attaches (no halant!), then fresh ल.
                        put_vowel("ॉ", "ऑ")
                        out.append("ल")
                        open_c, open_hard, ends_vowel = True, True, False
                        i += 3
                        continue
                    elif w.startswith("all", i):
                        out.append("अ")  # allow/alley/allergy
                        i += 1
                        continue
                    elif nxt == "x":
                        put_vowel("ै", "ऐ")  # tax/max/exam
                    elif w.startswith("tch", i + 1):
                        put_vowel("ै", "ऐ")  # match/catch/patch/batch
                    elif nxt == "t" and i + 2 < n and w[i + 2] == "h":
                        put_vowel("ा", "आ")  # father/bathroom
                    elif (nxt in _PHONETIC_CONS_LETTERS and i + 2 < n
                            and w[i + 2] == nxt):
                        put_vowel("ै", "ऐ")  # happy/battle/matter
                    elif (nxt in _PHONETIC_CONS_LETTERS and i + 2 < n
                            and w[i + 2] in _PHONETIC_VOWELS):
                        put_vowel("े", "ए")  # shake/paper/cable/halo
                    elif open_c:
                        open_c, open_hard, ends_vowel = False, False, False  # schwa: inherent अ
                    else:
                        out.append("अ")
                    i += 1
                    continue
                if ch == "e":
                    if i == n - 1 and open_c and n > 2:
                        open_c, open_hard, ends_vowel = False, False, False  # silent final e
                    elif w[i:] == "er":
                        # teacher/butter/water/paper: consume the r too.
                        if open_c:
                            out[-1] += "र"
                            open_c = True
                        else:
                            out.append("र")
                            open_c, open_hard = True, True
                        i += 2
                        continue
                    elif w[i:] == "en":
                        # pen/men/ten keep ए; garden/button/open take न.
                        if len(w) <= 4:
                            put_vowel("े", "ए")
                            i += 1
                        else:
                            out.append("न")
                            open_c, open_hard = True, True
                            i += 2
                        continue
                    else:
                        put_vowel("े", "ए")
                    i += 1
                    continue
                if ch == "i":
                    rest = w[i + 1:]
                    if _PHONETIC_MAGIC_RE.fullmatch(rest):
                        put_vowel("ाइ", "आइ")  # fire/tired/wire
                    elif nxt == "r" and i + 2 < n and w[i + 2] == "r":
                        put_vowel("ि", "इ")  # mirror
                    elif nxt == "r" and (i + 2 >= n or w[i + 2] in _PHONETIC_CONS_LETTERS):
                        if open_c:  # bird/first/girl/sir -> अ
                            open_c, open_hard, ends_vowel = False, False, False
                        else:
                            out.append("अ")
                    elif i == n - 1:
                        put_vowel("ी", "ई")
                    else:
                        put_vowel("ि", "इ")
                    i += 1
                    continue
                if ch == "o":
                    if nxt == "x":
                        put_vowel("ॉ", "ऑ")  # box/fox/oxygen
                    elif w[i:] == "or":
                        # mirror/error/terror -> अ (door/floor use oor)
                        if open_c:
                            open_c = False
                        else:
                            out.append("अ")
                    else:
                        put_vowel("ो", "ओ")
                    i += 1
                    continue
                if ch == "u":
                    rest = w[i + 1:]
                    if _PHONETIC_MAGIC_RE.fullmatch(rest):
                        put_vowel("्यू", "यू")  # tube/fire-rule twin
                    elif nxt == "r" and i + 2 < n and w[i + 2] in _PHONETIC_VOWELS:
                        put_vowel("ू", "ऊ")  # during/curious
                    elif i == n - 1:
                        put_vowel("ू", "ऊ")
                    else:
                        if open_c:  # schwa (but/sun/plus/hurry/under)
                            open_c, open_hard, ends_vowel = False, False, False
                        else:
                            out.append("अ")
                    i += 1
                    continue
                if ch == "y":
                    if i == n - 1 and n >= 3 and w[i - 1] in _PHONETIC_CONS_LETTERS and w[i - 2] in _PHONETIC_CONS_LETTERS:
                        put_vowel("ाय", "आय")  # fly/cry/dry/sky/spy (city/duty keep ई)
                    elif i == n - 1:
                        put_vowel("ी", "ई")
                    elif i == 0:
                        put_cons("य", nxt, None)
                    elif open_c and nxt in _PHONETIC_CONS_LETTERS:
                        put_vowel("ि", "इ")
                    elif open_c and nxt in _PHONETIC_VOWELS:
                        out[-1] += "्य"
                        open_c, open_hard, ends_vowel = False, False, False
                    else:
                        put_cons("य", nxt, None)
                    i += 1
                    continue
                if ch == "r" and open_c and open_hard and nxt in _PHONETIC_VOWELS:
                    out[-1] += "्र"  # rakar: train, brown, gravity
                    open_c, open_hard, ends_vowel = False, False, False
                    i += 1
                    continue
                if ch == "l" and w[i:] == "le":
                    # -ble = ब + ल (two syllables), NOT the ब्ल conjunct:
                    # break the peek halant the previous consonant carries.
                    if out and out[-1].endswith("्"):
                        out[-1] = out[-1][:-1]
                    out.append("ल")  # table/apple/cable/single
                    open_c, open_hard = True, True  # final ल carries inherent अ
                    i += 2
                    continue
                if ch == "c":
                    put_cons("स" if nxt in ("e", "i", "y") else "क", nxt, None)
                    i += 1
                    continue
                if ch == "g":
                    put_cons("ज" if nxt in ("e", "i") else "ग", nxt, None)
                    i += 1
                    continue
                base = _PHONETIC_CONS.get(ch)
                if base is None:
                    i += 1
                    continue
                put_cons(base, nxt, None)
                i += 1
                continue
            continue
    if tail == "ed":
        if w[-1:] in ("t", "d"):
            tail = "ेड"  # wanted/started
        elif w[-1:] in ("s", "x", "z") or w.endswith(("sh", "ch", "th")):
            tail = "्ड"  # fixed/mixed/matched/washed
        elif ends_vowel:
            tail = "ड"  # played/agreed
        else:
            tail = ""  # rendered/opened/listened: silent
    return "".join(out) + tail


def _spell_letters(token: str) -> str:
    """Letter NAMES + spoken digits (true acronyms only: ATP, DNA)."""
    out = []
    for ch in token.lower():
        if ch.isdigit():
            out.append(_DIGIT_HINDI.get(ch, ch))
        else:
            out.append(LATIN_TO_DEVANAGARI.get(ch, ""))
    return " ".join(o for o in out if o)


def _split_identifier(token: str) -> list[str]:
    """Split code identifiers so dict lookup hits words, not spell-outs.

    document.getElementById -> [document, get, Element, By, Id]
    querySelector -> [query, Selector] ; addEventListener -> [add, Event, Listener]
    Dots/underscores/hyphens split first, then camelCase / acronym boundaries.
    """
    parts: list[str] = []
    for dot_part in re.split(r"[._\-/]+", token):
        if not dot_part:
            continue
        # camelCase + acronym boundaries: HTMLDiv -> HTML Div, getId -> get Id
        spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", dot_part)
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", spaced)
        parts.extend(spaced.split())
    return parts or [token]


def _render_word(word: str) -> str:
    """One alpha word -> Devanagari: glossary/static hit, else phonetic.

    Two micro-rules for subwords (acronym case/shape is decided by caller):
    - consonant-only pair (js/db/os/tv) -> letter names (जे एस...),
    - consonant + y pair (my/by) -> ाय (माय, बाय).
    """
    low = word.lower()
    hit = _lookup(low)
    if hit:
        return hit
    if len(word) == 2:
        first, second = word[0].lower(), word[1].lower()
        cons = _PHONETIC_CONS_LETTERS - {"y"}
        if first in cons and second == "y":
            base = _PHONETIC_CONS.get(first, "")
            return (base + "ाय") if base else _spell_letters(word)  # my/by
        if first in cons and second in cons:
            return _spell_letters(word)  # js/db/os/tv/pm
    return _phonetic(word)


def _render_alpha_num(part: str) -> str:
    """Render a subword that may glue digits (h1, covid19): words phonetically."""
    out: list[str] = []
    for chunk in re.findall(r"[A-Za-z]+|\d+", part):
        if not chunk:
            continue
        if chunk[0].isdigit():
            out.append(" ".join(_DIGIT_HINDI.get(d, d) for d in chunk))
        else:
            out.append(_render_word(chunk))
    return " ".join(o for o in out if o)


def _devanagari_only(text: str) -> str:
    """Rewrite leftover Latin words as Devanagari so speech keeps the Hindi accent.

    Lookup order per word: static core -> course glossary -> true-acronym
    spelling (ATP, dna) -> generic phonetic fallback (photosynthesis ->
    फोटोसिन्थेसिस). Dotted/camelCase identifiers split first
    (getElementById -> गेट एलिमेंट बाय आईडी).
    """
    def repl(m):
        token = m.group(0)
        # Ransom-note case (MiXeD, 3+ flips) is emphasis/typo, not camelCase:
        # lowercase it so the splitter doesn't shred it into letters.
        flips = sum(
            1 for a, b in zip(token, token[1:])
            if a.isalpha() and b.isalpha()
            and (a.islower() != b.islower())
        )
        if flips > 2:
            token = token.lower()
        low = token.lower()
        hit = _lookup(low)
        if hit:
            return hit
        # True acronyms: ALL-CAPS token (ATP), vowelless (gps, tv), or
        # short with only a final 'a' (dna). Everything else is phonetic.
        alpha = re.sub(r"[^A-Za-z]", "", token)
        # y does glide duty (my/fly/gym), so it never counts as "vowelless".
        novowel = alpha and not re.search(r"[aeiouAEIOUYy]", alpha)
        final_a_only = bool(re.fullmatch(r"[^aeiouAEIOU]*[aA]", alpha))
        if alpha and (token == token.upper() and any(c.isupper() for c in token)
                      or (len(alpha) <= 3 and (novowel or final_a_only))):
            return _spell_letters(token)
        # camelCase / dotted names: joint hit, else per-part render.
        subwords = _split_identifier(token)
        if len(subwords) > 1:
            joint = "".join(subwords).lower()
            hit = _lookup(joint)
            if hit:
                return hit
            return " ".join(_render_alpha_num(s) for s in subwords)
        return _render_alpha_num(token)

    # Match dotted/chained APIs as ONE token so dots don't survive into speech
    # (document.getElementById -> डॉक्यूमेंट गेट एलिमेंट बाय आईडी, not डॉक्यूमेंट.गेट).
    out = re.sub(r"[A-Za-z]+(?:[._\-/][A-Za-z0-9]+)*\d*", repl, text) if HAS_LATIN.search(text) else text
    # Any leftover separator dots/slashes between Devanagari words become spaces —
    # a "." would otherwise be read as a sentence end (mid-word cutoff).
    out = re.sub(r"(?<=[\u0900-\u097F])[._/\-]+(?=[\u0900-\u097F])", " ", out)
    return out

