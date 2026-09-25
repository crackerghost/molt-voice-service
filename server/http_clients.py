"""Thread-local persistent HTTP clients used by provider integrations."""

import threading

import httpx


class ProviderClients:
    def __init__(self, *, llm_timeout: float, vision_timeout: float):
        self._llm_timeout = llm_timeout
        self._vision_timeout = vision_timeout
        self._llm_tls = threading.local()
        self._vision_tls = threading.local()

    def llm(self) -> httpx.Client:
        client = getattr(self._llm_tls, "client", None)
        if client is None:
            client = httpx.Client(timeout=self._llm_timeout, follow_redirects=True)
            self._llm_tls.client = client
        return client

    def vision(self) -> httpx.Client:
        client = getattr(self._vision_tls, "client", None)
        if client is None:
            client = httpx.Client(timeout=self._vision_timeout, follow_redirects=True)
            self._vision_tls.client = client
        return client
