"""Embed the voice-cloning server inside another project.

Install once (from the Voice_Cloning checkout)::

    pip install -e /path/to/Voice_Cloning
    # or: pip install -e /path/to/Voice_Cloning[mac]      (Apple Silicon ASR)
    # or: pip install -e /path/to/Voice_Cloning[linux-gpu] (Kaggle/CUDA)

Then mount or run standalone:
"""

from pathlib import Path

# 1) Standalone on its own port (reads Voice_Cloning/.env if present).
from server import create_app

app = create_app()


# 2) Explicit config (twelve-factor style — no .env needed).
def build_explicit() -> object:
    from server.config import VoiceConfig
    from server.factory import create_app as _create

    config = VoiceConfig.from_env(root=Path("."))
    # Override per deployment, e.g.:
    #   object.__setattr__(config, "port", 9000)  # frozen dataclass
    return _create(config)


# 3) Mount inside an existing FastAPI app under /voice.
def mount_into(existing_app) -> None:  # type: ignore[no-untyped-def]
    """Mount the voice API under an existing app (shares its event loop).

    Routers share the same Services container, so models load once.
    """
    existing_app.mount("/voice", app, name="voice-cloning")
