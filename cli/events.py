#!/usr/bin/env python3
"""Top-level CLI shim. Forwards to events_ndjson.cli.main."""

import sys
from pathlib import Path

# Allow running this file directly out of the repo without installing the
# package: drop libraries/python on sys.path so the import works.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "libraries" / "python"))

from events_ndjson.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
