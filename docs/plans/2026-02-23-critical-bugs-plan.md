# Critical Bugs Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the four critical bugs: multiple tk.Tk() instances, tkinter on wrong threads, dead re-auth retry code, and Upload Now blocking the tray.

**Architecture:** Introduce a WindowManager class that owns a single hidden tk.Tk() root on a dedicated thread, with popup windows as Toplevel children. Fix re-auth to run synchronously within the upload thread. Wrap Upload Now in a daemon thread.

**Tech Stack:** Python 3.11+, tkinter, pystray, threading, queue

---

### Task 1: Create WindowManager

**Files:**
- Create: `src/voidstorm_companion/window_manager.py`
- Test: `tests/test_window_manager.py`

**Step 1: Write the test**

```python
import threading
import time
import pytest
from unittest.mock import patch, MagicMock


def test_window_manager_starts_and_stops():
    from voidstorm_companion.window_manager import WindowManager
    wm = WindowManager()
    wm.start()
    assert wm._root is not None
    assert wm._thread.is_alive()
    wm.stop()
    time.sleep(0.2)
    assert not wm._thread.is_alive()


def test_window_manager_schedules_on_tk_thread():
    from voidstorm_companion.window_manager import WindowManager
    wm = WindowManager()
    wm.start()
    called = threading.Event()

    def callback():
        called.set()

    wm._root.after(0, callback)
    assert called.wait(timeout=2)
    wm.stop()
```

**Step 2: Run test to verify it fails**

Run: `cd C:\Users\magnu\Documents\git\voidstorm-companion && python -m pytest tests/test_window_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voidstorm_companion.window_manager'`

**Step 3: Write the implementation**

```python
import threading
import tkinter as tk


class WindowManager:
    def __init__(self):
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._ready.set()
        self._root.mainloop()

    def open_history(self, history):
        from voidstorm_companion.history_window import open_history
        if self._root:
            self._root.after(0, lambda: open_history(history, self._root))

    def open_settings(self, config):
        from voidstorm_companion.settings_window import open_settings
        if self._root:
            self._root.after(0, lambda: open_settings(config, self._root))

    def stop(self):
        if self._root:
            self._root.after(0, self._root.quit)
```

**Step 4: Run test to verify it passes**

Run: `cd C:\Users\magnu\Documents\git\voidstorm-companion && python -m pytest tests/test_window_manager.py -v`
Expected: PASS (both tests)

**Step 5: Commit**

```
feat: add WindowManager for single-root tkinter threading
```

---

### Task 2: Convert history_window.py to use Toplevel

**Files:**
- Modify: `src/voidstorm_companion/history_window.py`

**Step 1: Modify `open_history` signature and internals**

Changes to `history_window.py`:
1. Add `parent` parameter to `open_history(history, parent)`
2. Replace `win = tk.Tk()` with `win = tk.Toplevel(parent)`
3. Remove `win.mainloop()` at the end
4. Add `win.protocol("WM_DELETE_WINDOW", on_close)`
5. Fix mousewheel: replace `canvas.bind_all` with scoped binding via `<Enter>`/`<Leave>`
6. Move the `on_close` function definition before the entries loop so it can be used by `WM_DELETE_WINDOW`

The full updated file:

```python
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
```

**Step 2: Verify app still launches**

Run: `cd C:\Users\magnu\Documents\git\voidstorm-companion && python -m pytest tests/ -v`
Expected: All existing tests pass (history_window has no tests, but nothing should break)

**Step 3: Commit**

```
fix: convert history_window to Toplevel with scoped mousewheel binding
```

---

### Task 3: Convert settings_window.py to use Toplevel

**Files:**
- Modify: `src/voidstorm_companion/settings_window.py`

**Step 1: Modify `open_settings` signature and internals**

Changes:
1. Add `parent` parameter to `open_settings(config, parent)`
2. Replace `win = tk.Tk()` with `win = tk.Toplevel(parent)`
3. Remove `win.mainloop()` at the end
4. Add `win.protocol("WM_DELETE_WINDOW", on_cancel)`

The full updated file:

```python
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

    def on_cancel():
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_cancel)

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
```

**Step 2: Run tests**

Run: `cd C:\Users\magnu\Documents\git\voidstorm-companion && python -m pytest tests/ -v`
Expected: All existing tests pass

**Step 3: Commit**

```
fix: convert settings_window to Toplevel with WM_DELETE_WINDOW handler
```

---

### Task 4: Integrate WindowManager into main.py and fix bugs 3-4

**Files:**
- Modify: `src/voidstorm_companion/main.py`
- Modify: `src/voidstorm_companion/tray.py`

