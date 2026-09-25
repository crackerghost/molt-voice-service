"""Non-streaming chat route registration."""


def register(app, *, chat):
    app.post("/api/chat")(chat)
