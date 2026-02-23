import os
import sys

BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
BTN_BG = "#313244"
BTN_HOVER = "#45475a"
SURFACE = "#181825"
GREEN = "#a6e3a1"
RED = "#f38ba8"


def app_icon_path() -> str:
    if getattr(sys, '_MEIPASS', None):
        base = os.path.join(sys._MEIPASS, 'assets')
    else:
        base = os.path.join(os.path.dirname(__file__), '..', '..', 'assets')
    return os.path.join(base, 'app.ico')
