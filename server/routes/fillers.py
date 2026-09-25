"""Filler-audio route registration (latency maskers)."""

from fastapi.responses import Response


def register(app, *, fillers, threshold_ms: int, enabled: bool, mode: str = "slow"):
    @app.get("/api/fillers")
    def _list():
        return {
            "enabled": enabled and len(fillers) > 0,
            "threshold_ms": threshold_ms,
            "mode": mode,
            "count": len(fillers),
            "clips": fillers.listing(),
        }

    @app.get("/api/filler/random")
    def _random():
        clip = fillers.pick_random()
        if clip is None:
            return {"enabled": False, "reason": "no fillers generated yet — run scripts/generate_fillers.py"}
        return Response(
            content=clip["bytes"],
            media_type="audio/wav",
            headers={
                "Content-Disposition": f'inline; filename="{clip["name"]}.wav"',
                "X-Filler-Name": clip["name"],
                "Cache-Control": "public, max-age=86400",
            },
        )

    @app.get("/api/filler/file/{name}")
    def _file(name: str):
        clip = fillers.get(name)
        if clip is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"unknown filler {name!r}")
        return Response(
            content=clip["bytes"],
            media_type="audio/wav",
            headers={
                "Content-Disposition": f'inline; filename="{clip["name"]}.wav"',
                "Cache-Control": "public, max-age=86400",
            },
        )
