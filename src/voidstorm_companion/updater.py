import logging

import requests

log = logging.getLogger("voidstorm-companion")

CURRENT_VERSION = "0.1.0"
RELEASES_URL = "https://api.github.com/repos/matenm/voidstorm-companion/releases/latest"


def _parse_version(tag: str) -> tuple[int, ...]:
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def check_for_update() -> dict | None:
    try:
        resp = requests.get(RELEASES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        if not tag:
            return None
        if _parse_version(tag) > _parse_version(CURRENT_VERSION):
            return {
                "version": tag.lstrip("v"),
                "url": data.get("html_url", ""),
            }
    except Exception:
        log.debug("Update check failed", exc_info=True)
    return None
