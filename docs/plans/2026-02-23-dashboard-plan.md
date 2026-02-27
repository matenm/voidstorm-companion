# Dashboard Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Dashboard window showing lifetime gambling stats (persisted) and recent session details (from SavedVariables).

**Architecture:** A new `StatsStore` accumulates counters from parsed sessions into `stats.json`. A new `dashboard_window.py` displays those stats plus live session data in a combined tkinter Toplevel window. Integrated into the tray menu and upload flow.

**Tech Stack:** Python, tkinter, JSON persistence, slpp (Lua parser)

---

### Task 1: StatsStore — data layer

**Files:**
- Create: `src/voidstorm_companion/stats_store.py`
- Create: `tests/test_stats_store.py`
- Modify: `src/voidstorm_companion/config.py:14` — add STATS_PATH

**Step 1: Add STATS_PATH to config.py**

In `src/voidstorm_companion/config.py`, after line 14 (`STATE_PATH = ...`), add:

```python
STATS_PATH = os.path.join(CONFIG_DIR, "stats.json")
```

**Step 2: Write failing tests**

Create `tests/test_stats_store.py`:

```python
import json
import os
import tempfile

from voidstorm_companion.stats_store import StatsStore


def test_new_store_has_empty_stats():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        assert store.total_sessions == 0
        assert store.total_gold_wagered == 0
        assert store.modes == {}
        assert store.players == {}


def test_update_accumulates_stats():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        sessions = [
            {
                "id": "sess-1",
                "mode": "DIFFERENCE",
                "wager": 50000,
                "rounds": [
                    {
                        "players": [
                            {"name": "Bp"},
                            {"name": "Skatten"},
                        ],
                        "results": {"winner": "Bp", "loser": "Skatten"},
                    }
                ],
            }
        ]
        store.update(sessions)
        assert store.total_sessions == 1
        assert store.total_gold_wagered == 50000
        assert store.modes == {"DIFFERENCE": 1}
        assert store.players["Bp"] == 1
        assert store.players["Skatten"] == 1


def test_update_skips_already_seen():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        sessions = [{"id": "sess-1", "mode": "DIFFERENCE", "wager": 10000, "rounds": [{"players": [{"name": "Bp"}], "results": {}}]}]
        store.update(sessions)
        store.update(sessions)
        assert store.total_sessions == 1


def test_persistence_across_loads():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "stats.json")
        store = StatsStore(path)
        sessions = [{"id": "sess-1", "mode": "DEATHROLL", "wager": 25000, "rounds": [{"players": [{"name": "Koiebar"}, {"name": "Bp"}], "results": {}}]}]
        store.update(sessions)

        store2 = StatsStore(path)
        assert store2.total_sessions == 1
        assert store2.total_gold_wagered == 25000
        assert store2.modes == {"DEATHROLL": 1}
        assert store2.players["Koiebar"] == 1


def test_seen_ids_capped():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        for i in range(2100):
            store.update([{"id": f"sess-{i}", "mode": "DIFFERENCE", "wager": 100, "rounds": [{"players": [], "results": {}}]}])
        assert len(store._seen_ids) <= 2000
        assert store.total_sessions == 2100
```

**Step 3: Run tests to verify they fail**

Run: `./venv/Scripts/python.exe -m pytest tests/test_stats_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voidstorm_companion.stats_store'`

**Step 4: Implement StatsStore**

Create `src/voidstorm_companion/stats_store.py`:

```python
import json
import os
import threading

MAX_SEEN_IDS = 2000


class StatsStore:
    def __init__(self, stats_path: str):
        self.stats_path = stats_path
        self.total_sessions: int = 0
        self.total_gold_wagered: int = 0
        self.modes: dict[str, int] = {}
        self.players: dict[str, int] = {}
        self._seen_ids: set[str] = set()
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
                self._seen_ids = set(data.get("session_ids_seen", []))
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
                    "session_ids_seen": list(self._seen_ids)[-MAX_SEEN_IDS:],
                }, f, indent=2)
            os.replace(tmp_path, self.stats_path)
        except BaseException:
            os.unlink(tmp_path)
            raise

    def update(self, sessions: list[dict]):
        with self._lock:
            for s in sessions:
                sid = s.get("id")
                if not sid or sid in self._seen_ids:
                    continue
                self._seen_ids.add(sid)
                self.total_sessions += 1
                self.total_gold_wagered += int(s.get("wager", 0))
                mode = s.get("mode", "UNKNOWN")
                self.modes[mode] = self.modes.get(mode, 0) + 1
                for r in s.get("rounds", []):
                    for p in r.get("players", []):
                        name = p.get("name")
                        if name:
                            self.players[name] = self.players.get(name, 0) + 1
            if self._seen_ids:
                if len(self._seen_ids) > MAX_SEEN_IDS:
                    self._seen_ids = set(list(self._seen_ids)[-MAX_SEEN_IDS:])
                self._save()
```

