# Voice_Cloning — OmniVoice Hindi Voice Assistant (राहुल)

A realtime, **echo-free**, voice-cloning Hindi voice assistant built on
[k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice) (~613M params, 600+
languages). It clones a fixed reference voice once at startup, then answers
chat turns by speaking in that voice.

- **TTS / voice cloning:** OmniVoice, fp16 on CUDA (~1.3 GB VRAM — fits any
  8 GB NVIDIA GPU), diffusion `num_step` as the quality/speed dial.
- **Conversation brain:** any OpenAI-compatible chat LLM (default
  `ministral-8b-latest` via Mistral), streamed sentence-by-sentence.
- **Voice input — OpenAI/Gemini-style, echo-free:** the browser streams the
  **AEC-processed** `getUserMedia` mic (16 kHz) to a local
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper) server
  (`/ws/asr`). Chrome's acoustic echo canceller subtracts the assistant's own
  speaker output *before* the audio is transcribed, so the assistant can never
  "hear" itself. *(No Web Speech API — its separate capture path has no echo
  reference, which caused self-conversation loops.)*
- **API only:** HTTP and WebSocket endpoints for voice, chat, ASR, and vision.
  The product UI lives in the consuming application and connects through the
  configured API base URL.

```
Voice_Cloning/
├── voice_api.py          # thin deployment entrypoint (compat; new: `python -m server`)
├── pyproject.toml        # pip-installable package (`pip install -e .`, `voice-api` script)
├── server/
│   ├── __init__.py       # public API: create_app, VoiceConfig, Services
│   ├── factory.py        # create_app() — the single composition root
│   ├── config.py         # VoiceConfig: every env/.env knob in one dataclass
│   ├── services.py       # DI container (config + runtime + TTS engine + pipeline)
│   ├── cli.py            # `python -m server` / `voice-api` (port reuse + uvicorn)
│   ├── api/              # HTTP handler factories (health/ready/config/tts/chat/vision)
│   ├── sockets/          # realtime WS factories (/ws/tts chat+TTS, /ws/asr)
│   ├── chat/pipeline.py  # 3-thread LLM -> windowing -> audio-synth pipeline
│   ├── llm/              # providers (groq/deepseek), streaming, prompts, planners
│   ├── speech/           # TTSEngine, pacing, audio bytes, normalization
│   ├── screen/           # screen-context blocks + intent routing
│   ├── asr/              # streaming Whisper/VAD/speaker-gate service + facade
│   ├── vision/           # Qwen2.5-VL describe + RapidOCR + caches + facade
│   ├── routes/           # thin FastAPI registrars (no logic)
│   └── protocol/         # realtime event builders
├── examples/embed.py     # reuse in another project (standalone / explicit / mount)
├── web/ui/               # legacy local development sandbox; not served/deployed
├── my_voice.wav          # local reference voice clip
├── start.sh              # create the environment, run the server, open UI
├── requirements.txt
└── .env.example          # documented runtime configuration
```

### Reuse in another project

```bash
pip install -e /path/to/Voice_Cloning   # exposes the `voice-api` script
```

```python
from server import create_app
app = create_app()  # .env + environment driven; serve with uvicorn

# Or mount inside an existing FastAPI app:
#   app.mount("/voice", create_app(), name="voice-cloning")
# See examples/embed.py for standalone / explicit-config / mount patterns.
```

Design rules: `create_app(config)` is the only composition root; every
handler is a factory taking the `Services` container (no module globals,
no `os.environ` reads outside `VoiceConfig`); each subpackage (`asr`,
`vision`, `speech`, `llm`, `chat`, `screen`) has a stable public facade
so it imports cleanly on its own.

---

## 1. Hardware & device selection

The code auto-selects the device/dtype at startup (override in `.env`):

| Host                    | device | dtype |
| ----------------------- | ------ | ----- |
| NVIDIA GPU (8 GB is plenty) | `cuda` | `fp16` |
| Apple Silicon (M-series)    | `mps`  | `fp32` |
| CPU-only                    | `cpu`  | `fp32` |

Quick CUDA sanity check on the target machine:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

> ⚠️ **Never copy `omnivoice-env/` from a Mac to an NVIDIA machine.** The venv
> holds a CPU/MPS torch build; torch silently falls back to CPU (very slow).
> Create the venv fresh on the GPU machine so pip installs the CUDA wheel.

## 2. Setup (local)

