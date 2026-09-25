"""CLI entrypoint: ``python -m server`` or the ``voice-api`` console script.

Reuses an existing server on the port when present (auto-kill opt-out via
``VOICE_KILL_EXISTING=0``), mirroring the old ``voice_api.py`` behaviour.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_existing(port: int) -> bool:
    """Kill whatever already listens on `port`. Returns True if port is free."""
    current = os.getpid()
    if shutil.which("lsof"):
        try:
            out = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p.strip() for p in out.stdout.split() if p.strip().isdigit()]
            pids = [p for p in pids if int(p) != current]
            if not pids:
                return not port_in_use(port)
            print(f"⚠️  Port {port} busy (PID {', '.join(pids)}) — stopping old server...")
            subprocess.run(["kill", *pids], timeout=5)
            for _ in range(20):
                if not port_in_use(port):
                    return True
                time.sleep(0.5)
            print(f"⚠️  PIDs still alive — force killing {', '.join(pids)}...")
            subprocess.run(["kill", "-9", *pids], timeout=5)
            time.sleep(1)
            return not port_in_use(port)
        except Exception as exc:  # noqa: BLE001 — fall through to error below
            print(f"⚠️  Could not kill port {port}: {exc}")
            return not port_in_use(port)
    print(f"❌ Port {port} is busy and 'lsof' is unavailable — free it manually.")
    return False


def main() -> None:
    import uvicorn

    from server.factory import create_app

    app = create_app()
    host = os.environ.get("VOICE_HOST", "127.0.0.1")
    port = int(os.environ.get("VOICE_PORT", "8000"))

    if port_in_use(port):
        if os.environ.get("VOICE_KILL_EXISTING", "1") != "1":
            raise SystemExit(f"❌ Port {port} already in use (set VOICE_KILL_EXISTING=1 to auto-restart).")
        if not kill_existing(port):
            raise SystemExit(f"❌ Port {port} still busy after kill attempt — free it and retry.")
        print(f"✅ Port {port} freed — starting fresh server...")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
