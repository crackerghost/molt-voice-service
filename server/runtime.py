"""Application runtime ownership and readiness state."""

from dataclasses import dataclass, field
from threading import Lock

from server.http_clients import ProviderClients


@dataclass
class Readiness:
    tts: bool = False
    asr: bool = False
    vision: bool = False
    provider: bool = False
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.tts and self.provider

    def public(self) -> dict[str, object]:
        return {
            "status": "ready" if self.ready else "starting",
            "tts": self.tts,
            "asr": self.asr,
            "vision": self.vision,
            "provider": self.provider,
            "error": self.error,
        }


@dataclass
class VoiceRuntime:
    llm_timeout: float
    vision_timeout: float
    readiness: Readiness = field(default_factory=Readiness)
    provider_clients: ProviderClients = field(init=False)
    gpu_generate_lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        self.provider_clients = ProviderClients(
            llm_timeout=self.llm_timeout,
            vision_timeout=self.vision_timeout,
        )