```bash
cd Voice_Cloning

# 1) Python env (uv recommended; or python3.11 -m venv omnivoice-env)
uv venv --python 3.11 omnivoice-env
uv pip install -r requirements.txt

# 2) Config — copy and edit (reference voice path/text, LLM key, tuning)
cp .env.example .env
#   - GROQ_API_KEY=...           (required for chat; or export the env var)
#   - VOICE_REF_AUDIO=my_voice.wav
#   - VOICE_REF_TEXT=<EXACT transcript of the clip>
```

> Inline comments in `.env` are supported: `KEY=value  # note` is parsed as
> `value`.

### Reference voice

- `my_voice.wav` must be a **3–10 s clean mono clip** with the exact transcript configured in `VOICE_REF_TEXT`.
- It is git-ignored (`*.wav`) — drop your own after cloning.

### Run

```bash
# Start the API server:
./start.sh
# …or manually:
./omnivoice-env/bin/python voice_api.py

# Liveness/readiness checks:
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

**First run downloads models:** OmniVoice weights and (on first mic use) the
faster-whisper model (`ASR_MODEL`, default `small` ≈ 460 MB) from Hugging Face.
The service does not host a browser UI; point the main application at this API.

## 3. Quality ↔ speed tuning

The main dial is diffusion `num_step` (`VOICE_NUM_STEP`):

- **32** — highest quality (official default) — roughly real-time on a
  4060/3060-class card at fp16
- **16** — default here; ~2–4× real-time on an 8 GB NVIDIA card
- **8–12** — fastest, used for the *first* audio window (`VOICE_FIRST_STEP=6`)
  so a reply starts almost instantly

Run `main.py` at a few values on your GPU and pick the highest `num_step`
whose RTF feels comfortable — that is your real quality/speed sweet spot.
Every knob is documented in `.env.example` (chat windows, VAD, pauses, pacing,
ASR cadence, …) and is served to the UI by `/api/config`.

**Pronunciation of tech terms:** the LLM is instructed to write acronyms in
Devanagari (एचटीएमएल, सीएसएस…); any Latin that still slips through is mapped
by `HINGLISH_TO_DEVANAGARI` in `voice_api.py` (whole words first — html, css,
markup, video, … — then letter NAMES so unknown acronyms spell out: vpn → वी
पी एन). Extend the dict there when a term is mispronounced.

**Known upstream issue:** OmniVoice leaks GPU memory across repeated
`generate()` calls (`k2-fsa/OmniVoice#199`). This repo applies the upstream
workaround — `torch.cuda.empty_cache()` around every call plus pulling outputs
to CPU — so long-running servers stay flat.

## 4. Voice input (mic) — requirements & tuning

- Works in **Chrome / Edge** only (AudioWorklet + WebRTC AEC).
- The assistant's audio and the mic must share the browser's audio context
  (they do). **Headphones or a lower speaker volume** help Chrome's AEC lock.
- First mic use initializes the ASR backend (one-time load + model download;
  ~460 MB for `small`). **Keep `ASR_MODEL=large-v3-turbo` and `ASR_LANG=hi`** — turbo is the
  accuracy/speed sweet spot for Hindi/Hinglish (`small`/`base`/`tiny` mangle
  it), and forcing `hi` is both faster and accurate for Hindi/Hinglish.
- **Switchable backend (`ASR_BACKEND`)** — `auto` (default) uses **mlx-whisper
  on Apple Silicon** (Neural Engine, ~10x faster than CPU Whisper on an M4;
  install: `uv pip install -p omnivoice-env/bin/python mlx-whisper`) and
  **faster-whisper everywhere else** — CUDA fp16 on Kaggle/NVIDIA, CPU int8 on
  other machines. The same repo therefore runs fast on the M4 AND on Kaggle's
  Linux GPU with no edits. `ASR_BACKEND=mlx` or `=faster-whisper` forces one.
  Note mlx-whisper has no beam decoder; `ASR_FINAL_BEAM` applies to the
  faster-whisper backend only.
- **Fastest + accurate on Kaggle / NVIDIA (recommended .env):** `ASR_BACKEND=faster-whisper`,
  `ASR_MODEL=large-v3-turbo`, `ASR_DEVICE=cuda`, `ASR_COMPUTE=float16`, `ASR_FINAL_BEAM=5`.
  large-v3-turbo is ~10-15x realtime on a T4 with the best realtime Hindi/Hinglish
  accuracy (large-v3 is ~4x slower for near-zero gain; int8_float16 is ~20% faster
  with a slight accuracy trade). OmniVoice fp16 (~1.3 GB) + turbo fp16 (~1.6 GB)
  fit Kaggle's 16 GB GPUs with room to spare. `auto` already resolves to exactly
  this on Linux+GPU — pinning just removes ambiguity.
