# Deploy Molt Voice Service on Modal

This deploys the existing FastAPI application on a Modal T4 GPU. It exposes
the same REST and WebSocket routes used by `src/services/voiceAgent.js` in the
`notmybug` frontend. Modal starts the GPU container on demand and scales it
down after two idle minutes. The first request after scale-down can take
longer while the container and voice model start; Hugging Face model files
are kept in a Modal Volume between starts.

## One-time setup

1. Push this `molt-voice-service` repository, then clone or pull its updated
   default branch on the machine you use to manage Modal.
2. In the service checkout, install the Modal CLI and sign in:

   ```bash
   python -m pip install modal
   modal setup
   ```

3. Create a Modal Secret named `molt-voice-secrets` containing at least
   `GROQ_API_KEY`. Add `DEEPSEEK_API_KEY` or `VISION_API_KEY` if you use those
   providers. Use the Modal dashboard's **Secrets** page, or the CLI:

   ```bash
   modal secret create molt-voice-secrets GROQ_API_KEY=YOUR_GROQ_API_KEY
   ```

4. Upload the private reference clip used for voice cloning. The clip is
   stored in a Modal Volume, not committed to Git:

   ```bash
   modal volume create molt-voice-data
   modal volume put molt-voice-data /path/to/my_voice.wav /my_voice.wav
   ```

   The remote file must be `/my_voice.wav`. Set `VOICE_REF_TEXT` in the Modal
   Secret if the clip's transcript differs from the default in `.env.example`.

## Deploy and get the API URL

From the `molt-voice-service` checkout:

```bash
modal deploy modal_app.py
```

The deploy output includes the public `https://…modal.run` URL. Check
`https://…modal.run/health` and `/ready`; the first request may wait for the
GPU container and TTS model to load. The API includes:

| Route | Purpose |
|---|---|
| `GET /health`, `GET /ready` | Liveness and model/provider readiness |
| `GET /api/config` | Voice service configuration for the UI |
| `POST /tts`, `POST /api/chat`, `POST /api/vision` | TTS, text chat, and screen descriptions |
| `WS /ws/tts`, `WS /ws/asr` | Realtime voice turns and streaming microphone transcription |

## Connect the frontend

In the `notmybug` repo, set the exact URL printed by `modal deploy` as
`VITE_VOICE_API_URL` in the frontend environment. For local development, put
it in the repo's `.env` and restart Vite:

```env
VITE_VOICE_API_URL=https://YOUR-MODAL-URL.modal.run
```

For Vercel, add the same variable under **Project → Settings → Environment
Variables**, then redeploy the frontend. Vite embeds this value at build time.
The existing client derives its WebSocket URLs from the same setting, using
`wss://` for the Modal endpoint, so no second URL is needed.

## Updating after a push

After pushing a change to the voice-service repo, pull it in the Modal deploy
checkout and rerun `modal deploy modal_app.py`. Modal updates the running
deployment from that checkout. If the frontend repo tracks this service as a
Git submodule, update its recorded submodule revision too, then push the
frontend repo. Deploy the frontend again only when its code or its
`VITE_VOICE_API_URL` value changes.

The Modal endpoint is publicly reachable. Keep provider keys in the Modal
Secret and keep the reference audio in the private Modal Volume; neither
belongs in Git or a `VITE_*` variable.
