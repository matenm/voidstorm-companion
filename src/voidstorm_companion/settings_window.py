import os
import tkinter as tk

from voidstorm_companion.config import Config, get_autostart, set_autostart, detect_savedvariables


def _account_name(path: str) -> str:
    parts = os.path.normpath(path).split(os.sep)
    try:
        idx = parts.index("Account")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return path


BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
BTN_BG = "#313244"
BTN_HOVER = "#45475a"
SURFACE = "#181825"


def open_settings(config: Config, parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion — Settings")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 400, 400
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    def on_cancel():
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_cancel)

    try:
        win.iconbitmap(default="")
    except tk.TclError:
        pass

    header = tk.Label(win, text="Settings", font=("Segoe UI", 14, "bold"), bg=BG, fg=FG)
    header.pack(pady=(16, 12))

    autostart_var = tk.BooleanVar(value=get_autostart())
    minimized_var = tk.BooleanVar(value=config.start_minimized)

    cb_frame = tk.Frame(win, bg=BG)
    cb_frame.pack(fill="x", padx=24)

    tk.Checkbutton(
        cb_frame, text="Start with Windows", variable=autostart_var,
        bg=BG, fg=FG, selectcolor="#313244", activebackground=BG, activeforeground=FG,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=2)

    tk.Checkbutton(
        cb_frame, text="Start minimized", variable=minimized_var,
        bg=BG, fg=FG, selectcolor="#313244", activebackground=BG, activeforeground=FG,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=2)

    acct_label = tk.Label(
        win, text="WoW Accounts", font=("Segoe UI", 11, "bold"), bg=BG, fg=FG,
    )
    acct_label.pack(pady=(12, 4))

    acct_frame = tk.Frame(win, bg=BG)
    acct_frame.pack(fill="both", expand=True, padx=24)

    paths = list(config.savedvariables_paths)

    acct_listbox = tk.Listbox(
        acct_frame, bg=SURFACE, fg=FG, selectbackground=ACCENT, selectforeground=BG,
        font=("Segoe UI", 10), relief="flat", highlightthickness=0,
    )
    acct_listbox.pack(fill="both", expand=True, pady=(0, 6))

    for p in paths:
        acct_listbox.insert(tk.END, _account_name(p))

    acct_btn_frame = tk.Frame(acct_frame, bg=BG)
    acct_btn_frame.pack(fill="x")

    def on_detect():
        found = detect_savedvariables()
        for p in found:
            if p not in paths:
                paths.append(p)
                acct_listbox.insert(tk.END, _account_name(p))

    def on_remove():
        sel = acct_listbox.curselection()
        if sel:
            paths.pop(sel[0])
            acct_listbox.delete(sel[0])

    tk.Button(
        acct_btn_frame, text="Detect Accounts", command=on_detect, width=14,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 9), relief="flat", cursor="hand2",
    ).pack(side="left", padx=(0, 6))

    tk.Button(
        acct_btn_frame, text="Remove", command=on_remove, width=10,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 9), relief="flat", cursor="hand2",
    ).pack(side="left")

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(12, 12))

    def on_save():
        config.start_with_windows = autostart_var.get()
        config.start_minimized = minimized_var.get()
        config.savedvariables_paths = list(paths)
        config.save()
        set_autostart(config.start_with_windows, config.start_minimized)
        win.destroy()

    tk.Button(
        btn_frame, text="Save", command=on_save, width=10,
        bg=ACCENT, fg="#1e1e2e", activebackground="#b4d0fb", activeforeground="#1e1e2e",
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)

    tk.Button(
        btn_frame, text="Cancel", command=on_cancel, width=10,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)
