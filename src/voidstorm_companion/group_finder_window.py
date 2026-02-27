import logging
import threading
import tkinter as tk
from tkinter import ttk

from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, GREEN, RED, app_icon_path

log = logging.getLogger("voidstorm-companion")

ROLE_COLORS = {"TANK": "#33aaff", "HEALER": "#33ee55", "DPS": "#ff5555"}
STATUS_COLORS = {"OPEN": GREEN, "LOCKED": "#7f849c", "STARTED": "#00c2ff", "FULL": "#ffaa11"}
ROLE_LABELS = {"TANK": "T", "HEALER": "H", "DPS": "D"}


def _content_info(group):
    ct = group.get("contentType", "")
    dungeon = group.get("dungeonOrRaid", "")
    difficulty = group.get("difficulty")
    ks = group.get("keystoneLevel")
    if ct == "MYTHIC_PLUS":
        parts = ["Mythic+"]
        if dungeon:
            parts.append(dungeon)
        return " \u00b7 ".join(parts)
    parts = ["Raid"]
    if difficulty:
        parts.append(difficulty.capitalize())
    if dungeon:
        parts.append(dungeon)
    return " \u00b7 ".join(parts)


def _group_title(group):
    ct = group.get("contentType", "")
    title = group.get("title", "")
    ks = group.get("keystoneLevel")
    dungeon = group.get("dungeonOrRaid", "")
    if ct == "MYTHIC_PLUS" and ks:
        return f"+{ks} {dungeon}" if dungeon else f"+{ks} {title}"
    return title or dungeon or "Group"


def _threaded_action(action_fn, parent, btn, *args):
    btn.configure(state="disabled")

    def work():
        try:
            action_fn(*args)
        except Exception as e:
            log.error("Action failed: %s", e)
        finally:
            try:
                parent.after(0, lambda: btn.configure(state="normal"))
            except tk.TclError:
                pass

    threading.Thread(target=work, daemon=True).start()


