import tkinter as tk
import webbrowser
from datetime import datetime, timezone

from voidstorm_companion.upload_history import UploadHistory
from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, GREEN, RED, app_icon_path


def _relative_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (now - dt).total_seconds()
        if delta < 60:
            return "just now"
        if delta < 3600:
            return f"{int(delta // 60)} min ago"
        if delta < 86400:
            return f"{int(delta // 3600)} hr ago"
        return dt.astimezone().strftime("%m/%d %H:%M")
    except (ValueError, OSError):
        return iso[:16]


def open_history(history: UploadHistory, parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion — Upload History")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 480, 400
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    try:
        win.iconbitmap(app_icon_path())
    except tk.TclError:
        pass

    header = tk.Label(win, text="Upload History", font=("Segoe UI", 14, "bold"), bg=BG, fg=FG)
    header.pack(pady=(16, 4))

    total = history.total_imported()
    last = history.last_upload_time()
    last_str = _relative_time(last) if last else "Never"
    summary = tk.Label(
        win, text=f"Total uploaded: {total} sessions  |  Last: {last_str}",
        font=("Segoe UI", 9), bg=BG, fg=ACCENT,
    )
    summary.pack(pady=(0, 8))

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

    def on_close():
        canvas.unbind_all("<MouseWheel>")
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    entries = list(reversed(history.entries))
    if not entries:
        tk.Label(inner, text="No uploads yet", font=("Consolas", 10), bg=SURFACE, fg=FG).pack(pady=20)
    else:
        for i, entry in enumerate(entries):
            row_bg = SURFACE if i % 2 == 0 else BG
            ts = _relative_time(entry["timestamp"])
            error = entry.get("error")
            if error:
                err_short = error[:60] + "..." if len(error) > 60 else error
                text = f"{ts}  ERROR: {err_short}"
                color = RED
            else:
                imported = entry.get("imported", 0)
                skipped = entry.get("skipped", 0)
                text = f"{ts}  +{imported} imported, {skipped} skipped"
                color = GREEN
            tk.Label(
                inner, text=text, font=("Consolas", 9), bg=row_bg, fg=color, anchor="w",
            ).pack(fill="x", padx=8, pady=1)

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(0, 12))

    def _open_website():
        webbrowser.open("https://voidstorm.cc")

    tk.Button(
        btn_frame, text="View on Voidstorm.cc", command=_open_website, width=18,
        bg=BTN_BG, fg=ACCENT, activebackground=BTN_HOVER, activeforeground=ACCENT,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)

    tk.Button(
        btn_frame, text="Close", command=on_close, width=10,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)
