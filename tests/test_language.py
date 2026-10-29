import unittest
from server.llm.language import classify_language, spoken_language, apply_response_language
from server.llm.prompts import LLM_SYSTEM_SHORT
from server.chat.phrases import speech_sentence, clause_units


class LanguageTests(unittest.TestCase):
    def test_each_question_selects_its_own_language(self):
        cases = [
            ('What does DNS do?', 'en'),
            ('I did not understand the last question, please explain it again.', 'en'),
            ('How do I use the main function in C?', 'en'),
            ('मुझे पिछला सवाल समझ नहीं आया, फिर से समझाइए।', 'hi'),
            ('mujhe last question samajh nahi aaya dubara samjhao', 'hi'),
            ('DNS ka flow mujhe samjhao', 'hi'),
            ('Explain the DNS flow, थोड़ा detail please', 'en'),
            ('Explain this code mujhe samjhao', 'en'),
            ('यह code क्या करता है?', 'hi'),
            ('haan', 'hi'), ('yes please', 'en'),
            ('Explain this in Hindi', 'hi'),
            ('मुझे DNS explain in English please', 'en'),
            ('इसको इंग्लिश में समझाइए', 'en'),
            ('mujhe samjhao ```js\nconst a = window.document.querySelector("main");\n```', 'hi'),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(classify_language(text, [{'role': 'user', 'content': 'पुराना सवाल'}]), expected)

    def test_speech_does_not_convert_english_words_or_numbers_to_hindi(self):
        output = speech_sentence('**राज**, use HTML & CSS in 2 steps.', language='en')
        self.assertIn('HTML and CSS in 2 steps', output)
        self.assertIn('राज', output)
        self.assertNotIn('दो', output)
        self.assertEqual(spoken_language(output), 'en')
        self.assertEqual(spoken_language('राज, यह एचटीएमएल का हेड टैग है।'), 'hi')

    def test_english_prompt_preserves_context_without_hindi_only_persona(self):
        messages = [{'role': 'system', 'content': LLM_SYSTEM_SHORT + '\nLesson: DNS. STUDENT SPOKEN NAME: राज'}, {'role': 'user', 'content': 'Explain DNS'}]
        apply_response_language(messages, 'en')
        self.assertIn('Lesson: DNS', messages[0]['content'])
        self.assertIn('राज', messages[0]['content'])
        self.assertNotIn(LLM_SYSTEM_SHORT, messages[0]['content'])
        self.assertIn('TURN LANGUAGE: English', messages[-1]['content'])

    def test_hindi_speech_retains_existing_pronunciation_cleanup(self):
        self.assertIn('दो', speech_sentence('यह 2 स्टेप में होगा।'))

    def test_english_words_are_not_split_at_the_letter_n(self):
        self.assertEqual(clause_units('An explanation contains functions and conditions.', 110), ['An explanation contains functions and conditions.'])
