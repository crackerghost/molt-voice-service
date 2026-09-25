"""Screen vision route registration."""


def register(app, *, api_vision):
    app.post("/api/vision")(api_vision)
