import logging
import os
import threading
import webbrowser
from datetime import datetime, timezone

from voidstorm_companion.config import Config, STATE_PATH, HISTORY_PATH, STATS_PATH, set_autostart
from voidstorm_companion.lua_parser import parse_savedvariables
from voidstorm_companion.diff_engine import DiffEngine
from voidstorm_companion.upload_history import UploadHistory
from voidstorm_companion.api_client import ApiClient, AuthError
from voidstorm_companion.stats_store import StatsStore
from voidstorm_companion.auth_flow import authenticate, get_stored_token, clear_token
from voidstorm_companion.file_watcher import SavedVariablesWatcher
from voidstorm_companion.tray import TrayApp
from voidstorm_companion.window_manager import WindowManager
from voidstorm_companion.group_sync import GroupSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("voidstorm-companion")


def _derive_addon_path(sv_path: str) -> str | None:
    wow_root = sv_path
    for _ in range(4):
        wow_root = os.path.dirname(wow_root)
    candidate = os.path.join(wow_root, "Interface", "AddOns", "VoidstormGamba")
    if os.path.isdir(candidate):
        return candidate
    return None


class App:
    def __init__(self):
        self.config = Config()
        self.diff = DiffEngine(STATE_PATH)
        self.history = UploadHistory(HISTORY_PATH)
        self.stats = StatsStore(STATS_PATH)
        self.watchers: dict[str, SavedVariablesWatcher] = {}
        self.tray: TrayApp | None = None
        self.client: ApiClient | None = None
        self._client_lock = threading.Lock()
        self.window_manager = WindowManager()
        self._group_sync: GroupSync | None = None

    def _ensure_auth(self) -> bool:
        token = get_stored_token()
        if token:
            with self._client_lock:
                self.client = ApiClient(self.config.api_url, token)
            return True
        return False

    def _start_group_sync(self):
        with self._client_lock:
            client = self.client
        if not client:
            return
        addon_path = None
        for sv_path in self.config.savedvariables_paths:
            addon_path = _derive_addon_path(sv_path)
            if addon_path:
                break
        if not addon_path:
            log.warning("GroupSync: addon path not found, skipping")
            return
        if self._group_sync:
            self._group_sync.stop()
        self._group_sync = GroupSync(self.config.api_url, client.token, addon_path)
        self._group_sync.start()

    def _do_login(self):
        threading.Thread(target=self._login_worker, daemon=True).start()

    def _login_worker(self):
        log.info("Starting Battle.net login flow...")
        if self.tray:
            self.tray.set_status("Logging in...")
        token = authenticate(self.config.api_url)
        if token:
            with self._client_lock:
                self.client = ApiClient(self.config.api_url, token)
            log.info("Login successful!")
            self._start_group_sync()
            if self.tray:
                self.tray.set_status("Authenticated", logged_in=True)
        else:
            log.error("Login failed or timed out")
            if self.tray:
                self.tray.set_status("Login failed", logged_in=False)

    def _do_logout(self):
        log.info("Logging out...")
        with self._client_lock:
            self.client = None
        clear_token()
        if self.tray:
            self.tray.set_status("Logged out", logged_in=False)

    def _do_upload(self, path: str | None = None, _is_retry: bool = False):
        paths = [path] if path else list(self.config.savedvariables_paths)
        if not paths:
            log.warning("No SavedVariables paths configured")
            return

        with self._client_lock:
            client = self.client
        if not client:
            if not self._ensure_auth():
                log.warning("Not authenticated — skipping upload")
                return
            with self._client_lock:
                client = self.client

        total_imported = 0
        total_skipped = 0

        for sv_path in paths:
            try:
                if self.tray:
                    self.tray.set_status("Parsing...")

                sessions = parse_savedvariables(sv_path)
                self.stats.update(sessions)
                new_sessions = self.diff.filter_new(sessions)

                if not new_sessions:
                    log.info(f"No new sessions in {sv_path}")
                    continue

                log.info(f"Uploading {len(new_sessions)} new session(s) from {sv_path}...")
                if self.tray:
                    self.tray.set_status(f"Uploading {len(new_sessions)}...")

                result = client.upload(new_sessions)

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
                with self._client_lock:
                    self.client = None
                clear_token()
                if self.tray:
                    self.tray.set_status("Re-authenticating...", logged_in=False)
                self._login_worker()
                with self._client_lock:
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
        if total_imported and self.tray:
            self.tray.notify("Voidstorm Companion", f"Uploaded {total_imported} session(s)")

    def _do_upload_async(self, path: str | None = None):
        threading.Thread(target=self._do_upload, args=(path,), daemon=True).start()

    def _on_file_change(self, filepath: str):
        log.info(f"File change detected: {filepath}")
        if not self.config.auto_upload:
            log.info("Auto-upload disabled, skipping")
            return
        threading.Thread(target=self._do_upload, args=(filepath,), daemon=True).start()

    def _do_settings(self):
        self.window_manager.open_settings(self.config)

    def _do_history(self):
        self.window_manager.open_history(self.history)

    def _do_dashboard(self):
        self.window_manager.open_dashboard(self.stats, list(self.config.savedvariables_paths))

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
        self.tray.set_tooltip(total, last_str, watching=bool(self.watchers))

    def _check_update(self):
        from voidstorm_companion.updater import check_for_update
        info = check_for_update()
        if info and self.tray:
            log.info(f"Update available: v{info['version']}")
            self.tray.set_update(info)

    def _do_update(self):
        if not self.tray or not self.tray.update_info:
            return

        download_url = self.tray.update_info.get("download_url")
        if not download_url:
            self._open_release_page()
            return

        try:
            from voidstorm_companion.updater import download_update, apply_update

            self.tray.set_status("Downloading update...")
            new_exe = download_update(download_url)

            self.tray.set_status("Installing update...")
            apply_update(new_exe)

            self.tray.quit()
        except Exception as e:
            log.error(f"Auto-update failed: {e}")
            self._open_release_page()

    def _do_update_async(self):
        threading.Thread(target=self._do_update, daemon=True).start()

    def _open_release_page(self):
        if self.tray and self.tray.update_info and self.tray.update_info.get("url"):
            webbrowser.open(self.tray.update_info["url"])

    def _on_quit(self):
        if self._group_sync:
            self._group_sync.stop()
        for watcher in self.watchers.values():
            watcher.stop()
        self.window_manager.stop()
        log.info("Shutting down")

    def run(self):
        from voidstorm_companion.updater import cleanup_old_update
        cleanup_old_update()

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
        self._start_group_sync()

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
            on_dashboard=self._do_dashboard,
            on_update=self._do_update_async,
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
    import argparse
    parser = argparse.ArgumentParser(description="Voidstorm Companion")
    parser.add_argument("--dev", action="store_true", help="Use development API server (dev.voidstorm.cc)")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to tray")
    args = parser.parse_args()

    app = App()

    if args.dev:
        from voidstorm_companion.config import DEV_API_URL
        app.config.api_url = DEV_API_URL

    app.run()


if __name__ == "__main__":
    main()
