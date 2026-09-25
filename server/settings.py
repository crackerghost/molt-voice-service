"""Typed runtime settings for the Voice API."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    host: str
    port: int
    llm_timeout: float
    vision_timeout: float
    reference_audio: Path
    reference_text: str
    model_name: str
    sample_rate: int
    temperature: float
    default_speed: float
    device: str
    llm_model: str
    llm_url: str
    llm_retries: int
    diagram_enabled: bool

    @classmethod
    def from_environment(cls, root: Path) -> "Settings":
        reference_audio = Path(os.environ.get("VOICE_REF_AUDIO", "my_voice.wav")).expanduser()
        if not reference_audio.is_absolute():
            reference_audio = root / reference_audio
        return cls(
            root=root,
            host=os.environ.get("VOICE_HOST", "127.0.0.1"),
            port=int(os.environ.get("VOICE_PORT", "8000")),
            llm_timeout=float(os.environ.get("VOICE_LLM_TIMEOUT", "120.0")),
            vision_timeout=float(os.environ.get("VOICE_VISION_TIMEOUT", "90.0")),
            reference_audio=reference_audio,
            reference_text=os.environ.get(
                "VOICE_REF_TEXT",
                "कोडिंग में बहुत मज़ा आता है, बट समटाइम्स बग्स आर सो अनोइंग यार।",
            ),
            model_name=os.environ.get("OMNIVOICE_MODEL", "k2-fsa/OmniVoice"),
            sample_rate=int(os.environ.get("VOICE_SAMPLE_RATE", "24000")),
            temperature=float(os.environ.get("VOICE_TEMPERATURE", "0.3")),
            default_speed=float(os.environ.get("VOICE_SPEED", "1.2")),
            device=os.environ.get("VOICE_API_DEVICE", "").strip().lower(),
            llm_model=os.environ.get("LLM_MODEL", "openai/gpt-oss-20b"),
            llm_url=os.environ.get(
                "MISTRAL_URL",
                "https://api.groq.com/openai/v1/chat/completions",
            ),
            llm_retries=int(os.environ.get("LLM_RETRIES", "2")),
            diagram_enabled=os.environ.get("DIAGRAM_EVENTS", "1") == "1",
        )

    def public(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "model": self.model_name,
            "sample_rate": self.sample_rate,
            "llm_model": self.llm_model,
            "diagram_enabled": self.diagram_enabled,
        }
