import json
import os
import platform
import glob
import sys
try:
    import winreg
except ImportError:
    winreg = None

DEFAULT_API_URL = "https://voidstorm.cc"
DEV_API_URL = "https://dev.voidstorm.cc"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".voidstorm-companion")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_PATH = os.path.join(CONFIG_DIR, "uploaded.json")
STATS_PATH = os.path.join(CONFIG_DIR, "stats.json")


_SV_NAME = "VoidstormGamba.lua"
_PL_SV_NAME = "VoidstormPartyLedger.lua"
_KEYS_SV_NAME = "VoidstormKeys.lua"


def _default_wow_patterns() -> list[str]:
    if platform.system() == "Windows":
        patterns = [os.path.join(
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            rf"World of Warcraft\_retail_\WTF\Account\*\SavedVariables\{_SV_NAME}",
        )]
        for letter in "CDEFGH":
            patterns.append(rf"{letter}:\Games\World of Warcraft\_retail_\WTF\Account\*\SavedVariables\{_SV_NAME}")
        return patterns
    else:
        return [
            f"/Applications/World of Warcraft/_retail_/WTF/Account/*/SavedVariables/{_SV_NAME}",
        ]


def detect_savedvariables() -> list[str]:
    found = []
    for pattern in _default_wow_patterns():
        found.extend(glob.glob(pattern))
    return sorted(set(found))


def _default_partyledger_patterns() -> list[str]:
    if platform.system() == "Windows":
        patterns = [os.path.join(
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            rf"World of Warcraft\_retail_\WTF\Account\*\SavedVariables\{_PL_SV_NAME}",
        )]
        for letter in "CDEFGH":
            patterns.append(rf"{letter}:\Games\World of Warcraft\_retail_\WTF\Account\*\SavedVariables\{_PL_SV_NAME}")
        return patterns
    else:
        return [
            f"/Applications/World of Warcraft/_retail_/WTF/Account/*/SavedVariables/{_PL_SV_NAME}",
        ]


def detect_partyledger_savedvariables() -> list[str]:
    found = []
    for pattern in _default_partyledger_patterns():
        found.extend(glob.glob(pattern))
    return sorted(set(found))


def _default_keys_patterns() -> list[str]:
    if platform.system() == "Windows":
        patterns = [os.path.join(
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            rf"World of Warcraft\_retail_\WTF\Account\*\SavedVariables\{_KEYS_SV_NAME}",
        )]
        for letter in "CDEFGH":
            patterns.append(rf"{letter}:\Games\World of Warcraft\_retail_\WTF\Account\*\SavedVariables\{_KEYS_SV_NAME}")
        return patterns
    else:
        return [
            f"/Applications/World of Warcraft/_retail_/WTF/Account/*/SavedVariables/{_KEYS_SV_NAME}",
        ]


def detect_keys_savedvariables() -> list[str]:
    found = []
    for pattern in _default_keys_patterns():
        found.extend(glob.glob(pattern))
    return sorted(set(found))


def migrate_paths(paths: list[str]) -> list[str]:
    migrated = []
    for p in paths:
        if p.endswith("VoidstormGamble.lua"):
            new_p = p.replace("VoidstormGamble.lua", _SV_NAME)
            if os.path.exists(new_p):
                p = new_p
        if p not in migrated:
            migrated.append(p)
    return migrated


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
        self.auto_upload: bool = True
        self.analytics: bool = True
        self.webhook_url: str = ""
        self.stats_webhook_url: str = ""
        self.stats_summary_threshold: int = 5
        self.league_webhook_url: str = ""
        self.reputation_webhook_url: str = ""
        self.webhook_verbosity: str = "normal"
        self.partyledger_paths: list[str] = []
        self.keys_paths: list[str] = []
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
                    self.savedvariables_paths = migrate_paths(data["savedvariables_paths"])
                elif "savedvariables_path" in data and data["savedvariables_path"]:
                    self.savedvariables_paths = migrate_paths([data["savedvariables_path"]])
                else:
                    self.savedvariables_paths = []
                self.start_with_windows = data.get("start_with_windows", True)
                self.start_minimized = data.get("start_minimized", True)
                self.auto_upload = data.get("auto_upload", True)
                self.analytics = data.get("analytics", True)
                self.webhook_url = data.get("webhook_url", "")
                self.stats_webhook_url = data.get("stats_webhook_url", "")
                self.stats_summary_threshold = int(data.get("stats_summary_threshold", 5))
                self.league_webhook_url = data.get("league_webhook_url", "")
                self.reputation_webhook_url = data.get("reputation_webhook_url", "")
                self.webhook_verbosity = data.get("webhook_verbosity", "normal")
                self.partyledger_paths = data.get("partyledger_paths", [])
                self.keys_paths = data.get("keys_paths", [])
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
                    "auto_upload": self.auto_upload,
                    "analytics": self.analytics,
                    "webhook_url": self.webhook_url,
                    "stats_webhook_url": self.stats_webhook_url,
                    "stats_summary_threshold": self.stats_summary_threshold,
                    "league_webhook_url": self.league_webhook_url,
                    "reputation_webhook_url": self.reputation_webhook_url,
                    "webhook_verbosity": self.webhook_verbosity,
                    "partyledger_paths": self.partyledger_paths,
                    "keys_paths": self.keys_paths,
                }, f, indent=2)
            os.replace(tmp_path, CONFIG_PATH)
        except BaseException:
            os.unlink(tmp_path)
            raise
