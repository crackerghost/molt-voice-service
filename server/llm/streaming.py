"""Streaming LLM phrase generator with retries (config-injected, no globals).

Yields ``(text, complete)`` phrases as soon as they are speakable:
``complete=True`` at sentence boundaries, ``False`` for early word-boundary
flushes that let the first TTS window start before the sentence ends.
Retries transient failures (429/5xx/network/empty) only while nothing has
been yielded yet, so a retry can never interrupt playing audio.
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from server.llm.providers import LLMRetryable

log = logging.getLogger("voice_api")

SENT_END_RE = re.compile(r"[।?!.\n]")


def cut_phrase(buf: str, max_chars: int) -> tuple[str, str]:
    window = buf[:max_chars]
    cut = window.rfind(" ")
    if cut > 0:
        return window[:cut].strip(), (window[cut + 1 :] + buf[max_chars:]).lstrip()
    return window.strip(), buf[max_chars:].lstrip()


def llm_stream_phrases(
    key: str,
    messages: list[dict],
    temperature: float,
    http_client: httpx.Client,
    *,
    max_tokens: int,
    retries: int,
    phrase_chars: int,
    model: str,
    url: str,
    reasoning_effort: str | None = None,
    thinking: dict | None = None,
    tools: list[dict] | None = None,
    tool_choice: object = "auto",
    tool_sink=None,
):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    total_attempts = 1 + max(0, retries)
    attempt = 0
    tok_budget = max_tokens
    while True:
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": tok_budget,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        if reasoning_effort and ("gpt-oss" in model or thinking is not None):
            payload["reasoning_effort"] = reasoning_effort
        if thinking is not None:
            payload["thinking"] = thinking
        buf = ""
        yielded = False
        retry_wait = 0.8
        # Streaming tool calls arrive as per-index argument fragments across
        # chunks — accumulate here, emit whole calls to tool_sink.
        tool_bufs: dict[int, dict] = {}

        def _flush_tool(index: int) -> bool:
            """Deliver one completed tool call (best-effort JSON parse)."""
            item = tool_bufs.pop(index, None)
            if not item or tool_sink is None:
                return False
            try:
                args = json.loads(item["args"] or "{}")
            except ValueError:
                log.warning("Inline tool call unparsable, dropping (id=%s)", item.get("id"))
                return False
            try:
                tool_sink.put({"name": item.get("name") or "", "arguments": args})
            except Exception:  # noqa: BLE001 — sink full/closed: voice unaffected
                return False
            return True

        try:
            with http_client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = r.read()[:300]
                    if r.status_code == 429 or r.status_code >= 500:
                        ra = r.headers.get("retry-after", "")
                        try:
                            retry_wait = max(retry_wait, min(float(ra), 8.0))
                        except ValueError:
                            pass
                        raise LLMRetryable(f"LLM API {r.status_code}: {body!r}")
                    raise RuntimeError(f"LLM API {r.status_code}: {body!r}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta") or {}
                    except (KeyError, IndexError, ValueError):
                        continue
                    # Tool fragments first (a chunk can carry both).
                    for tc in delta.get("tool_calls") or []:
                        try:
                            idx = int(tc.get("index", 0))
                        except (TypeError, ValueError):
                            idx = 0
                        if idx not in tool_bufs and tool_bufs:
                            # A new index means every buffered call is done.
                            for pending in list(tool_bufs):
                                if _flush_tool(pending):
                                    yielded = True
                        slot = tool_bufs.setdefault(idx, {"id": "", "name": "", "args": ""})
                        if tc.get("id"):
                            slot["id"] = str(tc["id"])
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = str(fn["name"])
                        if fn.get("arguments"):
                            slot["args"] += str(fn["arguments"])
                    delta_text = delta.get("content") or ""
                    if not delta_text:
                        continue
                    buf += delta_text
                    while True:
                        m = SENT_END_RE.search(buf)
                        if m:
                            sent = buf[: m.end()].strip()
                            buf = buf[m.end() :]
                            if sent:
                                yielded = True
                                yield sent, True
                            continue
                        if len(buf) >= phrase_chars:
                            phrase, buf = cut_phrase(buf, phrase_chars)
                            if phrase:
                                yielded = True
                                yield phrase, False
                            continue
                        break
            tail = buf.strip()
            if tail:
                yielded = True
                yield tail, True
            # Stream over: whatever tool call was still assembling is done now.
            for pending in list(tool_bufs):
                if _flush_tool(pending):
                    yielded = True
            if not yielded:
                raise LLMRetryable("LLM returned no content (token budget exhausted by reasoning?)")
            return
        except LLMRetryable as e:
            if yielded or attempt + 1 >= total_attempts:
                raise RuntimeError(str(e)) from e
            attempt += 1
            tok_budget = tok_budget * 2
            log.warning("LLM attempt %d/%d failed (%s) — retrying in %.1fs", attempt, total_attempts, e, retry_wait)
            time.sleep(retry_wait)
            retry_wait = min(retry_wait * 2, 8.0)
        except httpx.HTTPError as e:
            if yielded or attempt + 1 >= total_attempts:
                raise RuntimeError(f"LLM stream failed: {e}") from e
            attempt += 1
            log.warning("LLM attempt %d/%d network error (%s) — retrying in %.1fs", attempt, total_attempts, e, retry_wait)
            time.sleep(retry_wait)
            retry_wait = min(retry_wait * 2, 8.0)
