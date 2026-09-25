"""Turn-level wiring: director -> diagram gate -> voice ack -> client queue.

Proves the live-path interplay (blocker 3) without network, models, or API
keys: a stub OpenAI-compatible client stands in for Groq/DeepSeek, and the
test replays app.py's exact turn composition:

    should_diagram = (not actions_done) and should_generate(text, ...)

plus the exact JSON contract App.jsx's agentCode queue consumes.
"""

import json
import threading
import unittest

from server.llm.diagrams import should_generate
from server.llm.os_control import (
    _DIRECTOR_SYSTEM,
    CODE_DIRECTOR_TOKENS,
    ack_block,
    plan_os_actions,
    sanitize_action,
    sanitize_os_snapshot,
    wants_code_action,
    wants_os_action,
)


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {}

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _StubClient:
    """Canned control_os tool-call reply; records budgets per call."""

    def __init__(self, actions):
        self._actions = actions
        self.calls = []

    def post(self, url, headers=None, **kw):
        payload = kw.get("json")
        self.calls.append(payload)
        return _Resp({"choices": [{"message": {
            "tool_calls": [{"function": {
                "name": "control_os",
                "arguments": json.dumps({"actions": self._actions}),
            }}],
        }}]})


def _plan(text, stub, **kw):
    return plan_os_actions(
        "key", text, {"open": ["code"], "code": {"file": "js/app.js"}},
        stop_evt=threading.Event(), client=stub,
        url="http://x", model="m", **kw,
    )


class TurnWiringTests(unittest.TestCase):
    def test_code_turn_runs_blocking_with_big_budget(self):
        text = "code me counter bana do"
        self.assertTrue(wants_os_action(text))  # blocking path + narration
        self.assertTrue(wants_code_action(text))  # 1500-token budget
        stub = _StubClient([{
            "op": "code_create", "path": "js/counter.js",
            "content": "let n = 0;",
        }])
        actions = _plan(text, stub, max_tokens=CODE_DIRECTOR_TOKENS)
        self.assertEqual(
            actions,
            [{"op": "code_create", "path": "js/counter.js", "content": "let n = 0;"}],
        )
        self.assertEqual(stub.calls[0]["max_tokens"], CODE_DIRECTOR_TOKENS)

    def test_os_turn_suppresses_diagram_and_narrates_file(self):
        """app.py composition: a turn that moved a window never draws."""
        text = "code me counter bana do"
        stub = _StubClient([{"op": "code_write", "path": "js/app.js",
                             "content": "let n = 0;", "mode": "overwrite"}])
        actions_done = _plan(text, stub)
        should_diagram = (not actions_done) and should_generate(text, [], True)
        self.assertFalse(should_diagram)
        ack = ack_block(actions_done)
        self.assertIn("js/app.js", ack)  # names the file, no phantom claims
        self.assertIn("Never claim", ack)

    def test_teaching_turn_keeps_diagram_and_moves_nothing(self):
        text = "explain photosynthesis"
        self.assertFalse(wants_os_action(text))
        actions_done = []  # blocking path not taken
        should_diagram = (not actions_done) and should_generate(text, [], True)
        self.assertTrue(should_diagram)

    def test_snapshot_carries_open_file_and_lesson(self):
        snap = sanitize_os_snapshot({
            "app": "code", "open": ["code", "browser"],
            "code": {"file": "js/app.js", "lang": "javascript", "chars": 99999},
            "lesson": {"id": "js-4", "title": "X" * 500},
            "evil": "drop me",
        })
        self.assertEqual(snap["code"], {"file": "js/app.js", "lang": "javascript"})
        self.assertEqual(snap["lesson"], {"id": "js-4"})
        self.assertNotIn("evil", snap)
        # traversal in the open-file slot is dropped, never trusted
        self.assertNotIn(
            "code", sanitize_os_snapshot({"code": {"file": "../x.js"}}),
        )

    def test_client_queue_contract(self):
        """Every code action the server can emit is exactly what App.jsx's
        agentCode queue consumes: cmd=op plus path/content/mode/find/replace."""
        cases = [
            {"op": "code_create", "path": "a.js", "content": "x"},
            {"op": "code_write", "path": "a.js", "content": "x", "mode": "append"},
            {"op": "code_edit", "path": "a.js", "find": "x", "replace": "y"},
        ]
        allowed = {"op", "path", "content", "mode", "find", "replace"}
        for raw in cases:
            action = sanitize_action(raw)
            self.assertIsNotNone(action)
            self.assertTrue(set(action) <= allowed, set(action) - allowed)
            queued = {"cmd": action["op"], **{k: v for k, v in action.items() if k != "op"}}
            self.assertEqual(queued["cmd"], raw["op"])
            self.assertEqual(queued["path"], raw["path"])

    def test_director_knows_open_file_rule(self):
        self.assertIn("code.file", _DIRECTOR_SYSTEM)
        self.assertIn("this code", _DIRECTOR_SYSTEM)


if __name__ == "__main__":
    unittest.main()
