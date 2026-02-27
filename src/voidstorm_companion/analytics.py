import os
import threading
import uuid

import requests

from voidstorm_companion.config import CONFIG_DIR

UMAMI_URL = "https://analytics.voidstorm.cc"
WEBSITE_ID = "pending-website-id"
SESSION_ID_PATH = os.path.join(CONFIG_DIR, "analytics_id")

_enabled = False
_session_id = ""


def _load_or_create_session_id() -> str:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(SESSION_ID_PATH):
        try:
            with open(SESSION_ID_PATH, "r") as f:
                sid = f.read().strip()
                if sid:
                    return sid
        except OSError:
            pass
    sid = str(uuid.uuid4())
    try:
        with open(SESSION_ID_PATH, "w") as f:
            f.write(sid)
    except OSError:
        pass
    return sid


def init(enabled: bool):
    global _enabled, _session_id
    _enabled = enabled
    if _enabled:
        _session_id = _load_or_create_session_id()


def track(event_name: str, data: dict | None = None):
    if not _enabled:
        return

    from voidstorm_companion.updater import CURRENT_VERSION

    payload = {
        "type": "event",
        "payload": {
            "website": WEBSITE_ID,
            "hostname": "companion-app",
            "url": "/app",
            "name": event_name,
            "data": {"version": CURRENT_VERSION, **(data or {})},
            "id": _session_id,
        },
    }

    def _send():
        try:
            requests.post(
                f"{UMAMI_URL}/api/send",
                json=payload,
                headers={"User-Agent": f"VoidstormCompanion/{CURRENT_VERSION}"},
                timeout=5,
            )
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()
