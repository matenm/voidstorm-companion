import json
import os
import threading

MAX_SEEN_IDS = 2000
MAX_WAGER = 1_000_000


class StatsStore:
    def __init__(self, stats_path: str):
        self.stats_path = stats_path
        self.total_sessions: int = 0
        self.total_gold_wagered: int = 0
        self.modes: dict[str, int] = {}
        self.players: dict[str, int] = {}
        self.gold_won: dict[str, int] = {}
        self.gold_lost: dict[str, int] = {}
        self._seen_ids: dict[str, None] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.stats_path):
            try:
                with open(self.stats_path, "r") as f:
                    data = json.load(f)
                self.total_sessions = data.get("total_sessions", 0)
                self.total_gold_wagered = data.get("total_gold_wagered", 0)
                self.modes = data.get("modes", {})
                self.players = data.get("players", {})
                self.gold_won = data.get("gold_won", {})
                self.gold_lost = data.get("gold_lost", {})
                self._seen_ids = dict.fromkeys(data.get("session_ids_seen", []))
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        import tempfile
        dir_ = os.path.dirname(self.stats_path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "total_sessions": self.total_sessions,
                    "total_gold_wagered": self.total_gold_wagered,
                    "modes": self.modes,
                    "players": self.players,
                    "gold_won": self.gold_won,
                    "gold_lost": self.gold_lost,
                    "session_ids_seen": list(self._seen_ids.keys())[-MAX_SEEN_IDS:],
                }, f, indent=2)
            os.replace(tmp_path, self.stats_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def update(self, sessions: list[dict]):
        with self._lock:
            for s in sessions:
                sid = s.get("id")
                if not sid or sid in self._seen_ids:
                    continue
                self._seen_ids[sid] = None
                self.total_sessions += 1
                wager = int(s.get("wager", 0))
                if wager > MAX_WAGER:
                    wager = MAX_WAGER
                self.total_gold_wagered += wager
                mode = s.get("mode", "UNKNOWN")
                self.modes[mode] = self.modes.get(mode, 0) + 1
                for r in s.get("rounds", []):
                    for p in r.get("players", []):
                        name = p.get("name")
                        if name:
                            self.players[name] = self.players.get(name, 0) + 1
                    results = r.get("results", {})
                    winner = results.get("winner")
                    loser = results.get("loser")
                    amount = min(int(results.get("amount", 0)), MAX_WAGER)
                    if winner and amount:
                        self.gold_won[winner] = self.gold_won.get(winner, 0) + amount
                    if loser and amount:
                        self.gold_lost[loser] = self.gold_lost.get(loser, 0) + amount
            if self._seen_ids:
                if len(self._seen_ids) > MAX_SEEN_IDS:
                    keys = list(self._seen_ids.keys())
                    self._seen_ids = dict.fromkeys(keys[-MAX_SEEN_IDS:])
                self._save()