- Want true multilingual STT? Set `ASR_LANG=` (empty = auto-detect per
  utterance). Auto-detect is great for English but routinely mislabels SHORT
  Hindi clips (as es/ru/ur/si) — that is why Hindi seemed broken.

```ini
# .env — voice input
ASR_BACKEND=auto      # auto | mlx (Apple Silicon only) | faster-whisper
ASR_MODEL=large-v3-turbo  # best Hindi/Hinglish accuracy you can run realtime; or small for a smaller download
ASR_LANG=hi           # hi = Hindi/Hinglish (fast, accurate); empty = auto-detect any language
ASR_DEVICE=           # auto: cuda on NVIDIA, cpu elsewhere (fw backend)
ASR_COMPUTE=          # auto: float16 (CUDA) / int8 (CPU) (fw backend)
ASR_FINAL_BEAM=5      # fw only: beam width for the final transcript
VOICE_ASR_PARTIAL_NEW_SECONDS=0.45   # live-caption cadence
VOICE_ASR_PARTIAL_GAP_SECONDS=0.9
VOICE_ASR_SPECULATIVE=1              # 1 = fast greedy transcript fires the reply before the beam final (lower latency)
VOICE_MIN_WINDOW_CHARS=24            # min chars a non-final TTS window must have (stops tiny 2-3 word chunks)
VOICE_SPECULATIVE_MS=5000            # how long the client waits for the final before releasing the mic anyway
VOICE_AUTO_SEND_MS=750               # end-of-speech silence tail before the utterance is sent (lower = snappier turns)
```

### Noise-immune turn-taking (server-side Silero VAD)

