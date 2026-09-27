"""Canonical runtime configuration for the voice-cloning package.

Single source of truth for every env/.env knob. Import-time side effects
are limited to reading ``os.environ`` inside :meth:`VoiceConfig.from_env`
— importing this module never touches the network, disk (except an
explicit :func:`load_dotenv` call), or torch.

Reuse in another project::

    from server.config import VoiceConfig, load_dotenv
    from server.factory import create_app

    load_dotenv(Path(".env"))
    config = VoiceConfig.from_env(root=Path("."))
    app = create_app(config)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency): KEY=VALUE lines, comments ignored.

    Trailing inline comments are stripped (``K=V  # note`` -> ``V``), and
    quoted values keep their content until the closing quote. Existing
    process env wins over the file; blank values are treated as unset so
    code defaults apply.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        raw = value.strip()
        if raw[:1] in ('"', "'"):
            q = raw[0]
            end = raw.find(q, 1)
            value = raw if end < 0 else raw[: end + 1]
        else:
            value = raw.split("#", 1)[0]
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def _resolve_path(raw: str, root: Path) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() else root / p


def detect_device(explicit: str = "") -> str:
    """Auto-select torch device: cuda > mps > cpu (explicit wins)."""
    explicit = (explicit or "").strip().lower()
    if explicit:
        return explicit
    try:
        import torch  # local import: config stays importable without torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def detect_dtype(device: str, explicit: str = "") -> str:
    """Return 'fp16' or 'fp32'. CUDA defaults to fp16, MPS/CPU to fp32.

    NOTE: torch 2.14 segfaults in its MPS fp16 copy/cast kernel — fp32 is
    the safe MPS/CPU default. Override with VOICE_API_DTYPE=fp16 at own risk.
    """
    explicit = (explicit or "").strip().lower()
    if explicit in ("fp16", "float16"):
        return "fp16"
    if explicit in ("fp32", "float32"):
        return "fp32"
    return "fp16" if device.startswith("cuda") else "fp32"


@dataclass(frozen=True)
class VoiceConfig:
    """Every tunable knob, resolved once at startup and injected everywhere."""

    root: Path
    # server
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: tuple = ("*",)
    # voice reference
    reference_audio: Path = field(default_factory=lambda: Path("my_voice.wav"))
    reference_text: str = "कोडिंग में बहुत मज़ा आता है, बट समटाइम्स बग्स आर सो अनोइंग यार।"
    # TTS model
    model_name: str = "k2-fsa/OmniVoice"
    sample_rate: int = 24000
    num_step: int = 8
    tts_temperature: float = 0.3
    default_speed: float = 1.2
    step_min: int = 4
    step_max: int = 64
    greeting_max: int = 2
    first_window_chars: int = 40
    jitter_frames: int = 1
    tts_language: str = "hi"
    tts_pad_s: float = 0.02
    tts_fade_s: float = 0.02
    device: str = "cpu"
    dtype: str = "fp32"  # 'fp16' | 'fp32' (string; converted to torch dtype at the engine boundary)
    # pacing
    speed_excited: float = 1.12
    speed_dramatic: float = 0.92
    speed_long: float = 0.96
    speed_long_chars: int = 110
    speed_min: float = 0.3
    speed_max: float = 2.0
    # LLM
    llm_model: str = "openai/gpt-oss-20b"
    llm_temperature: float = 0.6
    llm_max_tokens: int = 550
    llm_reasoning_effort: str = "low"
    llm_url: str = "https://api.groq.com/openai/v1/chat/completions"
    llm_provider_default: str = "groq"
    llm_timeout: float = 120.0
    llm_retries: int = 2
    deepseek_url: str = "https://api.deepseek.com/chat/completions"
    deepseek_model: str = "deepseek-chat"
    deepseek_diagram_model: str = ""
    deepseek_thinking: str = "disabled"
    deepseek_reasoning_effort: str = ""
    diagram_enabled: bool = True
    diagram_plan_mode: str = "turn"  # turn = 1 rich board/turn; window = 1 small board/window
    diagram_inline: bool = True  # single brain: the answer call itself draws (sidecar planners become fallback only)
    diagram_model: str = ""
    diagram_max_tokens: int = 1000
    os_director_enabled: bool = True
    os_director_block_s: float = 5.0
    # streaming / chat shaping
    stream_max_chars: int = 75
    stream_window: int = 3
    window_char_cap: int = 150
    min_window_chars: int = 55
    max_chat_sentences: int = 6
    first_window_step: int = 2
    max_history: int = 8
    pause_seconds: dict = field(default_factory=dict)
    # vision / screen
    vision_timeout: float = 90.0
    screen_recent_s: float = 25.0
    screen_routing_mode: str = "auto"
    # web dir (built UI); empty path = skip static mount
    web_dir: Path = field(default_factory=lambda: Path("web/ui/dist"))
    serve_ui: bool = True
    # filler maskers (pre-generated cloned-voice wavs masking LLM+TTS latency)
    filler_dir: Path = field(default_factory=lambda: Path("assets/fillers"))
    filler_enabled: bool = True
    filler_threshold_ms: int = 500
    filler_mode: str = "slow"  # always | slow | off
    # cheap smart pick: parallel qwen call (~100ms) choosing the clip per
    # turn; falls back to random on timeout/failure, never blocks voice
    filler_pick_enabled: bool = True
    filler_pick_model: str = "qwen/qwen3.8-27b"
    filler_pick_timeout_s: float = 0.3

    @classmethod
    def from_env(cls, root: Path | str = ".") -> "VoiceConfig":
        root = Path(root).resolve()
        ref_audio = _resolve_path(os.environ.get("VOICE_REF_AUDIO", "my_voice.wav"), root)
        device = detect_device(os.environ.get("VOICE_API_DEVICE", ""))
        dtype = detect_dtype(device, os.environ.get("VOICE_API_DTYPE", ""))
        deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
        llm_model = os.environ.get("LLM_MODEL", "openai/gpt-oss-20b")
        provider = (os.environ.get("LLM_PROVIDER", "groq").strip().lower() or "groq")
        if provider not in ("groq", "deepseek"):
            provider = "groq"
        think_raw = os.environ.get("DEEPSEEK_THINKING", "disabled").strip().lower()
        thinking = think_raw if think_raw in ("enabled", "disabled") else "disabled"
        effort_raw = os.environ.get("DEEPSEEK_REASONING_EFFORT", "").strip().lower()
        effort = effort_raw if effort_raw in ("low", "medium", "high", "xhigh", "max") else ""

        def _pause(key: str, dflt: float) -> float:
            try:
                return float(os.environ.get(f"VOICE_PAUSE_{key}", str(dflt)))
            except ValueError:
                return dflt

        scale = float(os.environ.get("VOICE_PAUSE_SCALE", "1.0"))
        pauses = {
            ",": round(_pause("COMMA", 0.35) * scale, 3),
            ";": round(_pause("SEMI", 0.3) * scale, 3),
            ".": round(_pause("FULL", 0.4) * scale, 3),
            "?": round(_pause("QUESTION", 0.4) * scale, 3),
            "!": round(_pause("EXCLAM", 0.45) * scale, 3),
            "।": round(_pause("DANDA", 0.45) * scale, 3),
        }
        web_dir = root / "web" / "ui" / "dist"
        raw_origins = os.environ.get("VOICE_ALLOWED_ORIGINS", "*").strip() or "*"
        if raw_origins == "*":
            allowed_origins = ("*",)
        else:
            allowed_origins = tuple(
                o.strip().rstrip("/")
                for o in raw_origins.replace(";", ",").split(",")
                if o.strip()
            ) or ("*",)
        try:
            filler_pick_timeout_s = float(os.environ.get("VOICE_FILLER_PICK_TIMEOUT_S", "0.3") or 0.3)
        except ValueError:
            filler_pick_timeout_s = 0.3
        _plan_mode = os.environ.get("DIAGRAM_PLAN_MODE", "turn").strip().lower() or "turn"
        if _plan_mode not in ("turn", "window"):
            _plan_mode = "turn"
        return cls(
            root=root,
            host=os.environ.get("VOICE_HOST", "127.0.0.1"),
            port=int(os.environ.get("VOICE_PORT", "8000")),
            allowed_origins=allowed_origins,
            reference_audio=ref_audio,
            reference_text=os.environ.get(
                "VOICE_REF_TEXT",
                "कोडिंग में बहुत मज़ा आता है, बट समटाइम्स बग्स आर सो अनोइंग यार।",
            ),
            model_name=os.environ.get("OMNIVOICE_MODEL", "k2-fsa/OmniVoice"),
            sample_rate=int(os.environ.get("VOICE_SAMPLE_RATE", "24000")),
            num_step=int(os.environ.get("VOICE_NUM_STEP", "8")),
            tts_temperature=float(os.environ.get("VOICE_TEMPERATURE", "0.3")),
            default_speed=float(os.environ.get("VOICE_SPEED", "1.2")),
            step_min=int(os.environ.get("VOICE_STEP_MIN", "4")),
            step_max=int(os.environ.get("VOICE_STEP_MAX", "64")),
            greeting_max=int(os.environ.get("VOICE_GREETING_MAX", "2")),
            first_window_chars=int(os.environ.get("VOICE_FIRST_WINDOW_CHARS", "40")),
            jitter_frames=max(0, int(os.environ.get("VOICE_JITTER_FRAMES", "1"))),
            tts_language=os.environ.get("VOICE_TTS_LANGUAGE", "hi").strip().lower() or "hi",
            tts_pad_s=float(os.environ.get("VOICE_TTS_PAD_S", "0.02")),
            tts_fade_s=float(os.environ.get("VOICE_TTS_FADE_S", "0.02")),
            device=device,
            dtype=dtype,
            speed_excited=float(os.environ.get("VOICE_EXCITED_SPEED", "1.12")),
            speed_dramatic=float(os.environ.get("VOICE_DRAMATIC_SPEED", "0.92")),
            speed_long=float(os.environ.get("VOICE_LONG_SPEED", "0.96")),
            speed_long_chars=int(os.environ.get("VOICE_LONG_CHARS", "110")),
            speed_min=float(os.environ.get("VOICE_SPEED_MIN", "0.3")),
            speed_max=float(os.environ.get("VOICE_SPEED_MAX", "2.0")),
            llm_model=llm_model,
            llm_temperature=float(os.environ.get("LLM_TEMPERATURE", "0.6")),
            llm_max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "550")),
            llm_reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "low"),
            llm_url=os.environ.get("MISTRAL_URL", "https://api.groq.com/openai/v1/chat/completions"),
            llm_provider_default=provider,
            llm_timeout=float(os.environ.get("VOICE_LLM_TIMEOUT", "120.0")),
            llm_retries=int(os.environ.get("LLM_RETRIES", "2")),
            deepseek_url=os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions").strip()
            or "https://api.deepseek.com/chat/completions",
            deepseek_model=deepseek_model,
            deepseek_diagram_model=os.environ.get("DEEPSEEK_DIAGRAM_MODEL", "").strip() or deepseek_model,
            deepseek_thinking=thinking,
            deepseek_reasoning_effort=effort,
            diagram_enabled=os.environ.get("DIAGRAM_EVENTS", "1") == "1",
    diagram_plan_mode=_plan_mode,
            diagram_inline=os.environ.get("DIAGRAM_INLINE", "1") == "1",
            diagram_model=os.environ.get("DIAGRAM_MODEL", "").strip() or llm_model,
            diagram_max_tokens=int(os.environ.get("DIAGRAM_MAX_TOKENS", "1000")),
            os_director_enabled=os.environ.get("OS_DIRECTOR_EVENTS", "1") == "1",
            os_director_block_s=float(os.environ.get("OS_DIRECTOR_BLOCK_S", "5") or 5),
            stream_max_chars=int(os.environ.get("VOICE_STREAM_MAX_CHARS", "75")),
            stream_window=max(1, int(os.environ.get("VOICE_STREAM_WINDOW", "3"))),
            window_char_cap=int(os.environ.get("VOICE_WINDOW_CHARS", "150")),
            min_window_chars=int(os.environ.get("VOICE_MIN_WINDOW_CHARS", "55")),
            max_chat_sentences=int(os.environ.get("VOICE_MAX_SENTENCES", "6")),
            first_window_step=max(2, min(32, int(os.environ.get("VOICE_FIRST_STEP", "2")))),
            max_history=int(os.environ.get("VOICE_MAX_HISTORY", "8")),
            pause_seconds=pauses,
            vision_timeout=float(os.environ.get("VOICE_VISION_TIMEOUT", "90.0")),
            screen_recent_s=float(os.environ.get("SCREEN_RECENT_S", "25")),
            screen_routing_mode=os.environ.get("VOICE_SCREEN_ROUTING", "auto").strip().lower(),
            web_dir=web_dir,
            serve_ui=os.environ.get("VOICE_SERVE_UI", "1") != "0",
            filler_dir=_resolve_path(
                os.environ.get("VOICE_FILLER_DIR", "assets/fillers"), root
            ),
            filler_enabled=os.environ.get("VOICE_FILLER_ENABLED", "1") != "0",
            filler_threshold_ms=int(os.environ.get("VOICE_FILLER_THRESHOLD_MS", "500")),
            filler_mode=(
                os.environ.get("VOICE_FILLER_MODE", "slow").strip().lower() or "slow"
            ),
            filler_pick_enabled=os.environ.get("VOICE_FILLER_PICK", "1") != "0",
            filler_pick_model=(
                os.environ.get("VOICE_FILLER_PICK_MODEL", "qwen/qwen3.8-27b").strip()
                or "qwen/qwen3.8-27b"
            ),
            filler_pick_timeout_s=filler_pick_timeout_s,
        )

    def torch_dtype(self):
        import torch

        return torch.float16 if self.dtype == "fp16" else torch.float32
