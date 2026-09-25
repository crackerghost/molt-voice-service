"""Allow ``python -m server`` to boot the API (same as the ``voice-api`` script)."""

from server.cli import main

if __name__ == "__main__":
    main()
