"""Shared realtime protocol constants and safe event builders."""

import json
from typing import Any

PROTOCOL_VERSION = 1

START = "start"
TEXT = "text"
WINDOW = "window"
DIAGRAM = "diagram"
OS_ACTION = "os_action"
AUDIO = "audio"
DONE = "done"
ERROR = "error"
PONG = "pong"


def event(event_type: str, **payload: Any) -> str:
    return json.dumps({"protocol_version": PROTOCOL_VERSION, "type": event_type, **payload})


def error_event(message: str, *, code: str = "internal_error") -> str:
    return event(ERROR, code=code, message=message)
