import json
import os
import platform
import glob

DEFAULT_API_URL = "https://dev.voidstorm.cc"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".voidstorm-companion")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_PATH = os.path.join(CONFIG_DIR, "uploaded.json")


def _default_wow_patterns() -> list[str]:
    if platform.system() == "Windows":
        return [
            os.path.join(
                os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                r"World of Warcraft\_retail_\WTF\Account\*\SavedVariables\VoidstormGamble.lua",
            ),
            r"E:\Games\World of Warcraft\_retail_\WTF\Account\*\SavedVariables\VoidstormGamble.lua",
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


class Config:
    def __init__(self):
        self.api_url: str = DEFAULT_API_URL
        self.savedvariables_path: str = ""
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                self.api_url = data.get("api_url", DEFAULT_API_URL)
                self.savedvariables_path = data.get("savedvariables_path", "")

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump({
                "api_url": self.api_url,
                "savedvariables_path": self.savedvariables_path,
            }, f, indent=2)
