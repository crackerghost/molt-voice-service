"""System API route registration."""


def register(app, *, health, ready, api_config):
    app.get("/health")(health)
    app.get("/ready")(ready)
    app.get("/api/config")(api_config)
