"""Shared GPU + screen-pause coordination primitives.

Single-GPU rule: OmniVoice TTS and the local Qwen2.5-VL describe share one
device. TTS windows are short, so the VLM waits its turn via
``gpu_generate_lock``. While a chat/synth turn streams, background screen
warm-ups hold off entirely (``screen_pause`` gate) so they can't queue
behind the reply's TTS windows on the GPU lock and add first-audio latency.

Lives here (not in app.py) so both ``server.app`` and
``server.vision.service`` import the SAME objects — a second copy of any of
these would silently break mutual exclusion.
"""

import threading
from contextlib import contextmanager


gpu_generate_lock = threading.Lock()

_screen_busy_count = 0
_screen_busy_lock = threading.Lock()
_screen_resume_evt = threading.Event()


def screen_pause_begin() -> None:
    """Mark a turn as synthesizing — background screen warm-ups pause."""
    global _screen_busy_count
    with _screen_busy_lock:
        _screen_busy_count += 1


def screen_pause_end() -> None:
    """Turn finished — resume background screen warm-ups."""
    global _screen_busy_count
    with _screen_busy_lock:
        _screen_busy_count = max(0, _screen_busy_count - 1)
        if _screen_busy_count == 0:
            _screen_resume_evt.set()


def screen_busy() -> bool:
    """True while any chat/synth turn is streaming."""
    with _screen_busy_lock:
        return _screen_busy_count > 0


def wait_for_screen_resume(timeout: float = 1.0) -> bool:
    """Block until the pause gate clears; returns False on timeout."""
    result = _screen_resume_evt.wait(timeout=timeout)
    if result:
        _screen_resume_evt.clear()
    return result


@contextmanager
def screen_paused():
    """Sync pause gate for worker threads (unwinds on exceptions too)."""
    screen_pause_begin()
    try:
        yield
    finally:
        screen_pause_end()