**Step 1: Update main.py**

Changes:
1. Import `WindowManager`, create in `__init__`, start in `run()`
2. Replace `_do_settings`/`_do_history` — call `window_manager.open_*` directly (no more daemon threads)
3. **Bug 3 fix:** In `_do_upload`'s `AuthError` handler, call `self._login_worker()` directly instead of `self._do_login()`
4. **Bug 4 fix:** Add `_do_upload_async` wrapper that spawns a thread, pass it as `on_upload_now`

Updated `main.py`:

```python
import logging
import threading
from datetime import datetime, timezone

from voidstorm_companion.config import Config, STATE_PATH, HISTORY_PATH, set_autostart
from voidstorm_companion.lua_parser import parse_savedvariables
from voidstorm_companion.diff_engine import DiffEngine
from voidstorm_companion.upload_history import UploadHistory
from voidstorm_companion.api_client import ApiClient, AuthError
from voidstorm_companion.auth_flow import authenticate, get_stored_token, clear_token
from voidstorm_companion.file_watcher import SavedVariablesWatcher
from voidstorm_companion.tray import TrayApp
from voidstorm_companion.window_manager import WindowManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("voidstorm-companion")


class App:
    def __init__(self):
        self.config = Config()
        self.diff = DiffEngine(STATE_PATH)
        self.history = UploadHistory(HISTORY_PATH)
        self.watchers: dict[str, SavedVariablesWatcher] = {}
        self.tray: TrayApp | None = None
        self.client: ApiClient | None = None
        self.window_manager = WindowManager()

    def _ensure_auth(self) -> bool:
        token = get_stored_token()
        if token:
            self.client = ApiClient(self.config.api_url, token)
            return True
        return False

    def _do_login(self):
        threading.Thread(target=self._login_worker, daemon=True).start()

    def _login_worker(self):
        log.info("Starting Battle.net login flow...")
        if self.tray:
            self.tray.set_status("Logging in...")
        token = authenticate(self.config.api_url)
        if token:
            self.client = ApiClient(self.config.api_url, token)
            log.info("Login successful!")
            if self.tray:
                self.tray.set_status("Authenticated", logged_in=True)
        else:
            log.error("Login failed or timed out")
            if self.tray:
                self.tray.set_status("Login failed", logged_in=False)

    def _do_logout(self):
        log.info("Logging out...")
        self.client = None
        clear_token()
        if self.tray:
            self.tray.set_status("Logged out", logged_in=False)

    def _do_upload_async(self, path: str | None = None):
        threading.Thread(target=self._do_upload, args=(path,), daemon=True).start()

    def _do_upload(self, path: str | None = None, _is_retry: bool = False):
        paths = [path] if path else list(self.config.savedvariables_paths)
        if not paths:
            log.warning("No SavedVariables paths configured")
            return

        if not self.client:
            if not self._ensure_auth():
                log.warning("Not authenticated — skipping upload")
                return

        total_imported = 0
        total_skipped = 0

        for sv_path in paths:
            try:
                if self.tray:
                    self.tray.set_status("Parsing...")

                sessions = parse_savedvariables(sv_path)
                new_sessions = self.diff.filter_new(sessions)

                if not new_sessions:
                    log.info(f"No new sessions in {sv_path}")
                    continue

                log.info(f"Uploading {len(new_sessions)} new session(s) from {sv_path}...")
                if self.tray:
                    self.tray.set_status(f"Uploading {len(new_sessions)}...")

                result = self.client.upload(new_sessions)

                uploaded_ids = [s["id"] for s in new_sessions]
                self.diff.mark_uploaded(uploaded_ids)

                imported = result.get('imported', 0)
                skipped = result.get('skipped', 0)
                total_imported += imported
                total_skipped += skipped

                log.info(f"Upload complete: {imported} imported, {skipped} skipped")

            except AuthError:
                if _is_retry:
                    log.error("Re-authentication failed — please log in manually")
                    self.history.record(0, 0, error="Auth failed")
                    if self.tray:
                        self.tray.set_status("Auth failed", logged_in=False)
                    self._update_tray_tooltip()
                    return
                log.warning("Token expired — re-authenticating...")
                self.client = None
                clear_token()
                if self.tray:
                    self.tray.set_status("Re-authenticating...", logged_in=False)
                self._login_worker()
                if self.client:
                    self._do_upload(path=path, _is_retry=True)
                return
            except FileNotFoundError:
                log.error(f"SavedVariables not found: {sv_path}")
                self.history.record(0, 0, error=f"File not found: {sv_path}")
                if self.tray:
                    self.tray.set_status("File not found")
                self._update_tray_tooltip()
                return
            except Exception as e:
                log.error(f"Upload error: {e}")
                self.history.record(0, 0, error=str(e))
                if self.tray:
                    self.tray.set_status("Error")
                self._update_tray_tooltip()
                return

        if total_imported or total_skipped:
            self.history.record(total_imported, total_skipped)
        if self.tray:
            self.tray.set_status(f"Synced {total_imported}" if total_imported else "Up to date")
        self._update_tray_tooltip()

    def _on_file_change(self, filepath: str):
        log.info(f"File change detected: {filepath}")
        self._do_upload(path=filepath)

    def _do_settings(self):
        self.window_manager.open_settings(self.config)

    def _do_history(self):
        self.window_manager.open_history(self.history)

    def _apply_autostart(self):
        set_autostart(self.config.start_with_windows, self.config.start_minimized)

    def _update_tray_tooltip(self):
        if not self.tray:
            return
        total = self.history.total_imported()
        last = self.history.last_upload_time()
        if last:
            dt = datetime.fromisoformat(last).astimezone()
            last_str = dt.strftime("%m/%d %H:%M")
        else:
            last_str = None
        self.tray.set_tooltip(total, last_str)

    def _check_update(self):
        from voidstorm_companion.updater import check_for_update
        info = check_for_update()
        if info and self.tray:
            log.info(f"Update available: v{info['version']}")
            self.tray.set_update(info)

    def _on_quit(self):
        for watcher in self.watchers.values():
            watcher.stop()
        self.window_manager.stop()
        log.info("Shutting down")

    def run(self):
        log.info("Voidstorm Companion starting...")

        self.window_manager.start()

        if not self.config.savedvariables_paths:
            from voidstorm_companion.config import detect_savedvariables
            found = detect_savedvariables()
            if found:
                self.config.savedvariables_paths = found
                self.config.save()
                log.info(f"Auto-detected {len(found)} SavedVariables path(s)")
            else:
                log.warning("Could not auto-detect WoW SavedVariables path")

        self._ensure_auth()

        self._apply_autostart()

        for sv_path in self.config.savedvariables_paths:
            watcher = SavedVariablesWatcher(sv_path, self._on_file_change)
            watcher.start()
            self.watchers[sv_path] = watcher
            log.info(f"Watching: {sv_path}")

        self.tray = TrayApp(
            on_upload_now=self._do_upload_async,
            on_login=self._do_login,
            on_logout=self._do_logout,
            on_quit=self._on_quit,
            on_settings=self._do_settings,
            on_history=self._do_history,
        )

        if self.client and self.watchers:
            threading.Thread(target=self._do_upload, daemon=True).start()

        is_authed = self.client is not None
        if is_authed and self.watchers:
            self.tray.set_status("Watching", logged_in=True)
        elif is_authed:
            self.tray.set_status("No WoW path", logged_in=True)
        else:
            self.tray.set_status("Not logged in", logged_in=False)

        self._update_tray_tooltip()

        threading.Thread(target=self._check_update, daemon=True).start()

        self.tray.run()


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
```

