# voice-service — 8GB GPU laptop deploy (ONE API endpoint)

This folder is a **standalone copy** of `realtime-human-tutor/Voice_Cloning`.
It is intentionally isolated: the main site (`src/`, `backend/`) never imports
it. The only connection is over HTTP/WS through **one base URL**.

```
notmybug/
├── src/                 ← main frontend (Vercel / your PC)
│   └── services/voiceAgent.js   ← talks to the GPU laptop (this file)
├── backend/             ← main Express API (unchanged)
└── voice-service/       ← THIS — upload only this to the 8GB GPU laptop
    ├── server/          ← FastAPI app (TTS + chat + vision + WS)
    ├── requirements.txt / pyproject.toml
    ├── .env.example     ← copy to .env on the laptop, fill keys
    ├── my_voice.wav     ← reference voice (git-ignored, copy manually!)
    └── web/ui/          ← bundled tutor UI (optional, rebuild on laptop)
```

## 1. Upload to the GPU laptop

Copy **only** `voice-service/` (not the whole repo):

```bash
# from this machine — excludes venv, caches, secrets
rsync -av --exclude='omnivoice-env/' --exclude='__pycache__/' \
  --exclude='node_modules/' --exclude='web/ui/dist/' \
  voice-service/ user@GPU_LAPTOP:~/voice-service/

# my_voice.wav is git-ignored upstream — copy it explicitly:
scp voice-service/my_voice.wav user@GPU_LAPTOP:~/voice-service/my_voice.wav
```

Never copy `omnivoice-env/` between machines (Mac ↔ NVIDIA torch builds
are incompatible and silently fall back to CPU).

## 2. Setup on the 8GB laptop (fresh venv — NVIDIA CUDA)

```bash
cd ~/voice-service

# Python 3.11, fresh CUDA venv
uv venv --python 3.11 omnivoice-env
uv pip install -r requirements.txt

# Config
cp .env.example .env
# edit .env:
#   GROQ_API_KEY=...            ← required for chat replies
#   VOICE_REF_AUDIO=my_voice.wav
#   VOICE_REF_TEXT=<EXACT transcript of my_voice.wav>
#   VOICE_HOST=0.0.0.0          ← LAN reachable (single endpoint)
#   VOICE_PORT=8000
#   VOICE_NUM_STEP=6            ← 8GB sweet spot (quality/speed dial)
#   VOICE_FIRST_STEP=4

# Optional: bundled tutor UI
cd web/ui && npm install && npm run build && cd ../..

# Run — this IS the one API endpoint
./start.sh
# or: ./omnivoice-env/bin/python -m server
```

Verify on the laptop:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Find the laptop's LAN IP (`ipconfig` / `hostname -I`) — say `192.168.1.50`.
Your **single API endpoint** is then:

```
http://192.168.1.50:8000
```

## 3. Point the frontend at it (one env var)

```bash
# notmybug/.env (frontend machine)
VITE_VOICE_API_URL=http://192.168.1.50:8000
```

All calls go through `src/services/voiceAgent.js`:

```js
import { voiceAgent } from './services/voiceAgent.js'

await voiceAgent.health()                    // GET  /health
await voiceAgent.ready()                     // GET  /ready
await voiceAgent.config()                    // GET  /api/config
await voiceAgent.chat([{ role:'user', content:'...' }])  // POST /api/chat
await voiceAgent.speak('नमस्ते!')             // POST /tts → playable audioUrl
await voiceAgent.describeScreen(b64, { force:true })     // POST /api/vision

// Realtime voice + OS window control (one socket):
const v = voiceAgent.connectVoice({
  onEvent: (m) => console.log(m.type, m),       // start|text|done|error
  onAudio: (buf) => playPcm(buf),               // binary WAV frames
  onOsAction: (actions) => applyToDesktop(actions), // {op,app,zone,...}
  onDiagram: (d) => drawOnWhiteboard(d),
})
v.ask('यह एरर क्यों आ रहा है?', { osSnapshot })
v.stop()  // barge-in
```

## 4. Endpoint contract (all under the one base URL)

| Method | Path         | Purpose |
|--------|--------------|---------|
| GET    | `/health`    | liveness `{ status, device }` |
| GET    | `/ready`     | `{ tts, asr, vision, provider }` readiness |
| GET    | `/api/config`| all tunables (UI defaults) |
| POST   | `/tts`       | `{ text, nfe_step?, speed? }` → `audio/wav` |
| POST   | `/api/chat`  | `{ messages, temperature?, provider? }` → `{ reply }` |
| POST   | `/api/vision`| `{ image(b64), hash?, force? }` → `{ description }` |
| WS     | `/ws/tts`    | realtime chat+TTS+diagram+`os_action` events |
| WS     | `/ws/asr`    | mic stream → transcripts (Chrome AEC echo-free) |

### OS actions (`os_action` over `/ws/tts`)

The tutor owns the desktop; the learner has no window controls. The server's
OS Director sidecar emits max 6 validated actions/turn:

```json
{ "type": "os_action", "actions": [
  { "op": "open_app", "app": "code" },
  { "op": "tile_app", "app": "code", "zone": "right" },
  { "op": "browser_navigate", "target": "https://..." },
  { "op": "code_create", "path": "index.html", "content": "..." },
  { "op": "note_add", "title": "...", "body": "..." }
]}
```

Ops: `open_app|focus_app|close_app|minimize_app|maximize_app|restore_app|`
`tile_app|float_app|tile_grid|browser_navigate|browser_back|browser_forward|`
`browser_new_tab|browser_reload|browser_close_tab|note_add|clear_board|`
`code_create|code_write|code_edit`. Apps: `whiteboard|browser|notes|code|help|tutor`.
Zones: `left|right|tl|tr|bl|br`. Toggle with `OS_DIRECTOR_EVENTS=0` in `.env`.

## 5. 8GB VRAM notes

- OmniVoice fp16 ≈ 1.3 GB — comfortable on 8 GB.
- `VOICE_NUM_STEP=6`, `VOICE_FIRST_STEP=4` is the realtime sweet spot; raise
  toward 16–32 only if latency allows.
- First run downloads OmniVoice weights + faster-whisper `large-v3-turbo`
  (~1.6 GB) from Hugging Face — allow time + disk.
- `VOICE_API_DEVICE` / `VOICE_API_DTYPE` auto-detect (cuda/fp16); leave unset.
- If the frontend is on another machine, open port 8000 in the laptop firewall
  and use the LAN IP (not localhost) in `VITE_VOICE_API_URL`.
