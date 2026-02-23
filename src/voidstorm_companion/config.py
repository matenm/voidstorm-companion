import json
import os
import platform
import glob
import sys
try:
    import winreg
except ImportError:
    winreg = None

DEFAULT_API_URL = "https://dev.voidstorm.cc"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".voidstorm-companion")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_PATH = os.path.join(CONFIG_DIR, "uploaded.json")
STATS_PATH = os.path.join(CONFIG_DIR, "stats.json")


def _default_wow_patterns() -> list[str]:
    if platform.system() == "Windows":
        return [
            os.path.join(
                os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                r"World of Warcraft\_retail_\WTF\Account\*\SavedVariables\VoidstormGamble.lua",
            ),
            r"D:\Games\World of Warcraft\_retail_\WTF\Account\*\SavedVariables\VoidstormGamble.lua",
        ]
    else:
        return [
            "/Applications/World of Warcraft/_retail_/WTF/Account/*/SavedVariables/VoidstormGamble.lua",
        ]


def detect_savedvariables() -> list[str]:
    found = []
    for pattern in _default_wow_patterns():
        found.extend(glob.glob(pattern))
    return sorted(set(found))


_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_VALUE = "VoidstormCompanion"


def get_autostart() -> bool:
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _AUTOSTART_VALUE)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_autostart(enabled: bool, minimized: bool = True):
    if winreg is None:
        return
    exe = sys.executable
    value = f'"{exe}" --minimized' if minimized else f'"{exe}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, _AUTOSTART_VALUE, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, _AUTOSTART_VALUE)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError:
        pass


HISTORY_PATH = os.path.join(CONFIG_DIR, "history.json")


class Config:
    def __init__(self):
        self.api_url: str = DEFAULT_API_URL
        self.savedvariables_paths: list[str] = []
        self.start_with_windows: bool = True
        self.start_minimized: bool = True
        self.load()

    @property
    def savedvariables_path(self) -> str:
        return self.savedvariables_paths[0] if self.savedvariables_paths else ""

    @savedvariables_path.setter
    def savedvariables_path(self, value: str):
        if value:
            self.savedvariables_paths = [value]
        else:
            self.savedvariables_paths = []

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                self.api_url = data.get("api_url", DEFAULT_API_URL)
                if "savedvariables_paths" in data:
                    self.savedvariables_paths = data["savedvariables_paths"]
                elif "savedvariables_path" in data and data["savedvariables_path"]:
                    self.savedvariables_paths = [data["savedvariables_path"]]
                else:
                    self.savedvariables_paths = []
                self.start_with_windows = data.get("start_with_windows", True)
                self.start_minimized = data.get("start_minimized", True)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        import tempfile
        os.makedirs(CONFIG_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "api_url": self.api_url,
                    "savedvariables_paths": self.savedvariables_paths,
                    "start_with_windows": self.start_with_windows,
                    "start_minimized": self.start_minimized,
                }, f, indent=2)
            os.replace(tmp_path, CONFIG_PATH)
        except BaseException:
            os.unlink(tmp_path)
            raise
