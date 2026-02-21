import json
import os
from datetime import datetime, timezone

MAX_ENTRIES = 100


class UploadHistory:
    def __init__(self, history_path: str):
        self.history_path = history_path
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.history_path):
            with open(self.history_path, "r") as f:
                self.entries = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(self.history_path) or ".", exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump(self.entries, f, indent=2)

    def record(self, imported: int, skipped: int, error: str | None = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "imported": imported,
            "skipped": skipped,
        }
        if error:
            entry["error"] = error
        self.entries.append(entry)
        if len(self.entries) > MAX_ENTRIES:
            self.entries = self.entries[-MAX_ENTRIES:]
        self._save()

    def total_imported(self) -> int:
        return sum(e.get("imported", 0) for e in self.entries)

    def last_upload_time(self) -> str | None:
        for entry in reversed(self.entries):
            if not entry.get("error"):
                return entry["timestamp"]
        return None
