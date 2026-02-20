import logging

from voidstorm_companion.config import Config, STATE_PATH
from voidstorm_companion.lua_parser import parse_savedvariables
from voidstorm_companion.diff_engine import DiffEngine
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
        self.watcher: SavedVariablesWatcher | None = None
        self.tray: TrayApp | None = None
        self.client: ApiClient | None = None

    def _ensure_auth(self) -> bool:
        token = get_stored_token()
        if token:
            self.client = ApiClient(self.config.api_url, token)
            return True
        return False

    def _do_login(self):
        log.info("Starting Battle.net login flow...")
        if self.tray:
            self.tray.set_status("Logging in...", "#f59e0b")
        token = authenticate(self.config.api_url)
        if token:
            self.client = ApiClient(self.config.api_url, token)
            log.info("Login successful!")
            if self.tray:
                self.tray.set_status("Authenticated", "#22c55e")
        else:
            log.error("Login failed or timed out")
            if self.tray:
                self.tray.set_status("Login failed", "#ef4444")

    def _do_upload(self, _is_retry: bool = False):
        if not self.config.savedvariables_path:
            log.warning("No SavedVariables path configured")
            return

        if not self.client:
            if not self._ensure_auth():
                log.warning("Not authenticated — skipping upload")
                return

        try:
            if self.tray:
                self.tray.set_status("Parsing...", "#3b82f6")

            sessions = parse_savedvariables(self.config.savedvariables_path)
            new_sessions = self.diff.filter_new(sessions)

            if not new_sessions:
                log.info("No new sessions to upload")
                if self.tray:
                    self.tray.set_status("Up to date", "#22c55e")
                return

            log.info(f"Uploading {len(new_sessions)} new session(s)...")
            if self.tray:
                self.tray.set_status(f"Uploading {len(new_sessions)}...", "#3b82f6")

            result = self.client.upload(new_sessions)

            uploaded_ids = [s["id"] for s in new_sessions]
            self.diff.mark_uploaded(uploaded_ids)

            log.info(
                f"Upload complete: {result.get('imported', 0)} imported, "
                f"{result.get('skipped', 0)} skipped"
            )
            if self.tray:
                self.tray.set_status(
                    f"Uploaded {result.get('imported', 0)}", "#22c55e"
                )

        except AuthError:
            if _is_retry:
                log.error("Re-authentication failed — please log in manually")
                if self.tray:
                    self.tray.set_status("Auth failed", "#ef4444")
                return
            log.warning("Token expired — re-authenticating...")
            self.client = None
            clear_token()
            self._do_login()
            if self.client:
                self._do_upload(_is_retry=True)
        except FileNotFoundError:
            log.error(f"SavedVariables not found: {self.config.savedvariables_path}")
            if self.tray:
                self.tray.set_status("File not found", "#ef4444")
        except Exception as e:
            log.error(f"Upload error: {e}")
            if self.tray:
                self.tray.set_status("Error", "#ef4444")

    def _on_file_change(self, filepath: str):
        log.info(f"File change detected: {filepath}")
        self._do_upload()

    def _on_quit(self):
        if self.watcher:
            self.watcher.stop()
        log.info("Shutting down")

    def run(self):
        log.info("Voidstorm Companion starting...")

        if not self.config.savedvariables_path:
            from voidstorm_companion.config import detect_savedvariables
            found = detect_savedvariables()
            if found:
                self.config.savedvariables_path = found[0]
                self.config.save()
                log.info(f"Auto-detected SavedVariables: {found[0]}")
            else:
                log.warning("Could not auto-detect WoW SavedVariables path")

        self._ensure_auth()

        if self.config.savedvariables_path:
            self.watcher = SavedVariablesWatcher(
                self.config.savedvariables_path,
                self._on_file_change,
            )
            self.watcher.start()
            log.info(f"Watching: {self.config.savedvariables_path}")

        self.tray = TrayApp(
            on_upload_now=self._do_upload,
            on_login=self._do_login,
            on_quit=self._on_quit,
        )

        status = "Watching" if self.watcher else "No WoW path"
        color = "#22c55e" if self.watcher else "#f59e0b"
        if not self.client:
            status = "Not logged in"
            color = "#f59e0b"
        self.tray.set_status(status, color)

        self.tray.run()


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
