import json
import os
import threading
from datetime import datetime, timezone

MAX_ENTRIES = 50


class UploadHistory:
    def __init__(self, history_path: str):
        self.history_path = history_path
        self.entries: list[dict] = []
        self.lifetime_imported: int = 0
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.entries = data
                    self.lifetime_imported = sum(e.get("imported", 0) for e in data)
                else:
                    self.entries = data.get("entries", [])
                    self.lifetime_imported = data.get("lifetime_imported", 0)
            except (json.JSONDecodeError, OSError):
                self.entries = []
                self.lifetime_imported = 0

    def _save(self):
        import tempfile
        dir_ = os.path.dirname(self.history_path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "lifetime_imported": self.lifetime_imported,
                    "entries": self.entries,
                }, f, indent=2)
            os.replace(tmp_path, self.history_path)
        except BaseException:
            os.unlink(tmp_path)
            raise

    def record(self, imported: int, skipped: int, error: str | None = None):
        with self._lock:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "imported": imported,
                "skipped": skipped,
            }
            if error:
                entry["error"] = error
            else:
                self.lifetime_imported += imported
            self.entries.append(entry)
            if len(self.entries) > MAX_ENTRIES:
                self.entries = self.entries[-MAX_ENTRIES:]
            self._save()

    def total_imported(self) -> int:
        return self.lifetime_imported

    def last_upload_time(self) -> str | None:
        for entry in reversed(self.entries):
            if not entry.get("error"):
                return entry["timestamp"]
        return None