**Step 5: Run tests to verify they pass**

Run: `./venv/Scripts/python.exe -m pytest tests/test_stats_store.py -v`
Expected: all 5 PASS

**Step 6: Run full test suite**

Run: `./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all PASS

---

### Task 2: Dashboard window

**Files:**
- Create: `src/voidstorm_companion/dashboard_window.py`

**Step 1: Create the dashboard window**

Create `src/voidstorm_companion/dashboard_window.py`:

```python
import tkinter as tk
import webbrowser
from datetime import datetime, timezone

from voidstorm_companion.lua_parser import parse_savedvariables
from voidstorm_companion.stats_store import StatsStore
from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, GREEN, RED, app_icon_path


def _relative_time(ts: int) -> str:
    try:
        delta = datetime.now(timezone.utc).timestamp() - ts
        if delta < 60:
            return "just now"
        if delta < 3600:
            return f"{int(delta // 60)} min ago"
        if delta < 86400:
            return f"{int(delta // 3600)} hr ago"
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%m/%d %H:%M")
    except (ValueError, OSError):
        return "unknown"


def _format_gold(amount: int) -> str:
    return f"{amount:,}g"


def open_dashboard(stats: StatsStore, sv_paths: list[str], parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion — Dashboard")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 520, 520
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    try:
        win.iconbitmap(app_icon_path())
    except tk.TclError:
        pass

    def on_close():
        canvas.unbind_all("<MouseWheel>")
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    header = tk.Label(win, text="Dashboard", font=("Segoe UI", 14, "bold"), bg=BG, fg=FG)
    header.pack(pady=(16, 8))

    stats_frame = tk.Frame(win, bg=SURFACE, padx=16, pady=12)
    stats_frame.pack(fill="x", padx=16, pady=(0, 8))

    left_col = tk.Frame(stats_frame, bg=SURFACE)
    left_col.pack(side="left", fill="both", expand=True)

    right_col = tk.Frame(stats_frame, bg=SURFACE)
    right_col.pack(side="left", fill="both", expand=True)

    tk.Label(left_col, text="Total Sessions", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w")
    tk.Label(left_col, text=str(stats.total_sessions), font=("Segoe UI", 16, "bold"), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(left_col, text="Gold Wagered", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w", pady=(8, 0))
    tk.Label(left_col, text=_format_gold(stats.total_gold_wagered), font=("Segoe UI", 16, "bold"), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(right_col, text="Modes", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w")
    if stats.modes:
        mode_lines = [f"{count} {mode.capitalize()}" for mode, count in sorted(stats.modes.items(), key=lambda x: -x[1])]
        tk.Label(right_col, text="\n".join(mode_lines), font=("Segoe UI", 10), bg=SURFACE, fg=FG, justify="left").pack(anchor="w")
    else:
        tk.Label(right_col, text="None yet", font=("Segoe UI", 10), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(right_col, text="Top Players", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w", pady=(8, 0))
    if stats.players:
        top = sorted(stats.players.items(), key=lambda x: -x[1])[:3]
        player_lines = [f"{name} ({count})" for name, count in top]
        tk.Label(right_col, text="\n".join(player_lines), font=("Segoe UI", 10), bg=SURFACE, fg=FG, justify="left").pack(anchor="w")
    else:
        tk.Label(right_col, text="None yet", font=("Segoe UI", 10), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(win, text="Recent Sessions", font=("Segoe UI", 11, "bold"), bg=BG, fg=FG).pack(anchor="w", padx=16, pady=(4, 4))

    list_frame = tk.Frame(win, bg=SURFACE)
    list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    canvas = tk.Canvas(list_frame, bg=SURFACE, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=SURFACE)

    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    all_sessions = []
    for sv_path in sv_paths:
        try:
            all_sessions.extend(parse_savedvariables(sv_path))
        except (FileNotFoundError, Exception):
            pass

    all_sessions.sort(key=lambda s: s.get("startedAt", 0), reverse=True)

    if not all_sessions:
        tk.Label(inner, text="No sessions on disk", font=("Consolas", 10), bg=SURFACE, fg=FG).pack(pady=20)
    else:
        for i, session in enumerate(all_sessions[:50]):
            row_bg = SURFACE if i % 2 == 0 else BG
            row = tk.Frame(inner, bg=row_bg)
            row.pack(fill="x", padx=4, pady=1)

            mode = session.get("mode", "?")
            wager = _format_gold(int(session.get("wager", 0)))
            ts = _relative_time(int(session.get("startedAt", 0)))
            channel = session.get("channel", "")

            summary = ""
            rounds = session.get("rounds", [])
            if rounds:
                last_round = rounds[-1] if isinstance(rounds, list) else list(rounds.values())[-1]
                results = last_round.get("results", {})
                summary = results.get("summary", "")

            tk.Label(
                row, text=f"{ts}  {mode} - {wager}", font=("Consolas", 9), bg=row_bg, fg=ACCENT, anchor="w",
            ).pack(fill="x", padx=8)

            if summary:
                tk.Label(
                    row, text=summary, font=("Consolas", 9), bg=row_bg, fg=GREEN, anchor="w",
                ).pack(fill="x", padx=8)

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(0, 12))

    tk.Button(
        btn_frame, text="Close", command=on_close, width=10, pady=4,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack()
```

**Step 2: Run full test suite to verify no import issues**

Run: `./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all PASS

---

### Task 3: Wire everything together

**Files:**
- Modify: `src/voidstorm_companion/window_manager.py` — add `open_dashboard`
- Modify: `src/voidstorm_companion/tray.py` — add Dashboard menu entry
- Modify: `src/voidstorm_companion/main.py` — create StatsStore, wire to upload flow and tray

**Step 1: Add `open_dashboard` to WindowManager**

In `src/voidstorm_companion/window_manager.py`, add after the `open_settings` method:

```python
    def open_dashboard(self, stats, sv_paths):
        from voidstorm_companion.dashboard_window import open_dashboard
        if self._root:
            self._root.after(0, lambda: open_dashboard(stats, sv_paths, self._root))
```

**Step 2: Add Dashboard entry to tray menu**

In `src/voidstorm_companion/tray.py`, add `on_dashboard=None` to `__init__` parameters (after `on_history`), store as `self.on_dashboard = on_dashboard`.

In `_build_menu`, add a Dashboard entry after Upload Now:

```python
            pystray.MenuItem(
                "Dashboard",
                lambda: self.on_dashboard() if self.on_dashboard else None,
            ),
```

**Step 3: Wire StatsStore into main.py**

In `src/voidstorm_companion/main.py`:

Add import at top:
```python
from voidstorm_companion.config import Config, STATE_PATH, HISTORY_PATH, STATS_PATH, set_autostart
from voidstorm_companion.stats_store import StatsStore
```

In `App.__init__`, add after `self.history = ...`:
```python
        self.stats = StatsStore(STATS_PATH)
```

In `_do_upload`, after `sessions = parse_savedvariables(sv_path)` (line 91) and before `new_sessions = ...` (line 92), add:
```python
                self.stats.update(sessions)
```

Add a new method:
```python
    def _do_dashboard(self):
        self.window_manager.open_dashboard(self.stats, list(self.config.savedvariables_paths))
```

In the `TrayApp(...)` constructor call, add:
```python
            on_dashboard=self._do_dashboard,
```

**Step 4: Run full test suite**

Run: `./venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all PASS

**Step 5: Manual smoke test**

Run: `./venv/Scripts/python.exe -c "from voidstorm_companion.main import main; main()"`

Verify:
- "Dashboard" appears in tray menu
- Clicking it opens a window with stats (all zeros if no data) and recent sessions
- Window has app icon, dark theme, Close button works
