# Run Molt Voice Service on Kaggle

The Kaggle notebook in this folder installs and starts the API on a Kaggle GPU,
then opens a temporary Cloudflare Quick Tunnel and prints its public URL.

## Setup

1. Import `molt_voice_service.ipynb` into Kaggle (Notebook → Import Notebook →
   GitHub, or upload the file).
2. In Notebook options, select a GPU accelerator and turn Internet on.
3. Add a Kaggle Dataset containing your clean 3–10 second voice clip. Keep the
   exact transcript of that clip; set both values in the notebook's
   **Configuration** cell.
4. Add a Kaggle Notebook secret named `GROQ_API_KEY` (or
   `DEEPSEEK_API_KEY`). The notebook reads it through Kaggle's secrets API and
   never writes it into the repo or notebook output.
5. Run all cells. The last startup cell prints the API URL and checks `/health`
   and `/ready`. Set `VITE_VOICE_API_URL` in the consuming frontend to the
   printed base URL.

## URL and session lifetime

The notebook uses a Cloudflare Quick Tunnel. Its random `trycloudflare.com`
URL is temporary, changes when the tunnel restarts, and stops working when the
Kaggle session ends. Keep the Kaggle session running while using the service.
Quick Tunnels are for testing and development, not a persistent production
deployment.

Anyone who gets the URL can call the API, including endpoints that use your
configured LLM key and GPU. Share it only with trusted testers, and stop the
notebook when finished. Do not put API keys in notebook code or share notebook
outputs containing the URL.

The first run installs Python dependencies and downloads the OmniVoice model
and ASR weights, so allow time and disk space. Kaggle's temporary filesystem
and GPU quota also apply.