The browser's energy VAD opens an utterance on ANY loud sound — fans, door
slams, keyboard bursts — so Whisper transcribes noise into phantom replies.
This repo ships the professional fix: a **server-side Silero neural VAD** that
classifies speech vs non-speech per 32 ms frame (`pip install silero-vad`;
`ASR_VAD_MODE=auto` uses it when installed). In this mode the browser is a thin
continuous streamer, the server owns open/close decisions (with hysteresis,
a server-side pre-roll ring so first words are never lost, and a gate that
ignores mic audio while the assistant's own TTS plays), and noise can no
longer open a turn. Tune via `VOICE_SILERO_*` knobs in `.env.example`.

### Speaker-identity gate (your voice vs everyone else)

Silero solves *noise*, but a **competing human voice** — a video playing on
another phone, a family member talking — is still speech. This repo adds the
"Hey Siri"-style answer: a **speaker-verification gate** (Resemblyzer,
MIT-licensed). The primary speaker's voiceprint is enrolled once from the same
`VOICE_REF_AUDIO` clip used for TTS cloning; before any utterance is
transcribed, its d-vector embedding is compared (cosine similarity). Same
speaker scores ~0.75–0.95; other voices, phones, and TV audio score ~0.4–0.6
and are **silently dropped** — no transcript, no phantom reply. It fails open
(any internal error → decode proceeds) and costs ~20 ms on CPU.

Knobs (see `.env.example`):

```bash
VOICE_SPEAKER_GATE=auto       # auto = on when resemblyzer + ref clip exist
VOICE_SPEAKER_SIM_MIN=0.45    # cosine threshold; raise for stricter, lower (0.4) if your mic rejects you
                               # (live voice via Chrome AEC/NS scores ~0.49-0.55 vs the clean ref clip)
```

Kaggle notebooks give a free NVIDIA GPU (T4/P100, 16 GB) — great for
benchmarking the CUDA path. Kaggle has no microphone or browser, so test
**TTS generation + speed** there (not the live mic chat).

Because a Kaggle notebook does **not** ship your `.env`, use the bundled
helpers which set every knob inside the process:

1. Push this repo to GitHub (public) or upload a zip as a Kaggle **Dataset**.
2. Create a Notebook → `File ▸ Add input` (the repo / dataset) or clone:
   ```bash
   !git clone https://github.com/<you>/<repo>.git
   %cd /kaggle/working/Voice_Cloning
   ```
3. Install + verify CUDA:
   ```bash
   !python kaggle/setup_kaggle.sh
   ```
4. Benchmark several `num_step` values and hear the outputs:
   ```bash
   !python kaggle/benchmark_kaggle.py
   ```
   (`kaggle/Voice_Cloning_Kaggle.ipynb` is a ready-made notebook with these
   steps — upload it and run all cells.)

Notes:
- `requirements.txt` leaves the preinstalled Kaggle torch untouched.
- `MISTRAL_API_KEY` (for chat replies) can be injected via Kaggle
  **Secrets** (`Add-ons ▸ Secrets`) or `os.environ` in a cell — the ASR/TTS
  benchmarks above don't need it.
- Outputs are saved as `output_step<num>.wav` next to `main.py`; listen inline
  with `IPython.display.Audio` or download them.

## 6. Screen understanding (Qwen2.5-VL, optional)

**Push-to-see (default, `SCREEN_PUSH_MODE=1`):** instead of a continuous share
loop, **hold the screen button** — frames are captured every 400 ms while you
hold, and each is described by the vision engine in the BACKGROUND so the
compute overlaps the hold itself. Release (or hold past 5 s) auto-sends the
turn with the freshest frame; the reply then starts at the usual ~0.8 s
first-audio latency with the screen description already warm in the server
cache. When the button is up, the GPU and network do ZERO vision work — no
more background describe queue competing with TTS. Full latency analysis and
the architecture diagram: `docs/PUSH_TO_SEE_ARCHITECTURE.md`.

Legacy continuous mode (`SCREEN_PUSH_MODE=0`) still works: while sharing, the
browser captures frames, detects changes client-side (32×24 gray block-diff,
~1.2 s cadence), and describes only CHANGED screens via `POST /api/vision`.
Descriptions are cached by the client's change hash, so an unchanged screen
costs ZERO vision calls, and a changed screen is described in the BACKGROUND
before you ask — the reply itself pays no vision latency.

The UI's screen-share button lights up when a vision engine is available.

Two engines (`VISION_BACKEND`):

- **`local` / `auto` without a key — the Kaggle path.** Qwen2.5-VL-3B-Instruct
  runs IN this process (transformers, fp16 ≈ 4.5 GB VRAM on CUDA — fits a T4
  next to OmniVoice + Whisper). No API key, no extra server; the model loads
  lazily on the first screen share so boot time is unchanged.
  Needs `pip install transformers pillow accelerate` (already in
  requirements.txt).
- **`api` — hosted, no VRAM.** Any OpenAI-compatible vision endpoint:
  DashScope (default), OpenRouter, Together. Needs `VISION_API_KEY` (or
  `DASHSCOPE_API_KEY`). `auto` (default) prefers the API when a key is set
  and falls back to the local model otherwise.

```bash
# .env — screen understanding
VISION_BACKEND=auto                                        # auto | api | local
VISION_API_KEY=...                                         # hosted engine only (or DASHSCOPE_API_KEY)
VISION_LOCAL_MODEL=Qwen/Qwen2.5-VL-3B-Instruct             # local engine (default, T4-friendly)
VISION_MODEL=qwen2.5-vl-7b-instruct                        # hosted engine model
SCREEN_PUSH_MODE=1                                         # 1 = push-to-see (hold the button); 0 = continuous share
SCREEN_PUSH_MAX_MS=5000                                    # hold cap — auto-sends the turn
SCREEN_PUSH_TICK_MS=400                                    # capture cadence during the hold
```

Screen context is injected into the chat system prompt for that turn, so you
can ask "यह एरर क्यों आ रहा है?" or "इस कोड में क्या गड़बड़ है?" by voice.

## 7. Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `torch.cuda.is_available()` is `False` on the GPU box | venv was copied from another machine; recreate it there (`uv pip install -r requirements.txt`) |
| Voice input does nothing | Chrome/Edge only; check `/api/config` shows `"asr_model"`; watch the server log for the whisper load line; allow a minute on first use |
| Assistant still hears itself | Use headphones / lower volume (AEC needs a clear echo reference); confirm the reply is playing through the same tab's speakers |
| Browser UI needed | Run the consuming frontend separately and set its voice API base URL |
| Chat says "LLM API key not configured" | Add `GROQ_API_KEY` (consoles.groq.com) to `.env` and restart the server |
| Assistant answers while you're still mid-sentence (server log shows many `Processing audio with duration 00:01…` lines) | End-of-speech tail is too short — raise `VOICE_AUTO_SEND_MS` to 700–900 (it cuts off speech in 1–2 s fragments, each firing a reply) |
| Generated speech sounds flat/robotic | Raise `VOICE_NUM_STEP`, and/or re-record a cleaner `my_voice.wav` with clear pauses |

## License & ethics

OmniVoice is Apache-2.0. Voice cloning can be misused: only clone voices you
own or have permission to use, and comply with local law.
