import logging
import threading
import tkinter as tk

from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, RED, app_icon_path

log = logging.getLogger("voidstorm-companion")

PRESETS = {
    "Mythic+ (5-man)": {"key": "MYTHIC_PLUS_5", "maxSize": 5, "tanks": 1, "healers": 1, "dps": 3},
    "Raid Normal (10)": {"key": "RAID_NORMAL_10", "maxSize": 10, "tanks": 2, "healers": 2, "dps": 6},
    "Raid Heroic (20)": {"key": "RAID_HEROIC_20", "maxSize": 20, "tanks": 2, "healers": 4, "dps": 14},
    "Raid Mythic (20)": {"key": "RAID_MYTHIC_20", "maxSize": 20, "tanks": 2, "healers": 4, "dps": 14},
    "Custom": {"key": "CUSTOM", "maxSize": 5, "tanks": 1, "healers": 1, "dps": 3},
}

CONTENT_TYPE_MAP = {"Mythic+": "MYTHIC_PLUS", "Raid": "RAID"}
DIFFICULTY_MAP = {"Normal": "NORMAL", "Heroic": "HEROIC", "Mythic": "MYTHIC"}


def open_create_group(api_client, group_sync, characters: list[dict], parent: tk.Tk):
    win = tk.Toplevel(parent)
    win.title("Create Group")
    win.configure(bg=BG)
    win.resizable(False, False)

    w, h = 420, 520
    sx = (win.winfo_screenwidth() - w) // 2
    sy = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{sx}+{sy}")

    try:
        win.iconbitmap(app_icon_path())
    except tk.TclError:
        pass

    win.lift()
    win.focus_force()

    form = tk.Frame(win, bg=BG)
    form.pack(fill="both", expand=True, padx=24, pady=16)

    row = 0
    label_opts = {"font": ("Segoe UI", 10), "bg": BG, "fg": FG, "anchor": "w"}
    entry_opts = {"font": ("Segoe UI", 10), "bg": SURFACE, "fg": FG, "insertbackground": FG, "relief": "flat"}
    spin_opts = {"font": ("Segoe UI", 10), "bg": SURFACE, "fg": FG, "insertbackground": FG,
                 "relief": "flat", "buttonbackground": BTN_BG}

    title_var = tk.StringVar()
    tk.Label(form, text="Title:", **label_opts).grid(row=row, column=0, sticky="w", pady=(0, 6))
    title_entry = tk.Entry(form, textvariable=title_var, width=30, **entry_opts)
    title_entry.grid(row=row, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
    row += 1

    content_type_var = tk.StringVar(value="Mythic+")
    tk.Label(form, text="Content Type:", **label_opts).grid(row=row, column=0, sticky="w", pady=(0, 6))
    content_type_menu = tk.OptionMenu(win, content_type_var, "Mythic+", "Raid")
    content_type_menu.configure(bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                                font=("Segoe UI", 10), relief="flat", highlightthickness=0)
    content_type_menu["menu"].configure(bg=BTN_BG, fg=FG, activebackground=ACCENT, activeforeground=BG,
                                        font=("Segoe UI", 10))
    content_type_menu.grid(in_=form, row=row, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
    row += 1

    dungeon_var = tk.StringVar()
    tk.Label(form, text="Dungeon/Raid:", **label_opts).grid(row=row, column=0, sticky="w", pady=(0, 6))
    dungeon_entry = tk.Entry(form, textvariable=dungeon_var, width=30, **entry_opts)
    dungeon_entry.grid(row=row, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
    row += 1

    key_level_var = tk.StringVar(value="10")
    key_level_label = tk.Label(form, text="Key Level:", **label_opts)
    key_level_label.grid(row=row, column=0, sticky="w", pady=(0, 6))
    key_level_spin = tk.Spinbox(form, textvariable=key_level_var, from_=2, to=40, width=5, **spin_opts)
    key_level_spin.grid(row=row, column=1, sticky="w", pady=(0, 6), padx=(8, 0))
    key_row = row
    row += 1

    difficulty_var = tk.StringVar(value="Normal")
    difficulty_label = tk.Label(form, text="Difficulty:", **label_opts)
    difficulty_label.grid(row=row, column=0, sticky="w", pady=(0, 6))
    difficulty_menu = tk.OptionMenu(win, difficulty_var, "Normal", "Heroic", "Mythic")
    difficulty_menu.configure(bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                              font=("Segoe UI", 10), relief="flat", highlightthickness=0)
    difficulty_menu["menu"].configure(bg=BTN_BG, fg=FG, activebackground=ACCENT, activeforeground=BG,
                                      font=("Segoe UI", 10))
    difficulty_menu.grid(in_=form, row=row, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
    diff_row = row
    row += 1

    preset_var = tk.StringVar(value="Mythic+ (5-man)")
    tk.Label(form, text="Preset:", **label_opts).grid(row=row, column=0, sticky="w", pady=(0, 6))
    preset_menu = tk.OptionMenu(win, preset_var, *PRESETS.keys())
    preset_menu.configure(bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                          font=("Segoe UI", 10), relief="flat", highlightthickness=0)
    preset_menu["menu"].configure(bg=BTN_BG, fg=FG, activebackground=ACCENT, activeforeground=BG,
                                  font=("Segoe UI", 10))
    preset_menu.grid(in_=form, row=row, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
    row += 1

    tanks_var = tk.StringVar(value="1")
    healers_var = tk.StringVar(value="1")
    dps_var = tk.StringVar(value="3")

    tk.Label(form, text="Composition:", **label_opts).grid(row=row, column=0, sticky="w", pady=(0, 6))
    comp_frame = tk.Frame(form, bg=BG)
    comp_frame.grid(row=row, column=1, sticky="w", pady=(0, 6), padx=(8, 0))

    tk.Label(comp_frame, text="Tanks:", font=("Segoe UI", 9), bg=BG, fg=FG).pack(side="left")
    tk.Spinbox(comp_frame, textvariable=tanks_var, from_=0, to=6, width=3, **spin_opts).pack(side="left", padx=(2, 8))
    tk.Label(comp_frame, text="Healers:", font=("Segoe UI", 9), bg=BG, fg=FG).pack(side="left")
    tk.Spinbox(comp_frame, textvariable=healers_var, from_=0, to=8, width=3, **spin_opts).pack(side="left", padx=(2, 8))
    tk.Label(comp_frame, text="DPS:", font=("Segoe UI", 9), bg=BG, fg=FG).pack(side="left")
    tk.Spinbox(comp_frame, textvariable=dps_var, from_=0, to=26, width=3, **spin_opts).pack(side="left", padx=(2, 0))
    row += 1

    char_options = []
    char_display_map = {}
    if characters:
        for c in characters:
            display = f"{c.get('name', '?')}-{c.get('realm', '?')}"
            char_options.append(display)
            char_display_map[display] = c
    else:
        char_options.append("No characters found")

    char_var = tk.StringVar(value=char_options[0])
    tk.Label(form, text="Character:", **label_opts).grid(row=row, column=0, sticky="w", pady=(0, 6))
    char_menu = tk.OptionMenu(win, char_var, *char_options)
    char_menu.configure(bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                        font=("Segoe UI", 10), relief="flat", highlightthickness=0)
    char_menu["menu"].configure(bg=BTN_BG, fg=FG, activebackground=ACCENT, activeforeground=BG,
                                font=("Segoe UI", 10))
    char_menu.grid(in_=form, row=row, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
    row += 1

    error_var = tk.StringVar()
    error_label = tk.Label(form, textvariable=error_var, font=("Segoe UI", 9), bg=BG, fg=RED,
                           anchor="w", wraplength=370)
    error_label.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 4))
    row += 1

    form.columnconfigure(1, weight=1)

    difficulty_label.grid_remove()
    difficulty_menu.grid_remove()

    def _on_content_type_change(*_args):
        ct = content_type_var.get()
        if ct == "Mythic+":
            key_level_label.grid()
            key_level_spin.grid()
            difficulty_label.grid_remove()
            difficulty_menu.grid_remove()
            if preset_var.get() not in ("Mythic+ (5-man)", "Custom"):
                preset_var.set("Mythic+ (5-man)")
        else:
            key_level_label.grid_remove()
            key_level_spin.grid_remove()
            difficulty_label.grid()
            difficulty_menu.grid()
            if preset_var.get() == "Mythic+ (5-man)":
                preset_var.set("Raid Normal (10)")

    content_type_var.trace_add("write", _on_content_type_change)

    def _on_preset_change(*_args):
        preset_name = preset_var.get()
        if preset_name in PRESETS:
            p = PRESETS[preset_name]
            tanks_var.set(str(p["tanks"]))
            healers_var.set(str(p["healers"]))
            dps_var.set(str(p["dps"]))

    preset_var.trace_add("write", _on_preset_change)

    title_manually_edited = [False]

    def _on_title_edit(*_args):
        title_manually_edited[0] = True

    title_var.trace_add("write", _on_title_edit)

    def _on_dungeon_change(*_args):
        if title_manually_edited[0] and title_var.get().strip():
            return
        dungeon = dungeon_var.get().strip()
        if not dungeon:
            return
        title_manually_edited[0] = False
        ct = content_type_var.get()
        if ct == "Mythic+":
            kl = key_level_var.get().strip()
            title_var.set(f"{dungeon} +{kl}" if kl else dungeon)
        else:
            diff = difficulty_var.get()
            title_var.set(f"{dungeon} {diff}")
        title_manually_edited[0] = False

    dungeon_var.trace_add("write", _on_dungeon_change)
    key_level_var.trace_add("write", _on_dungeon_change)
    difficulty_var.trace_add("write", _on_dungeon_change)

    btn_frame = tk.Frame(win, bg=BG)
    btn_frame.pack(pady=(0, 16))

    create_btn = tk.Button(
        btn_frame, text="Create", width=10, pady=4,
        bg=ACCENT, fg="#1e1e2e", activebackground="#b4d0fb", activeforeground="#1e1e2e",
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    )
    create_btn.pack(side="left", padx=6)

    cancel_btn = tk.Button(
        btn_frame, text="Cancel", width=10, pady=4, command=win.destroy,
        bg=BTN_BG, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
        font=("Segoe UI", 10), relief="flat", cursor="hand2",
    )
    cancel_btn.pack(side="left", padx=6)

    def _on_create():
        error_var.set("")

        title = title_var.get().strip()
        if len(title) < 3 or len(title) > 100:
            error_var.set("Title must be 3-100 characters.")
            return

        dungeon = dungeon_var.get().strip()
        if len(dungeon) < 2 or len(dungeon) > 100:
            error_var.set("Dungeon/Raid must be 2-100 characters.")
            return

        char_selection = char_var.get()
        if char_selection == "No characters found" or char_selection not in char_display_map:
            error_var.set("Please select a character.")
            return

        char = char_display_map[char_selection]
        leader_name = char.get("name", "")
        leader_realm = char.get("realm", "")

        if len(leader_name) < 2 or len(leader_name) > 24:
            error_var.set("Invalid character name.")
            return
        if len(leader_realm) < 2 or len(leader_realm) > 50:
            error_var.set("Invalid realm name.")
            return

        ct_display = content_type_var.get()
        content_type = CONTENT_TYPE_MAP.get(ct_display, "MYTHIC_PLUS")

        preset_name = preset_var.get()
        preset_data = PRESETS.get(preset_name, PRESETS["Custom"])

        try:
            tanks = int(tanks_var.get())
            healers = int(healers_var.get())
            dps = int(dps_var.get())
        except ValueError:
            error_var.set("Tanks, Healers, and DPS must be numbers.")
            return

        payload = {
            "title": title,
            "contentType": content_type,
            "dungeonOrRaid": dungeon,
            "leaderCharName": leader_name,
            "leaderRealm": leader_realm,
            "preset": preset_data["key"],
            "maxSize": tanks + healers + dps,
            "requiredTanks": tanks,
            "requiredHealers": healers,
            "requiredDps": dps,
        }

        if content_type == "MYTHIC_PLUS":
            try:
                kl = int(key_level_var.get())
                if kl < 2 or kl > 40:
                    error_var.set("Key level must be between 2 and 40.")
                    return
                payload["keystoneLevel"] = kl
            except ValueError:
                error_var.set("Key level must be a number.")
                return
        else:
            diff_display = difficulty_var.get()
            payload["difficulty"] = DIFFICULTY_MAP.get(diff_display, "NORMAL")

        create_btn.configure(state="disabled")

        def _do_create():
            try:
                api_client.create_group(payload)
                try:
                    group_sync.force_refresh()
                except Exception:
                    pass
                try:
                    win.after(0, win.destroy)
                except tk.TclError:
                    pass
            except Exception as e:
                log.error("Failed to create group: %s", e)
                try:
                    win.after(0, lambda: error_var.set(str(e)))
                    win.after(0, lambda: create_btn.configure(state="normal"))
                except tk.TclError:
                    pass

        threading.Thread(target=_do_create, daemon=True).start()

    create_btn.configure(command=_on_create)
    win.protocol("WM_DELETE_WINDOW", win.destroy)
