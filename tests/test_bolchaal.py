"""Shuddh -> bol-chaal safety net: conversions fire, proper nouns survive.

The matcher is Devanagari word-boundary aware: short keys must not rewrite
inside longer words (उत्तर in उत्तराखंड/उत्तरी, पाठ in पाठशाला, गीत in संगीत).
"""

import unittest

from server.chat.phrases import speech_sentence
from server.speech.normalization import SHUDDH_TO_BOLCHAAL, _naturalize


class ConversionTests(unittest.TestCase):
    def test_core_mapping(self):
        self.assertIn("हेल्प", _naturalize("मुझे सहायता चाहिए"))
        self.assertIn("आंसर", _naturalize("सही उत्तर बताओ"))
        self.assertIn("टाइम", _naturalize("समय लगेगा"))
        self.assertIn("प्रोसेस", _naturalize("प्रक्रिया समझो"))
        self.assertIn("इम्पोर्टेन्ट", _naturalize("यह महत्त्वपूर्ण टॉपिक है"))
        self.assertIn("फर्स्ट स्टेप", _naturalize("पहला कदम टैग का नाम लिखना है"))

    def test_formal_imperatives(self):
        self.assertIn("बताओ", _naturalize("बताइए क्या हुआ"))
        self.assertIn("देखो", _naturalize("देखिए स्क्रीन पर"))
        self.assertIn("करो", _naturalize("ट्राई कीजिए"))

    def test_variant_spellings(self):
        self.assertIn("इम्पोर्टेन्ट", _naturalize("महत्वपूर्ण बात है"))
        self.assertIn("स्कूल", _naturalize("पाठशाला जाओ"))
        self.assertIn("सिलेबस", _naturalize("पाठ्यक्रम देखो"))


class GuardTests(unittest.TestCase):
    def test_proper_nouns_untouched(self):
        self.assertIn("उत्तर प्रदेश", _naturalize("उत्तर प्रदेश की राजधानी"))
        self.assertIn("म्यूज़िक", _naturalize("संगीत सुनो"))
        self.assertIn("सितारा", _naturalize("सितारा चमकता है"))
        self.assertIn("एक्टर", _naturalize("अभिनेता अच्छा है"))
        self.assertIn("लाइब्रेरी", _naturalize("पुस्तकालय जाओ"))
        self.assertIn("न्यूज़पेपर", _naturalize("समाचारपत्र पढ़ो"))
        self.assertIn("अर्थशास्त्र", _naturalize("अर्थशास्त्र पढ़ो"))
        self.assertIn("साफ-साफ", _naturalize("साफ-साफ बताओ"))

    def test_lab_mapping_intended(self):
        # प्रयोगशाला -> लैब is wanted Hinglish (not a guard case)
        self.assertIn("लैब", _naturalize("प्रयोगशाला में देखो"))


