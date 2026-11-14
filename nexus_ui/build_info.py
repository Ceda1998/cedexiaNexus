"""Build identity shared by the desktop window and packaged smoke tests."""
import json
from pathlib import Path


def build_info():
    root = Path(__file__).resolve().parents[1]
    try:
        return json.loads((root / "config/build-info.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": (root / "installers/version.txt").read_text().strip(), "revision": "lokal"}
