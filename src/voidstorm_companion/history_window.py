import tkinter as tk
from datetime import datetime, timezone

from voidstorm_companion.upload_history import UploadHistory

BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
BTN_BG = "#313244"
BTN_HOVER = "#45475a"
GREEN = "#a6e3a1"
RED = "#f38ba8"
SURFACE = "#181825"


def _format_time(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone()
    return dt.strftime("%m/%d %H:%M")


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
        win.iconbitmap(default="")
    except tk.TclError:
        pass

    header = tk.Label(win, text="Upload History", font=("Segoe UI", 14, "bold"), bg=BG, fg=FG)
    header.pack(pady=(16, 4))

    total = history.total_imported()
    last = history.last_upload_time()
    last_str = _format_time(last) if last else "Never"
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
        for entry in entries:
            ts = _format_time(entry["timestamp"])
            error = entry.get("error")
            if error:
                text = f"{ts}  ERROR: {error}"
                color = RED
            else:
                imported = entry.get("imported", 0)
                skipped = entry.get("skipped", 0)
                text = f"{ts}  +{imported} imported, {skipped} skipped"
                color = GREEN
            tk.Label(
                inner, text=text, font=("Consolas", 9), bg=SURFACE, fg=color, anchor="w",
            ).pack(fill="x", padx=8, pady=1)

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(0, 12))

    tk.Button(
        btn_frame, text="Close", command=on_close, width=10,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack()
