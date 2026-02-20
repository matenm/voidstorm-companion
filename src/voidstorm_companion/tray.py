import pystray
from PIL import Image, ImageDraw


def create_icon_image(color: str = "#7c3aed") -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    return img


class TrayApp:
    def __init__(self, on_upload_now, on_login, on_quit):
        self.on_upload_now = on_upload_now
        self.on_login = on_login
        self.on_quit = on_quit
        self.status = "Idle"
        self.icon: pystray.Icon | None = None

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda text: f"Status: {self.status}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Upload Now", lambda: self.on_upload_now()),
            pystray.MenuItem("Login", lambda: self.on_login()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.quit()),
        )

    def set_status(self, status: str, color: str | None = None):
        self.status = status
        if self.icon and color:
            self.icon.icon = create_icon_image(color)

    def quit(self):
        self.on_quit()
        if self.icon:
            self.icon.stop()

    def run(self):
        self.icon = pystray.Icon(
            "Voidstorm Companion",
            icon=create_icon_image(),
            title="Voidstorm Companion",
            menu=self._build_menu(),
        )
        self.icon.run()
