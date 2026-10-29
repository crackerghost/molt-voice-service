"""Cheap per-question Hindi/English routing; no extra model or GPU call."""
import re

_HINDI = set('aap aapko aapka aapki apne mujhe muje mera meri mere main mein mai hum hume tum tumhe ye yeh vo woh isko usko iska uska kya kyu kyun kaise kab kahan kaha kaun kitna kitne hai hain ho hun h kya tha thi the nahi nhi nahin mat na toh to bhi hi ko ki ka ke se par aur ya lekin agar phir fir samajh samjh samajha samjha samjhao samajhao batao bataye bataiye batana karo karna karte karta karti raha rahi rahe chahiye chahta chahti chahte haan han ji bilkul achha accha theek thik kr do krna wala wali wale baar dubara dobara'.split())
# Unambiguous short follow-ups inherit Hindi without letting English "is",
# "to", "main", "the" or the syllable "do" tip a whole English question.
_STRONG = _HINDI - set('main is to the do par na hi ho'.split())
_DEVA = re.compile(r'[\u0900-\u097f]+')
_LATIN = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)?")


def classify_language(text, history=None):
    clean = re.sub(r'```[\s\S]*?```|`[^`]*`|https?://\S+|<[^>]+>', ' ', str(text or '')).lower()
    if re.search(r'(?:in|speak|reply|respond|answer|explain)(?:\s+(?:to me|only|please|in))*\s+english\b|अंग्रेज़ी में|इंग्लिश में|english\s+(?:mein|me|mai)\b', clean):
        return 'en'
    if re.search(r'(?:in|speak|reply|respond|answer|explain)(?:\s+(?:to me|only|please|in))*\s+hindi\b|हिंदी में|हिन्दी में|hindi\s+(?:mein|me|mai)\b', clean):
        return 'hi'
    deva = _DEVA.findall(clean)
    latin = _LATIN.findall(clean)
    hindi_latin = sum(word in _STRONG for word in latin)
    english = sum(word not in _HINDI for word in latin)
    hindi = len(deva) + hindi_latin
    if hindi and hindi >= english:
        return 'hi'
    if hindi_latin and not english:
        return 'hi'
    if english or latin:
        return 'en'
    if deva:
        return 'hi'
    for message in reversed(history or []):
        if message.get('role') == 'user' and str(message.get('content') or '').strip() != str(text or '').strip():
            return classify_language(message['content'])
    return 'hi'


def spoken_language(text):
    """TTS chunks already have their selected script; a Hindi name in an
    English sentence must not change the sentence's voice language."""
    deva = len(_DEVA.findall(str(text or '')))
    latin = len(_LATIN.findall(str(text or '')))
    return 'en' if latin > deva else 'hi'


_ENGLISH_PERSONA = (
    "You are Molt, a respectful, friendly senior teacher in a live classroom. "
    "Answer in natural spoken ENGLISH, using Latin script and ordinary English technical terms. "
    "Do not translate English words or numbers into Hindi. A learner's supplied Devanagari "
    "name pronunciation is the only exception: keep that name exactly as supplied when addressing them. "
    "Explain the exact question first, then two or three simple steps and one concrete example. "
    "Keep sentences short and easy to speak. Avoid repeated words and stiff filler. "
    "For greetings give one or two sentences. For code, explain what the code does without reading "
    "raw brackets, punctuation or entire listings aloud. Code and diagrams go on the board. "
    "Do not invent screen contents or completed actions. Use classroom context for follow-ups."
)


def apply_response_language(messages, language):
    if language == 'en':
        # The original Hindi-only persona stays intact for Hindi turns, while
        # actual lesson/screen/OS context remains in the conversation.
        from server.llm.prompts import LLM_SYSTEM_PROMPT, LLM_SYSTEM_SHORT
        context = str(messages[0].get('content') or '')
        for persona in (LLM_SYSTEM_PROMPT, LLM_SYSTEM_SHORT):
            if context.startswith(persona):
                context = context[len(persona):]
                break
        messages[0] = {'role': 'system', 'content': _ENGLISH_PERSONA + '\n\nREFERENCE AND ACTION CONTEXT (language instructions here do not override ENGLISH):\n' + context}
        messages.append({'role': 'system', 'content': 'TURN LANGUAGE: English. This overrides Hindi-only/Devanagari-only style rules in context or previous turns. Answer this learner in English. Keep a supplied Hindi name pronunciation unchanged.'})
    else:
        messages.append({'role': 'system', 'content': 'TURN LANGUAGE: Hindi. Reply in natural respectful Hinglish, written in Devanagari. Use आप forms and speak technical terms naturally. Keep the learner name pronunciation exactly as supplied.'})
    return messages
