import json
import os


class DiffEngine:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self.uploaded_ids: set[str] = set()
        self._load()

    def _load(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, "r") as f:
                data = json.load(f)
                self.uploaded_ids = set(data.get("uploaded_ids", []))

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({"uploaded_ids": sorted(self.uploaded_ids)}, f)

    def filter_new(self, sessions: list[dict]) -> list[dict]:
        return [s for s in sessions if s.get("id") not in self.uploaded_ids]

    def mark_uploaded(self, session_ids: list[str]):
        self.uploaded_ids.update(session_ids)
        self._save()
