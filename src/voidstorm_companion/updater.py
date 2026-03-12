import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import requests

log = logging.getLogger("voidstorm-companion")

CURRENT_VERSION = "1.0.0"
RELEASES_URL = "https://api.github.com/repos/matenm/voidstorm-companion/releases/latest"
UPDATE_DIR_PREFIX = "_voidstorm_update"


def _parse_version(tag: str) -> tuple[int, ...]:
    stripped = tag.lstrip("v")
    parts = stripped.split("-", 1)
    clean = parts[0]
    is_prerelease = len(parts) > 1
    try:
        numeric = tuple(int(x) for x in clean.split("."))
    except ValueError:
        return (0,)
    return numeric + (0,) if is_prerelease else numeric + (1,)


def _find_checksum_url(assets: list[dict]) -> str | None:
    for asset in assets:
        name = asset.get("name", "")
        if name in ("SHA256SUMS", "checksums.txt"):
            return asset.get("browser_download_url")
    return None


def _find_portable_zip_url(assets: list[dict]) -> str | None:
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".zip") and "portable" in name.lower():
            return asset.get("browser_download_url")
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".zip"):
            return asset.get("browser_download_url")
    return None


def check_for_update() -> dict | None:
    try:
        resp = requests.get(RELEASES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        if not tag:
            return None
        if _parse_version(tag) > _parse_version(CURRENT_VERSION):
            assets = data.get("assets", [])
            return {
                "version": tag.lstrip("v"),
                "url": data.get("html_url", ""),
                "download_url": _find_portable_zip_url(assets),
                "checksum_url": _find_checksum_url(assets),
            }
    except Exception:
        log.debug("Update check failed", exc_info=True)
    return None


def download_update(url: str, checksum_url: str | None = None) -> str:
    tmp_dir = tempfile.mkdtemp(prefix=UPDATE_DIR_PREFIX)
    zip_path = os.path.join(tmp_dir, "update.zip")
    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if checksum_url:
            try:
                cs_resp = requests.get(checksum_url, timeout=30)
                cs_resp.raise_for_status()
                expected_hash = None
                zip_basename = os.path.basename(url)
                for line in cs_resp.text.splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].lstrip("*") == zip_basename:
                        expected_hash = parts[0].lower()
                        break
                if expected_hash is None:
                    for line in cs_resp.text.splitlines():
                        parts = line.split()
                        if len(parts) >= 1 and len(parts[0]) == 64:
                            expected_hash = parts[0].lower()
                            break
                if expected_hash:
                    sha = hashlib.sha256()
                    with open(zip_path, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            sha.update(chunk)
                    actual_hash = sha.hexdigest()
                    if actual_hash != expected_hash:
                        raise ValueError(
                            f"SHA-256 mismatch: expected {expected_hash}, got {actual_hash}"
                        )
            except ValueError:
                raise
            except Exception as exc:
                log.warning("Checksum verification skipped: %s", exc)
        else:
            log.warning("No checksum file in release; skipping SHA-256 verification")

        with zipfile.ZipFile(zip_path, "r") as zf:
            exe_name = None
            for name in zf.namelist():
                if name.endswith("VoidstormCompanion.exe"):
                    exe_name = name
                    break
            if not exe_name:
                raise FileNotFoundError("VoidstormCompanion.exe not found in update zip")
            zf.extract(exe_name, tmp_dir)

        os.remove(zip_path)
        return os.path.join(tmp_dir, exe_name)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def apply_update(new_exe_path: str) -> None:
    current_exe = sys.executable
    script = (
        '@echo off\n'
        'timeout /t 3 /nobreak >nul\n'
        f'copy /y "{new_exe_path}" "{current_exe}"\n'
        'if errorlevel 1 (\n'
        f'    start "" "{current_exe}"\n'
        '    goto :cleanup\n'
        ')\n'
        f'start "" "{current_exe}"\n'
        f'del /q "{new_exe_path}"\n'
        ':cleanup\n'
        'del /q "%~f0"\n'
    )
    script_path = os.path.join(tempfile.gettempdir(), f"{UPDATE_DIR_PREFIX}.bat")
    with open(script_path, "w") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd", "/c", script_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )


def cleanup_old_update():
    tmp = tempfile.gettempdir()
    for entry in os.listdir(tmp):
        if entry.startswith(UPDATE_DIR_PREFIX):
            path = os.path.join(tmp, entry)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