class BoardMathTests(unittest.TestCase):
    def test_board_words(self):
        self.assertIn("ऐरो", _naturalize("ये तीर देखो"))
        self.assertIn("बॉक्स", _naturalize("पहला डिब्बा आ गया"))
        self.assertIn("सर्कल", _naturalize("गोला बनाओ"))
        self.assertIn("लाइन", _naturalize("रेखा खींचो"))
        self.assertIn("पॉइंट", _naturalize("बिंदु लगाओ"))
        self.assertIn("पार्ट", _naturalize("किस हिस्से में डाउट है"))

    def test_math_words(self):
        self.assertIn("नंबर", _naturalize("संख्या बताओ"))
        self.assertIn("ट्रायंगल", _naturalize("त्रिभुज बनाओ"))
        self.assertIn("एंगल", _naturalize("कोण नापो"))
        self.assertIn("थ्योरी", _naturalize("सिद्धांत समझो"))
        self.assertIn("सॉल्यूशन", _naturalize("सवाल हल करो"))
        self.assertIn("एडिशन", _naturalize("जोड़ करो"))

    def test_new_guards_hold(self):
        self.assertIn("उत्तर प्रदेश", _naturalize("उत्तर प्रदेश में लैब है"))
        self.assertIn("आधार कार्ड", _naturalize("आधार कार्ड दिखाओ"))
        self.assertIn("सेंट्रल गवर्नमेंट", _naturalize("केंद्र सरकार ने कहा"))
        self.assertIn("जोड़-तोड़", _naturalize("जोड़-तोड़ मत करो"))
        self.assertIn("हल चलाना", _naturalize("हल चलाना पड़ता है"))
        self.assertIn("नीति आयोग", _naturalize("नीति आयोग की रिपोर्ट"))
        # single-word compounds stay safe via boundaries
        self.assertNotIn("आंसर", _naturalize("उत्तराखंड घूमो"))
        self.assertNotIn("ट्राई", _naturalize("प्रयोगशाला" + "ओं में"))  # प्रयोगशालाओं untouched
        self.assertIn("ज्योमेट्री", _naturalize("रेखागणित पढ़ो"))
        self.assertIn("डेसिमल", _naturalize("दशमलव हटाओ"))

    def test_no_garbage_rewrites(self):
        out = _naturalize("उत्तर प्रदेश की प्रयोगशाला")
        self.assertNotIn("आंसर", out)
        self.assertNotIn("ट्राई", out)


class PipelineTests(unittest.TestCase):
    def test_sentence_final_word_before_danda(self):
        # । (0964) must not block: "बताइए।" -> "बताओ।"
        self.assertIn("बताओ", _naturalize("समय पर बताइए।"))

    def test_colors(self):
        self.assertIn("ब्लू", _naturalize("नीला आसमान"))
        self.assertIn("रेड", _naturalize("लाल फूल"))
        self.assertIn("ग्रीन", _naturalize("हरा पत्ता"))
        self.assertIn("येलो", _naturalize("पीली बस"))
        self.assertIn("ब्लैक", _naturalize("काला जूता"))
        self.assertIn("व्हाइट", _naturalize("सफेद कपड़ा"))
        self.assertIn("पिंक", _naturalize("गुलाबी ठंड"))
        self.assertIn("ग्रीन", _naturalize("हरे पत्ते"))

    def test_color_guards_hold(self):
        self.assertIn("हरा-भरा", _naturalize("हरा-भरा मैदान"))
        self.assertIn("नीलाम", _naturalize("नीलाम होगा"))
        self.assertIn("खुशबू", _naturalize("खुशबू आ रही"))
        self.assertIn("विक्रम", _naturalize("विक्रम आया"))
        self.assertIn("दमकल", _naturalize("दमकल आई"))
        self.assertIn("मज़ाक उड़ाना", _naturalize("मज़ाक उड़ाना गलत है"))
        self.assertIn("ग्लैमर", _naturalize("चमक-दमक पसंद है"))
        self.assertIn("वादा-खिलाफी", _naturalize("वादा-खिलाफी मत करो"))

    def test_speech_sentence_end_to_end(self):
        out = speech_sentence("यह प्रक्रिया बहुत महत्त्वपूर्ण है, कृपया समय पर बताइए।")
        for bad in ("प्रक्रिया", "महत्त्वपूर्ण", "कृपया", "बताइए"):
            self.assertNotIn(bad, out)
        for good in ("प्रोसेस", "इम्पोर्टेन्ट", "प्लीज़", "बताओ"):
            self.assertIn(good, out)

    def test_normal_hinglish_passthrough(self):
        out = speech_sentence("अरे वाह, आज क्या नया सीखना है।")
        self.assertIn("अरे वाह", out)

    def test_dict_has_no_duplicate_keys(self):
        import re
        from pathlib import Path
        src = Path("server/speech/normalization.py").read_text(encoding="utf-8")
        m = re.search(r"SHUDDH_TO_BOLCHAAL = \{(.*?)\n\}", src, re.S)
        keys = re.findall(r'^\s*"([^"]+)"\s*:', m.group(1), re.M)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreater(len(keys), 400)  # ~60 -> 900+ entries


if __name__ == "__main__":
    unittest.main()