**Step 2: Update tray.py — add `update_menu()` call in `set_status`**

Add `self.icon.update_menu()` at the end of `set_status()` so the status label refreshes when the menu is opened.

In `tray.py`, change `set_status`:

```python
def set_status(self, status: str, logged_in: bool | None = None):
    self.status = status
    if logged_in is not None:
        self.logged_in = logged_in
    if self.icon:
        self.icon.icon = _get_icon(self.logged_in)
        self.icon.update_menu()
```

**Step 3: Run all tests**

Run: `cd C:\Users\magnu\Documents\git\voidstorm-companion && python -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```
fix: integrate WindowManager, fix re-auth retry and Upload Now blocking
```

---

### Task 5: Manual smoke test

**Step 1: Run the app**

Run: `cd C:\Users\magnu\Documents\git\voidstorm-companion && python -m voidstorm_companion`

Verify:
- App starts, tray icon appears
- Right-click tray → "Upload History" opens the history window
- Close history window via X button (tests WM_DELETE_WINDOW)
- Open history again, close via Close button
- Open Settings, close via Cancel
- Open Settings, close via X button
- Open History AND Settings simultaneously (tests Toplevel sharing)
- Click "Upload Now" — tray remains responsive during upload
- Status text in tray menu updates correctly

**Step 2: Commit final state if any adjustments needed**

```
fix: smoke test adjustments for critical bug fixes
```
