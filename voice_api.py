"""Compatibility entrypoint for the modular Voice Cloning server.

New entrypoints (pick one):
  python -m server          # same as below
  voice-api                 # console script (pip install -e .)
  ./start.sh                # venv + server + open UI
"""

from server.app import app
from server.cli import main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
