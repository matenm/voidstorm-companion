import os
import tkinter as tk
from tkinter import filedialog

from voidstorm_companion.config import Config, get_autostart, set_autostart, detect_savedvariables
from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, app_icon_path

WARNING = "\u26a0 "


def _account_name(path: str) -> str:
    parts = os.path.normpath(path).split(os.sep)
    try:
        idx = parts.index("Account")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return path


def _display_name(p: str) -> str:
    name = _account_name(p)
    if not os.path.exists(p):
        return WARNING + name
    return name


def open_settings(config: Config, parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion — Settings")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 400, 690
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    def on_cancel():
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_cancel)

    try:
        win.iconbitmap(app_icon_path())
    except tk.TclError:
        pass

    win.lift()
    win.focus_force()

    header = tk.Label(win, text="Settings", font=("Segoe UI", 14, "bold"), bg=BG, fg=FG)
    header.pack(pady=(16, 12))

    autostart_var = tk.BooleanVar(value=get_autostart())
    minimized_var = tk.BooleanVar(value=config.start_minimized)
    auto_upload_var = tk.BooleanVar(value=config.auto_upload)
    analytics_var = tk.BooleanVar(value=config.analytics)

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

    tk.Checkbutton(
        cb_frame, text="Auto-upload on file change", variable=auto_upload_var,
        bg=BG, fg=FG, selectcolor="#313244", activebackground=BG, activeforeground=FG,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=2)

    tk.Checkbutton(
        cb_frame, text="Anonymous usage analytics", variable=analytics_var,
        bg=BG, fg=FG, selectcolor="#313244", activebackground=BG, activeforeground=FG,
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=2)

    acct_label = tk.Label(
        win, text="WoW Accounts", font=("Segoe UI", 11, "bold"), bg=BG, fg=FG,
    )
    acct_label.pack(pady=(12, 2), anchor="w", padx=24)

    acct_frame = tk.Frame(win, bg=BG)
    acct_frame.pack(fill="x", padx=24)

    acct_hint = tk.Label(
        acct_frame,
        text="Use Detect to find accounts automatically, or Browse to select a VoidstormGamba.lua file from your WTF folder.",
        font=("Segoe UI", 8), bg=BG, fg="#6c7086", justify="left", wraplength=352, anchor="w",
    )
    acct_hint.pack(fill="x", pady=(0, 6))

    paths = list(config.savedvariables_paths)

    acct_listbox = tk.Listbox(
        acct_frame, bg=SURFACE, fg=FG, selectbackground=ACCENT, selectforeground=BG,
        font=("Segoe UI", 10), relief="flat", highlightthickness=0, height=6,
    )
    acct_listbox.pack(fill="x", pady=(0, 6))

    for p in paths:
        acct_listbox.insert(tk.END, _display_name(p))

    acct_btn_frame = tk.Frame(acct_frame, bg=BG)
    acct_btn_frame.pack(fill="x")

    feedback_label = tk.Label(acct_frame, text="", font=("Segoe UI", 8), bg=BG, fg=ACCENT, anchor="w")

    def _refresh_list():
        acct_listbox.delete(0, tk.END)
        for p in paths:
            acct_listbox.insert(tk.END, _display_name(p))

    def on_detect():
        found = detect_savedvariables()
        existing_accounts = {os.path.dirname(os.path.dirname(p)) for p in paths}
        new_count = 0
        for p in found:
            account_dir = os.path.dirname(os.path.dirname(p))
            if account_dir not in existing_accounts:
                paths.append(p)
                existing_accounts.add(account_dir)
                new_count += 1
        _refresh_list()
        if new_count:
            feedback_label.config(text=f"Found {new_count} new")
        else:
            feedback_label.config(text="No new accounts")
        win.after(3000, lambda: feedback_label.config(text=""))

    def on_remove():
        sel = acct_listbox.curselection()
        if sel:
            paths.pop(sel[0])
            _refresh_list()

    def on_browse():
        filepath = filedialog.askopenfilename(
            parent=win,
            title="Select SavedVariables file",
            filetypes=[("Lua files", "*.lua"), ("All files", "*.*")],
        )
        if filepath and filepath not in paths:
            paths.append(filepath)
            _refresh_list()

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

    tk.Button(
        acct_btn_frame, text="Browse...", command=on_browse, width=8,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 9), relief="flat", cursor="hand2",
    ).pack(side="left", padx=(6, 0))

    feedback_label.pack(fill="x", pady=(4, 0))

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(12, 12))

    def on_save():
        config.start_with_windows = autostart_var.get()
        config.start_minimized = minimized_var.get()
        config.auto_upload = auto_upload_var.get()
        config.analytics = analytics_var.get()
        config.savedvariables_paths = list(paths)
        config.save()
        set_autostart(config.start_with_windows, config.start_minimized)
        win.destroy()

    tk.Button(
        btn_frame, text="Save", command=on_save, width=10, pady=4,
        bg=ACCENT, fg="#1e1e2e", activebackground="#b4d0fb", activeforeground="#1e1e2e",
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)

    tk.Button(
        btn_frame, text="Cancel", command=on_cancel, width=10, pady=4,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack(side="left", padx=6)
