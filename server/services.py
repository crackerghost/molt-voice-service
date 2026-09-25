"""Composition-time service container (dependency injection root).

:class:`Services` is built once in :func:`server.factory.create_app` and
handed to every HTTP/WS handler factory. No handler reads module globals
or ``os.environ`` directly — everything flows through here, which is what
makes each handler independently reusable in another project::

    from server.services import build_services
    from server.config import VoiceConfig

    services = build_services(VoiceConfig.from_env("."))
    services.tts_engine.load(config.reference_audio, config.reference_text)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from server.chat.pipeline import ChatPipelineDeps
from server.config import VoiceConfig
from server.runtime import VoiceRuntime


@dataclass
class Services:
    config: VoiceConfig
    runtime: VoiceRuntime
    tts_engine: Any
    pipeline: ChatPipelineDeps = field(init=False)

    def __post_init__(self) -> None:
        from server.chat.phrases import clause_units, speech_sentence
        from server.llm import streaming as _streaming
        from server.llm.diagrams import generate_for_step
        from server.llm.os_control import plan_os_actions
        from server.speech.audio import wav_bytes
        from server.speech.pacing import pick_speed

        cfg = self.config

        def _pick_speed(sent: str, base: float = 1.2) -> float:
            return pick_speed(
                sent,
                base,
                excited_mult=cfg.speed_excited,
                dramatic_mult=cfg.speed_dramatic,
                long_mult=cfg.speed_long,
                long_chars=cfg.speed_long_chars,
                speed_min=cfg.speed_min,
                speed_max=cfg.speed_max,
            )

        self.pipeline = ChatPipelineDeps(
            config=cfg,
            tts_engine=self.tts_engine,
            llm_stream_phrases=_streaming.llm_stream_phrases,
            speech_sentence=speech_sentence,
            clause_units=clause_units,
            pick_speed=_pick_speed,
            wav_bytes=wav_bytes,
            diagram_generate=generate_for_step,
            os_plan=plan_os_actions,
        )


def build_services(config: VoiceConfig) -> Services:
    """Build the container (engine is constructed but NOT loaded)."""
    from server.speech.tts_engine import TTSConfig, TTSEngine
    from server.speech.normalization import _fix_pronunciation

    runtime = VoiceRuntime(llm_timeout=config.llm_timeout, vision_timeout=config.vision_timeout)
    engine = TTSEngine(
        TTSConfig(
            model_name=config.model_name,
            device=config.device,
            dtype=config.torch_dtype(),
            sample_rate=config.sample_rate,
            temperature=config.tts_temperature,
            default_speed=config.default_speed,
            stream_max_chars=config.stream_max_chars,
            first_window_step=config.first_window_step,
            pause_seconds=dict(config.pause_seconds),
            language=config.tts_language,
            pad_duration=config.tts_pad_s,
            fade_duration=config.tts_fade_s,
        ),
        _fix_pronunciation,
    )
    return Services(config=config, runtime=runtime, tts_engine=engine)
