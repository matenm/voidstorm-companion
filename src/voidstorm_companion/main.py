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
                self._do_login()
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
        threading.Thread(target=self._settings_worker, daemon=True).start()

    def _settings_worker(self):
        from voidstorm_companion.settings_window import open_settings
        open_settings(self.config)

    def _do_history(self):
        threading.Thread(target=self._history_worker, daemon=True).start()

    def _history_worker(self):
        from voidstorm_companion.history_window import open_history
        open_history(self.history)

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
        log.info("Shutting down")

    def run(self):
        log.info("Voidstorm Companion starting...")

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
            on_upload_now=self._do_upload,
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
