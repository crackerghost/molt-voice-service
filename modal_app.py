"""Deploy the existing voice API as a Modal ASGI Web Function.

The application routes stay in ``server.factory``. This module only supplies
the Modal image, GPU, persistent model cache, reference-audio mount, and the
public HTTP/WebSocket entry point.
"""

from pathlib import Path

import modal


ROOT = Path(__file__).resolve().parent
APP_NAME = "molt-voice-service"
VOICE_VOLUME_NAME = "molt-voice-data"
MODEL_VOLUME_NAME = "molt-voice-model-cache"
SECRET_NAME = "molt-voice-secrets"

app = modal.App(APP_NAME)
voice_volume = modal.Volume.from_name(VOICE_VOLUME_NAME, create_if_missing=True)
model_volume = modal.Volume.from_name(MODEL_VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install_from_pyproject(
        str(ROOT / "pyproject.toml"),
        optional_dependencies=["linux-gpu"],
    )
    # faster-whisper's CTranslate2 backend needs CUDA 12 cuBLAS and cuDNN 9.
    # Modal supplies the host driver; the linux-gpu extra installs the user-
    # space libraries, and this registers their wheel directories for dlopen.
    .run_commands(
        "printf '%s\\n' "
        "/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib "
        "/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib "
        "> /etc/ld.so.conf.d/nvidia-python-libs.conf && ldconfig"
    )
    .env(
        {
            "HF_HOME": "/model-cache/huggingface",
            "HF_HUB_DISABLE_XET": "1",
            "VOICE_REF_AUDIO": "/voice/my_voice.wav",
            "VOICE_API_DEVICE": "cuda",
            "VOICE_API_DTYPE": "fp16",
            "VOICE_HOST": "0.0.0.0",
            "VISION_LOCAL_4BIT": "1",
        }
    )
    .add_local_dir(str(ROOT / "assets"), remote_path="/root/assets", copy=True)
    .add_local_python_source("server")
)


@app.function(
    image=image,
    gpu="T4",
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    volumes={"/model-cache": model_volume, "/voice": voice_volume},
    scaledown_window=120,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def voice_api():
    """Expose the existing REST and WebSocket API on Modal."""
    from server.app import app as fastapi_app

    return fastapi_app
