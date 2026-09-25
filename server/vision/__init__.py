"""Vision subsystem — public facade over :mod:`server.vision.service`.

Stable imports for other projects::

    from server.vision import describe_layers, warm_cache, is_ready
"""

from server.vision.service import (  # noqa: F401
    SCREEN_CACHE_TTL,
    SCREEN_STALE_DESC_S,
    SCREEN_WAIT_MAX_S,
    VISION_BACKEND,
    VISION_BASE_URL,
    VISION_LOCAL_MODEL,
    VISION_MODEL,
    _load_local_vlm as load_local_vlm,
    _load_ocr as load_ocr,
    _ocr_cache as ocr_cache,
    _ocr_lock as ocr_lock,
    _screen_backend_choice as backend_choice,
    _screen_cached_desc as cached_desc,
    _screen_cache as screen_cache,
    _screen_context as screen_context,
    _screen_layers as describe_layers,
    _screen_lock as screen_lock,
    _vision_ready as is_ready,
    _vision_ready_backend as ready_backend,
    _warm_screen_cache as warm_cache,
    _warm_screen_ocr as warm_ocr,
)

import server.vision.service as _service  # noqa: E402,F401

last_screen_activity = lambda: _service._last_screen_activity  # noqa: E731


def is_ocr_disabled() -> bool:
    return bool(_service._ocr_disabled)


def touch_screen_activity(ts: float) -> None:
    _service._last_screen_activity = ts


__all__ = [
    "SCREEN_CACHE_TTL",
    "SCREEN_STALE_DESC_S",
    "SCREEN_WAIT_MAX_S",
    "VISION_BACKEND",
    "VISION_BASE_URL",
    "VISION_LOCAL_MODEL",
    "VISION_MODEL",
    "backend_choice",
    "cached_desc",
    "describe_layers",
    "is_ocr_disabled",
    "is_ready",
    "last_screen_activity",
    "load_local_vlm",
    "load_ocr",
    "ocr_cache",
    "ocr_lock",
    "ready_backend",
    "screen_cache",
    "screen_context",
    "screen_lock",
    "touch_screen_activity",
    "warm_cache",
    "warm_ocr",
]