def open_group_finder(group_sync, api_client, parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Voidstorm Companion \u2014 Group Finder")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 620, 700
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    try:
        win.iconbitmap(app_icon_path())
    except tk.TclError:
        pass

    win.lift()
    win.focus_force()

    characters = []

    def _fetch_chars():
        nonlocal characters
        try:
            characters[:] = api_client.get_characters()
        except Exception:
            pass

    threading.Thread(target=_fetch_chars, daemon=True).start()

    header_frame = tk.Frame(win, bg=BG)
    header_frame.pack(fill="x", padx=16, pady=(12, 8))

    def _on_create():
        try:
            from voidstorm_companion.create_group_dialog import open_create_group
            open_create_group(api_client, group_sync, characters, parent)
        except Exception as e:
            log.error("Failed to open create group dialog: %s", e)

    create_btn = tk.Button(
        header_frame, text="+ Create Group", command=_on_create,
        bg=ACCENT, fg="#1e1e2e", activebackground="#b4d0fb", activeforeground="#1e1e2e",
        font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2", padx=12, pady=4,
    )
    create_btn.pack(side="left")

    def _on_refresh():
        group_sync.force_refresh()

    refresh_btn = tk.Button(
        header_frame, text="Refresh", command=_on_refresh,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2", padx=12, pady=4,
    )
    refresh_btn.pack(side="right")

    list_frame = tk.Frame(win, bg=BG)
    list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))

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

    status_bar = tk.Frame(win, bg=SURFACE, height=30)
    status_bar.pack(fill="x", side="bottom", padx=16, pady=(0, 12))
    status_bar.pack_propagate(False)

    status_dot = tk.Label(status_bar, text="\u25cf", font=("Segoe UI", 10), bg=SURFACE, fg="#7f849c")
    status_dot.pack(side="left", padx=(8, 4))

    status_label = tk.Label(
        status_bar, text="Connecting...", font=("Segoe UI", 9), bg=SURFACE, fg=FG, anchor="w",
    )
    status_label.pack(side="left", fill="x", expand=True)

    def _build_role_row(card, group):
        role_frame = tk.Frame(card, bg=SURFACE)
        role_frame.pack(fill="x", padx=12, pady=(0, 4))

        slots = [
            ("TANK", group.get("acceptedTanks", 0), group.get("requiredTanks", 0)),
            ("HEALER", group.get("acceptedHealers", 0), group.get("requiredHealers", 0)),
            ("DPS", group.get("acceptedDps", 0), group.get("requiredDps", 0)),
        ]

        for i, (role, filled, required) in enumerate(slots):
            color = ROLE_COLORS.get(role, FG)
            label_text = f"{ROLE_LABELS[role]} {filled}/{required}"
            lbl = tk.Label(
                role_frame, text=label_text, font=("Segoe UI", 9, "bold"),
                bg=SURFACE, fg=color,
            )
            lbl.pack(side="left", padx=(0, 16) if i < 2 else (0, 0))

        signups_total = group.get("totalSignups", 0)
        if signups_total > 0:
            tk.Label(
                role_frame, text=f"({signups_total} signup{'s' if signups_total != 1 else ''})",
                font=("Segoe UI", 8), bg=SURFACE, fg="#6c7086",
            ).pack(side="right")

    def _build_signup_list(card, group_id, signups):
        signup_header = tk.Label(
            card, text="Signups:", font=("Segoe UI", 9, "bold"),
            bg=SURFACE, fg=ACCENT, anchor="w",
        )
        signup_header.pack(fill="x", padx=12, pady=(2, 0))

        for signup in signups:
            row = tk.Frame(card, bg=SURFACE)
            row.pack(fill="x", padx=16, pady=1)

            char_name = signup.get("characterName", "?")
            realm = signup.get("realm", "")
            role = signup.get("role", "?")
            status = signup.get("status", "?")
            spec = signup.get("spec", "")
            ilvl = signup.get("ilvl", 0)
            role_color = ROLE_COLORS.get(role, FG)

            name_text = f"{char_name}-{realm}" if realm else char_name
            detail_parts = [role]
            if spec:
                detail_parts.append(spec)
            if ilvl:
                detail_parts.append(f"{ilvl} ilvl")

            tk.Label(
                row, text=name_text, font=("Segoe UI", 9),
                bg=SURFACE, fg=FG, anchor="w",
            ).pack(side="left")

            tk.Label(
                row, text=f"  {' \u00b7 '.join(detail_parts)}",
                font=("Segoe UI", 8), bg=SURFACE, fg=role_color, anchor="w",
            ).pack(side="left")

            status_color = GREEN if status == "ACCEPTED" else "#ffaa11" if status == "PENDING" else FG
            tk.Label(
                row, text=f"  {status.capitalize()}",
                font=("Segoe UI", 8, "bold"), bg=SURFACE, fg=status_color,
            ).pack(side="left", padx=(4, 0))

            if status == "PENDING":
                signup_id = signup.get("id", "")

                accept_btn = tk.Button(
                    row, text="\u2713", width=2,
                    bg="#2a4030", fg=GREEN, activebackground="#3a5a40", activeforeground=GREEN,
                    font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                )
                accept_btn.pack(side="right", padx=(2, 0))

                decline_btn = tk.Button(
                    row, text="\u2717", width=2,
                    bg="#402a2a", fg=RED, activebackground="#5a3a3a", activeforeground=RED,
                    font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                )
                decline_btn.pack(side="right", padx=(4, 0))

                def _make_accept(gid, sid, b):
                    def handler():
                        _threaded_action(api_client.accept_signup, parent, b, gid, sid)
                        win.after(500, group_sync.force_refresh)
                    return handler

                def _make_decline(gid, sid, b):
                    def handler():
                        _threaded_action(api_client.decline_signup, parent, b, gid, sid)
                        win.after(500, group_sync.force_refresh)
                    return handler

                accept_btn.configure(command=_make_accept(group_id, signup_id, accept_btn))
                decline_btn.configure(command=_make_decline(group_id, signup_id, decline_btn))

    def _build_card(group, my_signups, my_group_signups):
        group_id = group.get("id", "")
        status = group.get("status", "OPEN")
        leader_name = group.get("leaderCharName", "?")
        leader_realm = group.get("leaderRealm", "")

        my_signup = my_signups.get(group_id)
        is_signed_up = my_signup is not None
        is_leader = group_id in my_group_signups

        card = tk.Frame(inner, bg=SURFACE, padx=0, pady=0)
        card.pack(fill="x", padx=4, pady=(0, 6))

        row1 = tk.Frame(card, bg=SURFACE)
        row1.pack(fill="x", padx=12, pady=(10, 2))

        title_prefix = "My Group: " if is_leader else ""
        title_text = title_prefix + _group_title(group)
        tk.Label(
            row1, text=title_text, font=("Segoe UI", 11, "bold"),
            bg=SURFACE, fg=FG, anchor="w",
        ).pack(side="left", fill="x", expand=True)

        status_color = STATUS_COLORS.get(status, FG)
        tk.Label(
            row1, text=status, font=("Segoe UI", 9, "bold"),
            bg=SURFACE, fg=status_color,
        ).pack(side="right")

        row2 = tk.Frame(card, bg=SURFACE)
        row2.pack(fill="x", padx=12, pady=(0, 4))

        content = _content_info(group)
        leader_display = "You" if is_leader else f"{leader_name}-{leader_realm}" if leader_realm else leader_name
        tk.Label(
            row2, text=f"{content} \u00b7 Leader: {leader_display}",
            font=("Segoe UI", 9), bg=SURFACE, fg="#a6adc8", anchor="w",
        ).pack(side="left")

        _build_role_row(card, group)

        if is_leader:
            signups = my_group_signups.get(group_id, [])
            if signups:
                _build_signup_list(card, group_id, signups)

        if is_signed_up and my_signup:
            signup_role = my_signup.get("role", "?")
            signup_status = my_signup.get("status", "?")
            info_frame = tk.Frame(card, bg=SURFACE)
            info_frame.pack(fill="x", padx=12, pady=(2, 0))
            role_color = ROLE_COLORS.get(signup_role, FG)
            tk.Label(
                info_frame,
                text=f"Signed up as {signup_role} \u00b7 {signup_status.capitalize()}",
                font=("Segoe UI", 8, "bold"), bg=SURFACE, fg=role_color,
            ).pack(side="left")

        btn_row = tk.Frame(card, bg=SURFACE)
        btn_row.pack(fill="x", padx=12, pady=(4, 10))

        role_picker = tk.Frame(card, bg=SURFACE)

        if is_signed_up:
            withdraw_btn = tk.Button(
                btn_row, text="Withdraw", padx=10, pady=2,
                bg="#402a2a", fg=RED, activebackground="#5a3a3a", activeforeground=RED,
                font=("Segoe UI", 9), relief="flat", cursor="hand2",
            )

            def _withdraw(b=withdraw_btn, gid=group_id):
                _threaded_action(api_client.withdraw_group, parent, b, gid)
                win.after(500, group_sync.force_refresh)

            withdraw_btn.configure(command=_withdraw)
            withdraw_btn.pack(side="left", padx=(0, 6))
        elif status == "OPEN":
            signup_btn = tk.Button(
                btn_row, text="Sign Up", padx=10, pady=2,
                bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                font=("Segoe UI", 9), relief="flat", cursor="hand2",
            )

            def _toggle_role_picker(picker=role_picker, b=signup_btn):
                if picker.winfo_ismapped():
                    picker.pack_forget()
                else:
                    picker.pack(fill="x", padx=12, pady=(0, 8), after=btn_row)
                    _populate_role_picker(picker, group_id)

            signup_btn.configure(command=_toggle_role_picker)
            signup_btn.pack(side="left", padx=(0, 6))
        elif status == "FULL":
            full_btn = tk.Button(
                btn_row, text="Sign Up", padx=10, pady=2,
                bg=BTN_BG, fg="#6c7086",
                font=("Segoe UI", 9), relief="flat", state="disabled",
            )
            full_btn.pack(side="left", padx=(0, 6))

        if is_leader and status in ("OPEN", "LOCKED", "FULL"):
            if status == "OPEN":
                lock_btn = tk.Button(
                    btn_row, text="Lock", padx=10, pady=2,
                    bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                    font=("Segoe UI", 9), relief="flat", cursor="hand2",
                )

                def _lock(b=lock_btn, gid=group_id):
                    _threaded_action(api_client.lock_group, parent, b, gid)
                    win.after(500, group_sync.force_refresh)

                lock_btn.configure(command=_lock)
                lock_btn.pack(side="left", padx=(0, 6))

            start_btn = tk.Button(
                btn_row, text="Start", padx=10, pady=2,
                bg="#2a4030", fg=GREEN, activebackground="#3a5a40", activeforeground=GREEN,
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
            )

            def _start(b=start_btn, gid=group_id):
                _threaded_action(api_client.start_group, parent, b, gid)
                win.after(500, group_sync.force_refresh)

            start_btn.configure(command=_start)
            start_btn.pack(side="left", padx=(0, 6))

            cancel_btn = tk.Button(
                btn_row, text="Cancel", padx=10, pady=2,
                bg="#402a2a", fg=RED, activebackground="#5a3a3a", activeforeground=RED,
                font=("Segoe UI", 9), relief="flat", cursor="hand2",
            )

            def _cancel(b=cancel_btn, gid=group_id):
                _threaded_action(api_client.cancel_group, parent, b, gid)
                win.after(500, group_sync.force_refresh)

            cancel_btn.configure(command=_cancel)
            cancel_btn.pack(side="left", padx=(0, 6))

    def _populate_role_picker(picker, group_id):
        for child in picker.winfo_children():
            child.destroy()

        char_display_map = {}
        all_char_options = []
        if characters:
            for c in characters:
                display = f"{c.get('name', '?')}-{c.get('realm', '?')}"
                all_char_options.append(display)
                char_display_map[display] = c

        style = ttk.Style(picker)
        style.configure("CharPicker.TCombobox", fieldbackground=SURFACE, background=BTN_BG,
                         foreground=FG, arrowcolor=FG)
        char_var = tk.StringVar(value=all_char_options[0] if all_char_options else "")
        char_combo = ttk.Combobox(
            picker, textvariable=char_var, values=all_char_options,
            font=("Segoe UI", 9), width=20, style="CharPicker.TCombobox",
        )
        char_combo.pack(side="left", padx=(0, 8))

        def _filter_chars(*_args):
            typed = char_var.get().lower()
            if not typed:
                char_combo["values"] = all_char_options
            else:
                char_combo["values"] = [o for o in all_char_options if typed in o.lower()]

        char_combo.bind("<KeyRelease>", _filter_chars)

        for role, color in [("TANK", ROLE_COLORS["TANK"]), ("HEALER", ROLE_COLORS["HEALER"]), ("DPS", ROLE_COLORS["DPS"])]:
            role_btn = tk.Button(
                picker, text=role.capitalize(), padx=8, pady=2,
                bg=BTN_BG, fg=color, activebackground=BTN_HOVER, activeforeground=color,
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
            )

            def _do_signup(r=role, b=role_btn, gid=group_id):
                selected = char_var.get()
                char = char_display_map.get(selected)
                if not char:
                    log.warning("No character selected for signup")
                    return
                payload = {
                    "characterName": char.get("name", ""),
                    "realm": char.get("realm", ""),
                    "characterClass": char.get("class", char.get("characterClass", "")),
                    "spec": char.get("spec", ""),
                    "role": r,
                    "ilvl": char.get("ilvl", 0),
                    "source": "WEBSITE",
                }
                _threaded_action(api_client.signup_group, parent, b, gid, payload)
                picker.pack_forget()
                win.after(500, group_sync.force_refresh)

            role_btn.configure(command=_do_signup)
            role_btn.pack(side="left", padx=(0, 4))

    def _refresh(state):
        for child in inner.winfo_children():
            child.destroy()

        groups = state.get("groups", [])
        my_signups = state.get("mySignups", {})
        my_group_signups = state.get("myGroupSignups", {})
        online = state.get("online", False)

        if online:
            status_dot.configure(fg=GREEN)
            status_label.configure(text=f"Connected \u00b7 {len(groups)} group{'s' if len(groups) != 1 else ''}")
        else:
            status_dot.configure(fg=RED)
            status_label.configure(text="Disconnected")

        if not groups:
            tk.Label(
                inner, text="No groups available",
                font=("Segoe UI", 11), bg=BG, fg="#6c7086",
            ).pack(pady=40)
        else:
            leader_groups = []
            other_groups = []
            for g in groups:
                gid = g.get("id", "")
                if gid in my_group_signups:
                    leader_groups.append(g)
                else:
                    other_groups.append(g)

            for g in leader_groups + other_groups:
                _build_card(g, my_signups, my_group_signups)

    def _on_state_update(state):
        try:
            parent.after(0, lambda s=state: _refresh(s))
        except tk.TclError:
            pass

    group_sync.add_state_callback(_on_state_update)

    initial_state = group_sync.get_state()
    _refresh(initial_state)

    def on_close():
        group_sync.remove_state_callback(_on_state_update)
        canvas.unbind_all("<MouseWheel>")
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)
