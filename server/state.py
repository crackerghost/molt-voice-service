"""Shared process runtime state for the modular Voice API."""

import threading
from dataclasses import dataclass, field

from server.http_clients import ProviderClients


@dataclass
class RuntimeState:
    llm_timeout: float
    vision_timeout: float
    provider_clients: ProviderClients = field(init=False)
    gpu_generate_lock: threading.Lock = field(default_factory=threading.Lock)
    gen_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ov_model: object | None = None
    voice_prompt: object | None = None

    def __post_init__(self):
        self.provider_clients = ProviderClients(
            llm_timeout=self.llm_timeout,
            vision_timeout=self.vision_timeout,
        )
