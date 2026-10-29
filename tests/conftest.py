"""Isolate tests from real data and services: temp data dir, mock Gmail. Must run before any server import."""

import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="openpoke-test-")
os.environ["OPENPOKE_DATA_DIR"] = _DATA
os.environ["OPENPOKE_MOCK_GMAIL"] = "1"
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
