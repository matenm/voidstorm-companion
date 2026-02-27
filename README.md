# Voidstorm Companion

Desktop companion app for the [VoidstormGamba](https://voidstorm.cc) World of Warcraft addon. Monitors your SavedVariables files and automatically syncs gambling session data to the Voidstorm website.

## Features

- Automatic detection of WoW accounts and SavedVariables files
- Real-time file monitoring with auto-upload on change
- Battle.net authentication
- Session dashboard with stats (gold wagered, win/loss, top players)
- Upload history tracking
- System tray with status indicators and notifications
- Auto-update notifications

## Install

### Installer (recommended)

Download `VoidstormCompanion-x.x.x-Setup.exe` from the [latest release](https://github.com/matenm/voidstorm-companion/releases/latest). Run the installer and optionally enable "Start with Windows".

### Portable

Download `VoidstormCompanion-x.x.x-portable.zip` from the [latest release](https://github.com/matenm/voidstorm-companion/releases/latest). Extract and run `VoidstormCompanion.exe`.

### Verify download

Each release includes a `checksums.txt` file with SHA-256 hashes. To verify:

```powershell
Get-FileHash VoidstormCompanion-1.0.0-Setup.exe -Algorithm SHA256
```

Compare the output hash with the one in `checksums.txt`.

### From source

Requires Python 3.11+.

```bash
git clone https://github.com/matenm/voidstorm-companion.git
cd voidstorm-companion
pip install -r requirements.txt
pip install -e .
python src/voidstorm_companion/main.py
```

## Usage

On first launch the app sits in the system tray. Right-click the tray icon to:

- **Log in** with your Battle.net account
- **Upload Now** to manually sync sessions
- **Dashboard** to view gambling stats
- **Settings** to configure WoW accounts, auto-upload, and API server

### CLI flags

| Flag | Description |
|------|-------------|
| `--dev` | Use the development API server (`dev.voidstorm.cc`) for the current session |
| `--minimized` | Start minimized to tray |

## Configuration

Settings are stored in `~/.voidstorm-companion/config.json`. The app auto-detects WoW installations on drives C-H and Program Files.
