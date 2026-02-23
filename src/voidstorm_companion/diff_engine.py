import json
import os


class DiffEngine:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self.uploaded_ids: set[str] = set()
        self._load()

    def _load(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r") as f:
                    data = json.load(f)
                    self.uploaded_ids = set(data.get("uploaded_ids", []))
            except (json.JSONDecodeError, OSError):
                self.uploaded_ids = set()

    def _save(self):
        import tempfile
        dir_ = os.path.dirname(self.state_path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"uploaded_ids": sorted(self.uploaded_ids)}, f)
            os.replace(tmp_path, self.state_path)
        except BaseException:
            os.unlink(tmp_path)
            raise

    def filter_new(self, sessions: list[dict]) -> list[dict]:
        return [s for s in sessions if s.get("id") not in self.uploaded_ids]

    def mark_uploaded(self, session_ids: list[str]):
        self.uploaded_ids.update(session_ids)
        self._save()
