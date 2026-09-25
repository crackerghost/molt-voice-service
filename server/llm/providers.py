"""LLM provider resolution + API-key lookup (pure, config-injected).

Supports two OpenAI-compatible providers selected per turn:
``groq`` (default) and ``deepseek``. Reads keys from ``os.environ`` only
at call time (``.env`` must already be loaded by the composition root).
"""

from __future__ import annotations

import os
from typing import Any


def groq_api_key() -> str:
    for name in ("GROQ_API_KEY", "LLM_API_KEY", "MISTRAL_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key
    return ""


def deepseek_api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def llm_api_key(provider: str | None = None) -> str:
    p = (provider or "").strip().lower()
    if p == "deepseek":
        return deepseek_api_key()
    if p == "groq":
        return groq_api_key()
    return groq_api_key() or deepseek_api_key()


def providers_available() -> list[str]:
    out = []
    if groq_api_key():
        out.append("groq")
    if deepseek_api_key():
        out.append("deepseek")
    return out


def resolve_llm(provider: str | None, config) -> dict[str, Any]:
    """Per-turn provider config: {name, key, url, model, reasoning_effort, ...}."""
    name = (provider or config.llm_provider_default).strip().lower()
    if name not in ("groq", "deepseek"):
        name = config.llm_provider_default
    if name == "deepseek":
        return {
            "name": name,
            "key": deepseek_api_key(),
            "url": config.deepseek_url,
            "model": config.deepseek_model,
            "reasoning_effort": config.deepseek_reasoning_effort,
            "thinking": {"type": config.deepseek_thinking},
            "diagram_model": config.deepseek_diagram_model,
            "diagram_thinking": {"type": "disabled"},
        }
    reasoning = config.llm_reasoning_effort if "gpt-oss" in config.llm_model else ""
    return {
        "name": name,
        "key": groq_api_key(),
        "url": config.llm_url,
        "model": config.llm_model,
        "reasoning_effort": reasoning,
        "diagram_model": config.diagram_model,
    }


class LLMRetryable(Exception):
    """Transient LLM API failure (429/5xx/network) worth retrying."""
