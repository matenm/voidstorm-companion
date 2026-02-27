# Critical Bugs Fix — Design

## Bugs Addressed

1. Multiple `tk.Tk()` instances (history + settings each create their own root)
2. Tkinter running on non-main daemon threads (undefined behavior on Windows)
3. Re-auth retry is dead code (`_do_login()` is async, `if self.client:` check runs before login completes)
4. "Upload Now" blocks the pystray event loop (synchronous HTTP upload on tray callback thread)

## Design

### WindowManager (Bugs 1 & 2)

New file: `src/voidstorm_companion/window_manager.py`

A `WindowManager` class that:
- Creates a single hidden `tk.Tk()` root on a dedicated daemon thread
- Runs `root.mainloop()` on that thread
- Exposes `open_history(history)` and `open_settings(config)` methods callable from any thread
- Uses `root.after(0, fn)` to schedule window creation on the tkinter thread (thread-safe)
- Opens windows as `tk.Toplevel(root)` instead of `tk.Tk()`

Changes to existing files:
- `history_window.py`: `open_history(history)` takes a `parent` parameter, creates `Toplevel(parent)` instead of `Tk()`, removes `mainloop()` call
- `settings_window.py`: same pattern — `open_settings(config, parent)` with `Toplevel(parent)`
- `main.py`: creates `WindowManager` in `App.__init__`, passes it as the callback source for history/settings. Removes the daemon thread spawning for `_do_history` and `_do_settings` (the WindowManager handles threading internally)

Additional fixes included:
- Add `WM_DELETE_WINDOW` protocol handler to both windows
- Fix `bind_all` mousewheel leak in history_window (use canvas-scoped binding)

### Synchronous Re-auth (Bug 3)

In `main.py` `_do_upload()`, the `AuthError` handler currently calls `self._do_login()` which spawns a thread and returns immediately. Change to call `self._login_worker()` directly — this is already on a background thread so blocking is fine. After `_login_worker()` returns, check `self.client` and retry.

### Upload Now Threading (Bug 4)

In `main.py`, change `on_upload_now` to pass a wrapper that spawns a daemon thread. Same pattern already used by `_do_login`.

## Files Modified

- `src/voidstorm_companion/window_manager.py` (new)
- `src/voidstorm_companion/history_window.py` (Toplevel, remove mainloop, fix mousewheel)
- `src/voidstorm_companion/settings_window.py` (Toplevel, remove mainloop, add WM_DELETE_WINDOW)
- `src/voidstorm_companion/main.py` (WindowManager integration, sync re-auth, upload threading)
- `src/voidstorm_companion/tray.py` (add `update_menu()` call in `set_status` — bonus fix, trivial)

## Full Improvement Backlog

For future sessions — prioritized list from the three-agent review:

### High Priority
5. Non-atomic file writes (diff_engine, upload_history, config)
6. No JSONDecodeError handling on load (all _load methods)
7. No thread locks on DiffEngine/UploadHistory
8. self.client race condition (no lock)
9. bind_all mousewheel leak (fixed as part of bug 1-2)
10. Status label never refreshes (fixed as bonus in this batch)

### Medium Priority
11. Lua parser fragility (index crash, UTF-8, mixed keys)
12. Auth flow eats preflight requests
13. Hard-coded dev path in config.py
14. Unconditional import winreg
15. File-change upload blocks watchdog thread
16. total_imported() misleading (capped at 50)
17. Fixed geometry ignores DPI scaling
18. Long error strings overflow in history
19. Version parser crashes on pre-release tags
20. Debounce timer has no lock

### UX Improvements
21. Add tray notifications (icon.notify)
22. Relative timestamps everywhere
23. Restructure tray menu (auth at top, disable Upload Now when logged out)
24. Improve tooltip (watching status, account count, relative time)
25. Extract shared theme to theme.py
26. Add "View on Voidstorm.cc" link in history
27. Persist lifetime total counter
28. Settings: feedback on Detect Accounts
29. Settings: Browse button for manual path
30. Settings: path validation indicators
31. History: alternating row colors
32. Set proper app icon in window title bars
