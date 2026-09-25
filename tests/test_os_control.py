import unittest

from server.llm.os_control import (
    _DIRECTOR_SYSTEM,
    OS_CONTROL_TOOL,
    ack_block,
    describe_action,
    sanitize_action,
    sanitize_os_snapshot,
    should_direct,
    wants_code_action,
    wants_os_action,
)


class OsControlTests(unittest.TestCase):
    def test_tool_shape(self):
        fn = OS_CONTROL_TOOL["function"]
        self.assertEqual(fn["name"], "control_os")
        props = fn["parameters"]["properties"]["actions"]["items"]["properties"]
        self.assertIn("op", props)
        self.assertIn("open_app", props["op"]["enum"])
        self.assertIn("browser_navigate", props["op"]["enum"])
        self.assertIn("browser_new_tab", props["op"]["enum"])
        self.assertIn("browser_reload", props["op"]["enum"])
        self.assertIn("browser_close_tab", props["op"]["enum"])

    def test_should_direct_gates_trivia(self):
        self.assertFalse(should_direct("hi"))
        self.assertFalse(should_direct("नमस्ते"))
        self.assertFalse(should_direct(""))
        self.assertTrue(should_direct("browser me python docs kholo"))

    def test_snapshot_is_bounded(self):
        snap = sanitize_os_snapshot({
            "app": "browser",
            "open": ["browser", "notes", "evil", "browser"],
            "minimized": ["code"],
            "browserUrl": "https://x.com/" + "y" * 900,
            "whiteboardSteps": 5,
            "code": {"huge": "x" * 5000},
        })
        self.assertEqual(snap["app"], "browser")
        self.assertNotIn("evil", snap["open"])
        self.assertEqual(snap["minimized"], ["code"])
        self.assertLessEqual(len(snap["browserUrl"]), 500)
        self.assertEqual(snap["whiteboardSteps"], 5)
        self.assertNotIn("code", snap)  # code context never leaves the client
        self.assertEqual(sanitize_os_snapshot("junk"), {})

    def test_action_allowlist(self):
        self.assertEqual(
            sanitize_action({"op": "open_app", "app": "browser", "evil": 1}),
            {"op": "open_app", "app": "browser"},
        )
        self.assertEqual(
            sanitize_action({"op": "tile_app", "app": "code", "zone": "tl"}),
            {"op": "tile_app", "app": "code", "zone": "tl"},
        )
        self.assertIsNone(sanitize_action({"op": "tile_app", "app": "code", "zone": "center"}))
        self.assertIsNone(sanitize_action({"op": "open_app", "app": "terminal"}))
        self.assertIsNone(sanitize_action({"op": "rm_rf", "app": "browser"}))
        self.assertIsNone(sanitize_action("junk"))

    def test_browser_noarg_ops(self):
        self.assertEqual(sanitize_action({"op": "browser_back"}), {"op": "browser_back"})
        self.assertEqual(sanitize_action({"op": "browser_forward"}), {"op": "browser_forward"})
        self.assertEqual(sanitize_action({"op": "browser_new_tab"}), {"op": "browser_new_tab"})
        self.assertEqual(sanitize_action({"op": "browser_reload"}), {"op": "browser_reload"})
        self.assertEqual(sanitize_action({"op": "browser_close_tab"}), {"op": "browser_close_tab"})
        # extra keys are stripped, never forwarded
        self.assertEqual(
            sanitize_action({"op": "browser_reload", "target": "x", "app": "browser"}),
            {"op": "browser_reload"},
        )

    def test_browser_navigate_rejects_schemes(self):
        self.assertIsNone(sanitize_action({"op": "browser_navigate", "target": "javascript:alert(1)"}))
        self.assertIsNone(sanitize_action({"op": "browser_navigate", "target": "  DATA:text/html,x"}))
        self.assertIsNone(sanitize_action({"op": "browser_navigate", "target": "   "}))
        good = sanitize_action({"op": "browser_navigate", "target": "python docs"})
        self.assertEqual(good, {"op": "browser_navigate", "target": "python docs"})

    def test_note_add_bounds(self):
        self.assertIsNone(sanitize_action({"op": "note_add"}))
        note = sanitize_action({"op": "note_add", "title": "T" * 200, "body": "B" * 5000})
        self.assertEqual(len(note["title"]), 80)
        self.assertEqual(len(note["body"]), 2000)

    def test_snapshot_bounds_browser_tabs(self):
        snap = sanitize_os_snapshot({"app": "browser", "browserUrl": "https://x.com/", "browserTabs": 3})
        self.assertEqual(snap["browserTabs"], 3)
        snap = sanitize_os_snapshot({"browserTabs": 999})
        self.assertEqual(snap["browserTabs"], 32)
        snap = sanitize_os_snapshot({"browserTabs": 0})
        self.assertNotIn("browserTabs", snap)
        snap = sanitize_os_snapshot({"browserTabs": "junk"})
        self.assertNotIn("browserTabs", snap)

    def test_help_app_allowlisted(self):
        self.assertEqual(
            sanitize_action({"op": "open_app", "app": "help"}),
            {"op": "open_app", "app": "help"},
        )
        self.assertEqual(describe_action({"op": "open_app", "app": "help"}), "opened the Help Center")
        snap = sanitize_os_snapshot({"app": "help", "open": ["browser", "help"]})
        self.assertEqual(snap["app"], "help")
        self.assertIn("help", snap["open"])

    def test_action_gate(self):
        self.assertTrue(wants_os_action("browser kholo"))
        self.assertTrue(wants_os_action("notes me ye likh do"))
        self.assertTrue(wants_os_action("python docs dikhao"))
        self.assertTrue(wants_os_action("page reload karo"))
        self.assertTrue(wants_os_action("refresh the page"))
        self.assertTrue(wants_os_action("help center kholo"))
        # bilingual: Hindi, English, Hinglish, either script — same meaning
        self.assertTrue(wants_os_action("open browser"))
        self.assertTrue(wants_os_action("browser open karo"))
        self.assertTrue(wants_os_action("ओपन ब्राउज़र"))
        self.assertTrue(wants_os_action("browser kholo"))
        self.assertTrue(wants_os_action("clear the board"))
        self.assertTrue(wants_os_action("board saaf karo"))
        self.assertTrue(wants_os_action("open whiteboard"))
        self.assertTrue(wants_os_action("notes open karo"))
        # multilingual fast path: es/fr/de/pt + ta/te/kn/ml/bn/mr
        self.assertTrue(wants_os_action("abre el navegador"))
        self.assertTrue(wants_os_action("ouvre le navigateur"))
        self.assertTrue(wants_os_action("öffne den Browser"))
        self.assertTrue(wants_os_action("abrir nova aba"))
        self.assertTrue(wants_os_action("உலாவியை திற"))
        self.assertTrue(wants_os_action("బ్రౌజర్ తెరువు"))
        self.assertTrue(wants_os_action("ಬ್ರೌಸರ್ ತೆರೆ"))
        self.assertTrue(wants_os_action("ബ്രൗസർ തുറക്കൂ"))
        self.assertTrue(wants_os_action("ব্রাউজার খুলুন"))
        self.assertTrue(wants_os_action("ब्राउझर उघड"))
        # precision: substrings inside other words must NOT trigger
        self.assertFalse(wants_os_action("this is notable"))
        self.assertFalse(wants_os_action("about everything"))
        self.assertFalse(wants_os_action("browser kya hai?"))
        self.assertFalse(wants_os_action("ye kya hai"))
        self.assertFalse(wants_os_action("hi"))
        # teaching/screen questions about code stay OFF the blocking path
        self.assertFalse(wants_os_action("explain this code"))
        self.assertFalse(wants_os_action("ye code kya karta hai?"))
        self.assertFalse(wants_os_action("what does this code do?"))
        # explicit code-write imperatives take the blocking path + narration
        self.assertTrue(wants_os_action("write code for a counter"))
        self.assertTrue(wants_os_action("create a file app.js"))
        self.assertTrue(wants_os_action("code me counter bana do"))
        self.assertTrue(wants_os_action("edit the code to add a button"))
        self.assertTrue(wants_os_action("fix the code"))
        self.assertTrue(wants_code_action("write code for a counter"))
        self.assertTrue(wants_code_action("code likh do"))
        self.assertFalse(wants_code_action("open browser"))
        self.assertFalse(wants_code_action("explain this code"))

    def test_code_actions_sanitized(self):
        self.assertEqual(
            sanitize_action({"op": "code_create", "path": "js/app.js", "content": "let x = 1;"}),
            {"op": "code_create", "path": "js/app.js", "content": "let x = 1;"},
        )
        self.assertEqual(
            sanitize_action({"op": "code_write", "path": "index.html", "content": "<h1>hi</h1>", "mode": "append"}),
            {"op": "code_write", "path": "index.html", "content": "<h1>hi</h1>", "mode": "append"},
        )
        self.assertEqual(
            sanitize_action({"op": "code_write", "path": "a.js", "content": "x"}),
            {"op": "code_write", "path": "a.js", "content": "x", "mode": "overwrite"},
        )
        self.assertEqual(
            sanitize_action({"op": "code_edit", "path": "a.js", "find": "let x", "replace": "const x"}),
            {"op": "code_edit", "path": "a.js", "find": "let x", "replace": "const x"},
        )
        # traversal rejected; absolute paths are normalized to relative
        self.assertIsNone(sanitize_action({"op": "code_write", "path": "../evil.js", "content": "x"}))
        self.assertEqual(
            sanitize_action({"op": "code_create", "path": "/abs.js"}),
            {"op": "code_create", "path": "abs.js"},
        )
        self.assertIsNone(sanitize_action({"op": "code_write", "path": "a.js", "content": "  "}))
        self.assertIsNone(sanitize_action({"op": "code_edit", "path": "a.js", "find": "  ", "replace": "y"}))
        self.assertEqual(describe_action({"op": "code_create", "path": "a.js"}), "created file 'a.js'")
        self.assertEqual(describe_action({"op": "code_write", "path": "a.js", "mode": "append"}), "appended code to 'a.js'")
        self.assertEqual(describe_action({"op": "code_edit", "path": "a.js"}), "edited 'a.js'")
        ops = OS_CONTROL_TOOL["function"]["parameters"]["properties"]["actions"]["items"]["properties"]["op"]["enum"]
        self.assertIn("code_create", ops)
        self.assertIn("code_write", ops)
        self.assertIn("code_edit", ops)

    def test_ack_block(self):
        acts = [
            {"op": "open_app", "app": "browser"},
            {"op": "browser_navigate", "target": "python docs"},
        ]
        block = ack_block(acts)
        self.assertIn("opened the Browser", block)
        self.assertIn("python docs", block)
        self.assertIn("Devanagari", block)
        honest = ack_block([])
        self.assertIn("none", honest)
        self.assertIn("Do NOT claim", honest)
        self.assertEqual(
            describe_action({"op": "tile_app", "app": "code", "zone": "tl"}),
            "tiled the Code editor to the top-left quarter",
        )
        self.assertEqual(describe_action({"op": "browser_reload"}), "reloaded the browser page")
        self.assertEqual(describe_action({"op": "browser_close_tab"}), "closed the browser tab")

    def test_honest_ack_never_pushes_work_back_to_learner(self):
        """The learner has no window controls — the failure ack must not tell
        them to open/close/move anything themselves."""
        honest = ack_block([]).lower()
        self.assertNotIn("manually", honest)
        self.assertIn("no controls", honest)

    def test_director_owns_every_window(self):
        self.assertIn("ONLY agent that can move windows", _DIRECTOR_SYSTEM)
        self.assertIn("NEVER", _DIRECTOR_SYSTEM)
        # ...and must not hand window management back to the learner.
        self.assertIn("tell the learner to open", _DIRECTOR_SYSTEM)
        # the learner is expected to be able to speak, not to click.
        self.assertIn("speaking and typing", _DIRECTOR_SYSTEM)

    def test_director_opens_teaching_surfaces_unprompted(self):
        """Auto-teach: a teaching turn may move windows without an explicit ask."""
        self.assertIn("TEACH", _DIRECTOR_SYSTEM)
        self.assertIn("code editor", _DIRECTOR_SYSTEM)
        # definitions/small talk still move nothing.
        self.assertIn("appears by itself", _DIRECTOR_SYSTEM)


if __name__ == "__main__":
    unittest.main()
