import tkinter as tk
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
    if amount < 0:
        return f"-{abs(amount):,}g"
    return f"{amount:,}g"


def open_dashboard(stats: StatsStore, sv_paths: list[str], parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion — Dashboard")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 580, 860
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    try:
        win.iconbitmap(app_icon_path())
    except tk.TclError:
        pass

    win.lift()
    win.focus_force()

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

    all_players = set(stats.gold_won.keys()) | set(stats.gold_lost.keys())
    net = {p: stats.gold_won.get(p, 0) - stats.gold_lost.get(p, 0) for p in all_players}

    tk.Label(left_col, text="Biggest Winners", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w", pady=(8, 0))
    winners = sorted(((p, n) for p, n in net.items() if n > 0), key=lambda x: -x[1])[:3]
    if winners:
        winner_lines = [f"{name} (+{_format_gold(amount)})" for name, amount in winners]
        tk.Label(left_col, text="\n".join(winner_lines), font=("Segoe UI", 10), bg=SURFACE, fg=GREEN, justify="left").pack(anchor="w")
    else:
        tk.Label(left_col, text="None yet", font=("Segoe UI", 10), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(left_col, text="Biggest Losers", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w", pady=(8, 0))
    losers = sorted(((p, n) for p, n in net.items() if n < 0), key=lambda x: x[1])[:3]
    if losers:
        loser_lines = [f"{name} ({_format_gold(amount)})" for name, amount in losers]
        tk.Label(left_col, text="\n".join(loser_lines), font=("Segoe UI", 10), bg=SURFACE, fg=RED, justify="left").pack(anchor="w")
    else:
        tk.Label(left_col, text="None yet", font=("Segoe UI", 10), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(right_col, text="Modes", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w")
    if stats.modes:
        mode_lines = [f"{count} {mode.capitalize()}" for mode, count in sorted(stats.modes.items(), key=lambda x: -x[1])]
        tk.Label(right_col, text="\n".join(mode_lines), font=("Segoe UI", 10), bg=SURFACE, fg=FG, justify="left").pack(anchor="w")
    else:
        tk.Label(right_col, text="None yet", font=("Segoe UI", 10), bg=SURFACE, fg=FG).pack(anchor="w")

    tk.Label(right_col, text="Most Active", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w", pady=(8, 0))
    if stats.players:
        top = sorted(stats.players.items(), key=lambda x: -x[1])[:10]
        player_lines = [f"{name} ({count} rounds)" for name, count in top]
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
    canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

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
            wager = _format_gold(min(int(session.get("wager", 0)), 1_000_000))
            ts = _relative_time(int(session.get("startedAt", 0)))

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
