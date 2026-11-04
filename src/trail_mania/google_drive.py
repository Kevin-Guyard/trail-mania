"""Public OAuth configuration; credentials remain in the native Google SDK."""

import json
import os
from pathlib import Path


def get_google_client_id() -> str:
    """Read the public web client ID from the environment or packaged assets."""
    client_id = os.environ.get("TRAIL_MANIA_GOOGLE_WEB_CLIENT_ID", "").strip()
    if not client_id:
        assets_directory = os.environ.get("FLET_ASSETS_DIR")
        assets = (
            Path(assets_directory) if assets_directory
            else Path(__file__).resolve().parents[1] / "assets"
        )
        config = assets / "google_drive.json"
        try:
            settings = json.loads(config.read_text(encoding="utf-8"))
            client_id = settings.get("web_client_id", "")
        except (OSError, ValueError, AttributeError):
            return ""
    if not isinstance(client_id, str):
        return ""
    client_id = client_id.strip()
    return client_id if client_id.endswith(".apps.googleusercontent.com") else ""
