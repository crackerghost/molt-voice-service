"""``voice_cloning`` public package API.

Lightweight: importing ``server`` never loads torch, models, or env —
everything heavy happens inside :func:`create_app`. ::

    from server import create_app, VoiceConfig

    app = create_app()  # .env + environment driven
"""

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "create_app",
    "VoiceConfig",
    "Services",
    "Settings",
    "VoiceRuntime",
    "load_dotenv",
]


def __getattr__(name: str):
    if name == "create_app":
        from server.factory import create_app as _create_app

        return _create_app
    if name in ("VoiceConfig", "load_dotenv"):
        import server.config as _config

        return getattr(_config, name)
    if name == "Services":
        from server.services import Services as _Services

        return _Services
    if name == "Settings":
        from server.settings import Settings as _Settings

        return _Settings
    if name == "VoiceRuntime":
        from server.runtime import VoiceRuntime as _VoiceRuntime

        return _VoiceRuntime
    raise AttributeError(f"module 'server' has no attribute {name!r}")
