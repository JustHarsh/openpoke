"""Single source of truth for on-disk state; override with OPENPOKE_DATA_DIR (used by experiments)."""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("OPENPOKE_DATA_DIR") or Path(__file__).resolve().parent / "data")
