"""Screen helper package (intent routing + context blocks)."""

from server.screen.context import (
    SCREEN_CONTEXT_TMPL,
    SCREEN_PENDING_TMPL,
    recent_screen_block,
    screen_context_block,
    should_include_screen_context,
)

__all__ = [
    "SCREEN_CONTEXT_TMPL",
    "SCREEN_PENDING_TMPL",
    "recent_screen_block",
    "screen_context_block",
    "should_include_screen_context",
]
