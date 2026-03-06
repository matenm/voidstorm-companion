import tkinter as tk
from datetime import datetime, timezone

from voidstorm_companion.lua_parser import parse_lua_table
from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, GREEN, RED, app_icon_path

from voidstorm_companion.constants import MODE_NAMES

YELLOW = "#f9e2af"


def _format_gold(amount) -> str:
    amount = int(amount)
    if amount < 0:
        return f"-{abs(amount):,}g"
    return f"{amount:,}g"


def _format_time(ts) -> str:
    try:
        ts = int(ts)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%m/%d %H:%M")
    except (ValueError, OSError, TypeError):
        return "unknown"


def _load_ledger(sv_paths: list[str]) -> list[dict]:
    all_ledger = []
    for sv_path in sv_paths:
        try:
            with open(sv_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            data = parse_lua_table(content, "VoidstormGambaDB")
            ledger = data.get("ledger", [])
            if isinstance(ledger, dict):
                ledger = [ledger[k] for k in sorted(ledger.keys(), key=str)]
            for entry in ledger:
                if isinstance(entry, dict) and "debtor" in entry:
                    all_ledger.append(entry)
        except (FileNotFoundError, Exception):
            pass
    seen_ids = set()
    deduped = []
    for entry in all_ledger:
        eid = entry.get("id")
        if eid is not None and eid in seen_ids:
            continue
        if eid is not None:
            seen_ids.add(eid)
        deduped.append(entry)
    return deduped


def _save_ledger_paid(sv_paths: list[str], entry_id, paid: bool):
    """Mark a ledger entry as paid/unpaid in SavedVariables."""
    import time
    for sv_path in sv_paths:
        try:
            with open(sv_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            id_pattern = f'["id"] = {entry_id}'
            if id_pattern not in content:
                continue
            paid_str = "true" if paid else "false"
            lines = content.split("\n")
            new_lines = []
            in_target_entry = False
            for line in lines:
                if id_pattern in line:
                    in_target_entry = True
                if in_target_entry and '["paid"]' in line:
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(f'{indent}["paid"] = {paid_str},')
                    in_target_entry = False
                    # Also add/update paidAt
                    continue
                if in_target_entry and '["paidAt"]' in line:
                    if paid:
                        indent = line[:len(line) - len(line.lstrip())]
                        new_lines.append(f'{indent}["paidAt"] = {int(time.time())},')
                    continue
                new_lines.append(line)
            with open(sv_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
        except Exception:
            pass


def open_debt_manager(sv_paths: list[str], parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion — Debt Manager")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 580, 700
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

    header = tk.Label(win, text="Debt Manager", font=("Segoe UI", 14, "bold"), bg=BG, fg=FG)
    header.pack(pady=(16, 8))

    # Summary bar
    summary_frame = tk.Frame(win, bg=SURFACE, padx=16, pady=10)
    summary_frame.pack(fill="x", padx=16, pady=(0, 8))

    summary_left = tk.Frame(summary_frame, bg=SURFACE)
    summary_left.pack(side="left", fill="both", expand=True)

    summary_right = tk.Frame(summary_frame, bg=SURFACE)
    summary_right.pack(side="left", fill="both", expand=True)

    # Filter buttons
    filter_frame = tk.Frame(win, bg=BG)
    filter_frame.pack(fill="x", padx=16, pady=(0, 4))

    show_paid = tk.BooleanVar(value=False)

    def _build_list():
        for child in inner.winfo_children():
            child.destroy()

        ledger = _load_ledger(sv_paths)
        unpaid = [e for e in ledger if not e.get("paid")]
        paid = [e for e in ledger if e.get("paid")]

        # Update summary
        for child in summary_left.winfo_children():
            child.destroy()
        for child in summary_right.winfo_children():
            child.destroy()

        # Aggregate owed-to-you and you-owe
        owed_to = {}  # creditor -> total
        you_owe = {}  # debtor -> total
        for e in unpaid:
            creditor = e.get("creditor", "?")
            debtor = e.get("debtor", "?")
            amount = int(e.get("amount", 0))
            owed_to[creditor] = owed_to.get(creditor, 0) + amount
            you_owe[debtor] = you_owe.get(debtor, 0) + amount

        total_unpaid = sum(int(e.get("amount", 0)) for e in unpaid)
        total_paid = sum(int(e.get("amount", 0)) for e in paid)

        tk.Label(summary_left, text="Outstanding Debts", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w")
        tk.Label(summary_left, text=f"{len(unpaid)} debts ({_format_gold(total_unpaid)})",
                 font=("Segoe UI", 14, "bold"), bg=SURFACE, fg=RED if unpaid else FG).pack(anchor="w")

        tk.Label(summary_right, text="Settled", font=("Segoe UI", 8), bg=SURFACE, fg=ACCENT).pack(anchor="w")
        tk.Label(summary_right, text=f"{len(paid)} paid ({_format_gold(total_paid)})",
                 font=("Segoe UI", 14, "bold"), bg=SURFACE, fg=GREEN if paid else FG).pack(anchor="w")

        # Display entries
        entries = unpaid if not show_paid.get() else paid
        entries.sort(key=lambda e: e.get("createdAt", 0), reverse=True)

        if not entries:
            msg = "No outstanding debts" if not show_paid.get() else "No settled debts"
            tk.Label(inner, text=msg, font=("Segoe UI", 11), bg=BG, fg="#6c7086").pack(pady=40)
            return

        for i, entry in enumerate(entries):
            row_bg = SURFACE if i % 2 == 0 else BG
            card = tk.Frame(inner, bg=row_bg)
            card.pack(fill="x", padx=4, pady=1)

            debtor = entry.get("debtor", "?")
            creditor = entry.get("creditor", "?")
            amount = int(entry.get("amount", 0))
            mode = MODE_NAMES.get(entry.get("mode", ""), entry.get("mode", "?"))
            created = _format_time(entry.get("createdAt"))
            is_paid = entry.get("paid", False)

            # Main row
            top_row = tk.Frame(card, bg=row_bg)
            top_row.pack(fill="x", padx=8, pady=(4, 0))

            tk.Label(
                top_row, text=f"{debtor} owes {creditor}",
                font=("Segoe UI", 10, "bold"), bg=row_bg, fg=FG, anchor="w",
            ).pack(side="left")

            amount_color = RED if not is_paid else GREEN
            tk.Label(
                top_row, text=_format_gold(amount),
                font=("Segoe UI", 10, "bold"), bg=row_bg, fg=amount_color,
            ).pack(side="right")

            # Detail row
            detail_row = tk.Frame(card, bg=row_bg)
            detail_row.pack(fill="x", padx=8, pady=(0, 4))

            tk.Label(
                detail_row, text=f"{mode} · {created}",
                font=("Segoe UI", 8), bg=row_bg, fg="#6c7086", anchor="w",
            ).pack(side="left")

            if is_paid:
                paid_at = _format_time(entry.get("paidAt"))
                tk.Label(
                    detail_row, text=f"Paid {paid_at}",
                    font=("Segoe UI", 8, "bold"), bg=row_bg, fg=GREEN,
                ).pack(side="right")
            else:
                entry_id = entry.get("id")
                if entry_id is not None:
                    mark_btn = tk.Button(
                        detail_row, text="Mark Paid", padx=8, pady=1,
                        bg="#2a4030", fg=GREEN, activebackground="#3a5a40", activeforeground=GREEN,
                        font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                    )

                    def _mark_paid(eid=entry_id, b=mark_btn):
                        _save_ledger_paid(sv_paths, eid, True)
                        b.configure(state="disabled", text="Saved")
                        win.after(500, _build_list)

                    mark_btn.configure(command=_mark_paid)
                    mark_btn.pack(side="right")

    # Filter toggle buttons
    def _show_unpaid():
        show_paid.set(False)
        unpaid_btn.configure(bg=ACCENT, fg="#1e1e2e")
        paid_btn.configure(bg=BTN_BG, fg=FG)
        _build_list()

    def _show_paid():
        show_paid.set(True)
        paid_btn.configure(bg=ACCENT, fg="#1e1e2e")
        unpaid_btn.configure(bg=BTN_BG, fg=FG)
        _build_list()

    unpaid_btn = tk.Button(
        filter_frame, text="Outstanding", command=_show_unpaid, padx=12, pady=2,
        bg=ACCENT, fg="#1e1e2e", activebackground="#b4d0fb", activeforeground="#1e1e2e",
        font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
    )
    unpaid_btn.pack(side="left", padx=(0, 6))

    paid_btn = tk.Button(
        filter_frame, text="Settled", command=_show_paid, padx=12, pady=2,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 9), relief="flat", cursor="hand2",
    )
    paid_btn.pack(side="left")

    refresh_btn = tk.Button(
        filter_frame, text="Refresh", command=_build_list, padx=12, pady=2,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 9), relief="flat", cursor="hand2",
    )
    refresh_btn.pack(side="right")

    # Scrollable list
    list_frame = tk.Frame(win, bg=BG)
    list_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

    canvas = tk.Canvas(list_frame, bg=BG, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=BG)

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

    # Close button
    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(0, 12))

    tk.Button(
        btn_frame, text="Close", command=on_close, width=10, pady=4,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    ).pack()

    _build_list()
