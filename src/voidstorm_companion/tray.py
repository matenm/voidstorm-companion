import os
import sys
import webbrowser

import pystray
from PIL import Image


def _assets_dir() -> str:
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, 'assets')
    return os.path.join(os.path.dirname(__file__), '..', '..', 'assets')


def _load_icon(name: str) -> Image.Image:
    path = os.path.join(_assets_dir(), name)
    return Image.open(path).resize((64, 64), Image.LANCZOS)


ICON_ACTIVE = None
ICON_INACTIVE = None


def _get_icon(active: bool) -> Image.Image:
    global ICON_ACTIVE, ICON_INACTIVE
    if active:
        if ICON_ACTIVE is None:
            ICON_ACTIVE = _load_icon('icon_active.png')
        return ICON_ACTIVE
    else:
        if ICON_INACTIVE is None:
            ICON_INACTIVE = _load_icon('icon_inactive.png')
        return ICON_INACTIVE


class TrayApp:
    def __init__(self, on_upload_now, on_login, on_logout, on_quit,
                 on_settings=None, on_history=None, on_dashboard=None,
                 on_group_finder=None, on_update=None, on_debt_manager=None):
        self.on_upload_now = on_upload_now
        self.on_login = on_login
        self.on_logout = on_logout
        self.on_quit = on_quit
        self.on_settings = on_settings
        self.on_history = on_history
        self.on_dashboard = on_dashboard
        self.on_group_finder = on_group_finder
        self.on_update = on_update
        self.on_debt_manager = on_debt_manager
        self.status = "Idle"
        self.logged_in = False
        self.icon: pystray.Icon | None = None
        self.update_info: dict | None = None

    def _open_update(self):
        if self.update_info and self.update_info.get("url"):
            webbrowser.open(self.update_info["url"])

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda text: f"Update available (v{self.update_info['version']})",
                lambda: self.on_update() if self.on_update else self._open_update(),
                visible=lambda item: self.update_info is not None,
            ),
            pystray.MenuItem(lambda text: f"Status: {self.status}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Login",
                lambda: self.on_login(),
                visible=lambda item: not self.logged_in,
            ),
            pystray.MenuItem(
                "Logout",
                lambda: self.on_logout(),
                visible=lambda item: self.logged_in,
            ),
            pystray.MenuItem(
                "Upload Now",
                lambda: self.on_upload_now(),
                enabled=lambda item: self.logged_in,
            ),
            pystray.MenuItem(
                "Group Finder",
                lambda: self.on_group_finder() if self.on_group_finder else None,
                enabled=lambda item: self.logged_in,
            ),
            pystray.MenuItem(
                "Debt Manager",
                lambda: self.on_debt_manager() if self.on_debt_manager else None,
            ),
            pystray.MenuItem(
                "Dashboard",
                lambda: self.on_dashboard() if self.on_dashboard else None,
                default=True,
            ),
            pystray.MenuItem(
                "Upload History",
                lambda: self.on_history() if self.on_history else None,
            ),
            pystray.MenuItem(
                "Settings",
                lambda: self.on_settings() if self.on_settings else None,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.quit()),
        )

    def set_status(self, status: str, logged_in: bool | None = None):
        self.status = status
        if logged_in is not None:
            self.logged_in = logged_in
        if self.icon:
            try:
                self.icon.icon = _get_icon(self.logged_in)
                self.icon.update_menu()
            except OSError:
                pass

    def set_tooltip(self, total_uploaded: int, last_upload: str | None, watching: bool = False,
                    elo: int | None = None, tier: str | None = None):
        if not self.icon:
            return
        lines = ["Voidstorm Companion"]
        if watching:
            lines.append("Watching for changes")
        lines.append(f"Uploaded: {total_uploaded} sessions")
        lines.append(f"Last: {last_upload}" if last_upload else "Last: Never")
        if elo is not None:
            tier_str = f" ({tier.title()})" if tier else ""
            lines.append(f"ELO: {elo}{tier_str}")
        try:
            self.icon.title = "\n".join(lines)
        except OSError:
            pass

    def notify(self, title: str, message: str):
        if self.icon:
            try:
                self.icon.notify(message, title)
            except OSError:
                pass

    def set_update(self, info: dict | None):
        self.update_info = info

    def quit(self):
        self.on_quit()
        if self.icon:
            self.icon.stop()

    def run(self):
        self.icon = pystray.Icon(
            "Voidstorm Companion",
            icon=_get_icon(self.logged_in),
            title="Voidstorm Companion",
            menu=self._build_menu(),
        )
        self.icon.run()
