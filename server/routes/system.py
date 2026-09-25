"""System and static UI route registration."""

from fastapi.staticfiles import StaticFiles


def register(app, *, health, ready, api_config, web_dir, serve_ui=True):
    app.get("/health")(health)
    app.get("/ready")(ready)
    app.get("/api/config")(api_config)
    # API-only GPU deploy: VOICE_SERVE_UI=0 skips the bundled Bug OS panel —
    # notmybug ships its own Molt UI and talks only over HTTP/WS.
    if serve_ui and web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
