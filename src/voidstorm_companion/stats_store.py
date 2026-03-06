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
        self.wins: dict[str, int] = {}
        self.losses: dict[str, int] = {}
        self.streaks: dict[str, int] = {}
        self.best_streaks: dict[str, int] = {}
        self.worst_streaks: dict[str, int] = {}
        self.mode_wins: dict[str, dict[str, int]] = {}
        self.mode_losses: dict[str, dict[str, int]] = {}
        self.h2h: dict[str, dict[str, int]] = {}
        self.elo: int | None = None
        self.tier: str | None = None
        self.session_wins: int = 0
        self.session_losses: int = 0
        self.session_net_gold: int = 0
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
                self.wins = data.get("wins", {})
                self.losses = data.get("losses", {})
                self.streaks = data.get("streaks", {})
                self.best_streaks = data.get("best_streaks", {})
                self.worst_streaks = data.get("worst_streaks", {})
                self.mode_wins = data.get("mode_wins", {})
                self.mode_losses = data.get("mode_losses", {})
                self.h2h = data.get("h2h", {})
                self._seen_ids = dict.fromkeys(data.get("session_ids_seen", []))
                elo_val = data.get("elo")
                self.elo = int(elo_val) if elo_val is not None else None
                tier_val = data.get("tier")
                self.tier = str(tier_val) if tier_val is not None else None
                self.session_wins = data.get("session_wins", 0)
                self.session_losses = data.get("session_losses", 0)
                self.session_net_gold = data.get("session_net_gold", 0)
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
                    "wins": self.wins,
                    "losses": self.losses,
                    "streaks": self.streaks,
                    "best_streaks": self.best_streaks,
                    "worst_streaks": self.worst_streaks,
                    "mode_wins": self.mode_wins,
                    "mode_losses": self.mode_losses,
                    "h2h": self.h2h,
                    "elo": self.elo,
                    "tier": self.tier,
                    "session_wins": self.session_wins,
                    "session_losses": self.session_losses,
                    "session_net_gold": self.session_net_gold,
                    "session_ids_seen": list(self._seen_ids.keys())[-MAX_SEEN_IDS:],
                }, f, indent=2)
            os.replace(tmp_path, self.stats_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _update_streak(self, name: str, won: bool):
        cur = self.streaks.get(name, 0)
        if won:
            self.streaks[name] = max(cur, 0) + 1
        else:
            self.streaks[name] = min(cur, 0) - 1
        s = self.streaks[name]
        if s > 0:
            self.best_streaks[name] = max(self.best_streaks.get(name, 0), s)
        elif s < 0:
            self.worst_streaks[name] = min(self.worst_streaks.get(name, 0), s)

    def update(self, sessions: list[dict], local_player: str = ""):
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
                        if local_player and name == local_player:
                            payout = int(p.get("payout", 0))
                            bet = int(p.get("bet", 0))
                            if payout > 0:
                                self.session_net_gold += payout - bet
                            elif bet > 0:
                                self.session_net_gold -= bet
                    results = r.get("results", {})
                    winner = results.get("winner")
                    loser = results.get("loser")
                    amount = min(int(results.get("amount", 0)), MAX_WAGER)
                    if winner and amount:
                        self.gold_won[winner] = self.gold_won.get(winner, 0) + amount
                    if loser and amount:
                        self.gold_lost[loser] = self.gold_lost.get(loser, 0) + amount
                    if winner:
                        self.wins[winner] = self.wins.get(winner, 0) + 1
                        self._update_streak(winner, True)
                        if mode not in self.mode_wins:
                            self.mode_wins[mode] = {}
                        self.mode_wins[mode][winner] = self.mode_wins[mode].get(winner, 0) + 1
                        if local_player and winner == local_player:
                            self.session_wins += 1
                    if loser:
                        self.losses[loser] = self.losses.get(loser, 0) + 1
                        self._update_streak(loser, False)
                        if mode not in self.mode_losses:
                            self.mode_losses[mode] = {}
                        self.mode_losses[mode][loser] = self.mode_losses[mode].get(loser, 0) + 1
                        if local_player and loser == local_player:
                            self.session_losses += 1
                    if winner and loser:
                        key = f"{winner} vs {loser}"
                        self.h2h[key] = self.h2h.get(key, 0) + 1
            if self._seen_ids:
                if len(self._seen_ids) > MAX_SEEN_IDS:
                    keys = list(self._seen_ids.keys())
                    self._seen_ids = dict.fromkeys(keys[-MAX_SEEN_IDS:])
                self._save()

    def win_rate(self, name: str) -> float:
        w = self.wins.get(name, 0)
        l = self.losses.get(name, 0)
        total = w + l
        return (w / total * 100) if total > 0 else 0.0

    def top_rivalries(self, limit: int = 5) -> list[tuple[str, int]]:
        return sorted(self.h2h.items(), key=lambda x: -x[1])[:limit]

    def reset_session_counters(self):
        with self._lock:
            self.session_wins = 0
            self.session_losses = 0
            self.session_net_gold = 0
            self._save()
