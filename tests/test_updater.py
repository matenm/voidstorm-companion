import hashlib
import os
import shutil
import sys
import tempfile
import zipfile

import pytest

from voidstorm_companion.updater import (
    _find_checksum_url,
    _find_portable_zip_url,
    _parse_version,
    cleanup_old_update,
    download_update,
    apply_update,
    UPDATE_DIR_PREFIX,
)


def test_parse_version_basic():
    assert _parse_version("v1.2.3") == (1, 2, 3, 1)
    assert _parse_version("1.0.0") == (1, 0, 0, 1)
    assert _parse_version("v2.0.0-beta.1") == (2, 0, 0, 0)
    assert _parse_version("v1.0.0-alpha") < _parse_version("v1.0.0")


def test_parse_version_invalid():
    assert _parse_version("garbage") == (0,)


def test_find_portable_zip_prefers_portable():
    assets = [
        {"name": "VoidstormCompanion-installer.exe", "browser_download_url": "https://example.com/installer"},
        {"name": "VoidstormCompanion-portable.zip", "browser_download_url": "https://example.com/portable"},
        {"name": "VoidstormCompanion.zip", "browser_download_url": "https://example.com/plain"},
    ]
    assert _find_portable_zip_url(assets) == "https://example.com/portable"


def test_find_portable_zip_falls_back_to_any_zip():
    assets = [
        {"name": "VoidstormCompanion-installer.exe", "browser_download_url": "https://example.com/installer"},
        {"name": "VoidstormCompanion.zip", "browser_download_url": "https://example.com/plain"},
    ]
    assert _find_portable_zip_url(assets) == "https://example.com/plain"


def test_find_portable_zip_returns_none_without_zip():
    assets = [
        {"name": "VoidstormCompanion-installer.exe", "browser_download_url": "https://example.com/installer"},
    ]
    assert _find_portable_zip_url(assets) is None


def test_find_portable_zip_empty_assets():
    assert _find_portable_zip_url([]) is None


def test_find_checksum_url_sha256sums():
    assets = [
        {"name": "VoidstormCompanion.zip", "browser_download_url": "https://example.com/zip"},
        {"name": "SHA256SUMS", "browser_download_url": "https://example.com/sha256sums"},
    ]
    assert _find_checksum_url(assets) == "https://example.com/sha256sums"


def test_find_checksum_url_checksums_txt():
    assets = [
        {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums"},
    ]
    assert _find_checksum_url(assets) == "https://example.com/checksums"


def test_find_checksum_url_none():
    assets = [
        {"name": "VoidstormCompanion.zip", "browser_download_url": "https://example.com/zip"},
    ]
    assert _find_checksum_url(assets) is None


@pytest.fixture
def fake_update_zip():
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "fake_update.zip")
    exe_content = b"FAKE_EXE_CONTENT"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("VoidstormCompanion.exe", exe_content)
    yield zip_path, exe_content
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)


def test_download_update(fake_update_zip, httpserver):
    zip_path, exe_content = fake_update_zip
    with open(zip_path, "rb") as f:
        zip_data = f.read()

    httpserver.expect_request("/update.zip").respond_with_data(zip_data, content_type="application/zip")
    url = httpserver.url_for("/update.zip")

    result_path = download_update(url)
    assert result_path.endswith("VoidstormCompanion.exe")
    assert os.path.exists(result_path)
    with open(result_path, "rb") as f:
        assert f.read() == exe_content

    shutil.rmtree(os.path.dirname(result_path))


def test_download_update_with_valid_checksum(fake_update_zip, httpserver):
    zip_path, exe_content = fake_update_zip
    with open(zip_path, "rb") as f:
        zip_data = f.read()

    digest = hashlib.sha256(zip_data).hexdigest()
    checksum_content = f"{digest}  update.zip\n"

    httpserver.expect_request("/update.zip").respond_with_data(zip_data, content_type="application/zip")
    httpserver.expect_request("/SHA256SUMS").respond_with_data(checksum_content, content_type="text/plain")

    url = httpserver.url_for("/update.zip")
    checksum_url = httpserver.url_for("/SHA256SUMS")

    result_path = download_update(url, checksum_url=checksum_url)
    assert result_path.endswith("VoidstormCompanion.exe")
    assert os.path.exists(result_path)

    shutil.rmtree(os.path.dirname(result_path))


def test_download_update_checksum_mismatch(fake_update_zip, httpserver):
    zip_path, exe_content = fake_update_zip
    with open(zip_path, "rb") as f:
        zip_data = f.read()

    wrong_digest = "a" * 64
    checksum_content = f"{wrong_digest}  update.zip\n"

    httpserver.expect_request("/update.zip").respond_with_data(zip_data, content_type="application/zip")
    httpserver.expect_request("/SHA256SUMS").respond_with_data(checksum_content, content_type="text/plain")

    url = httpserver.url_for("/update.zip")
    checksum_url = httpserver.url_for("/SHA256SUMS")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        download_update(url, checksum_url=checksum_url)


def test_download_update_no_checksum_file_warns(fake_update_zip, httpserver, caplog):
    zip_path, exe_content = fake_update_zip
    with open(zip_path, "rb") as f:
        zip_data = f.read()

    httpserver.expect_request("/update.zip").respond_with_data(zip_data, content_type="application/zip")
    url = httpserver.url_for("/update.zip")

    import logging
    with caplog.at_level(logging.WARNING, logger="voidstorm-companion"):
        result_path = download_update(url, checksum_url=None)

    assert "skipping SHA-256 verification" in caplog.text
    assert os.path.exists(result_path)
    shutil.rmtree(os.path.dirname(result_path))


def test_download_update_missing_exe(httpserver):
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "bad.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("README.txt", "no exe here")

    with open(zip_path, "rb") as f:
        zip_data = f.read()

    httpserver.expect_request("/bad.zip").respond_with_data(zip_data, content_type="application/zip")
    url = httpserver.url_for("/bad.zip")

    with pytest.raises(FileNotFoundError, match="VoidstormCompanion.exe not found"):
        download_update(url)

    shutil.rmtree(tmp_dir)


def test_download_update_cleans_up_on_failure(httpserver):
    httpserver.expect_request("/fail.zip").respond_with_data(b"not a zip", content_type="application/zip")
    url = httpserver.url_for("/fail.zip")

    created_dirs_before = set(
        os.path.join(tempfile.gettempdir(), e)
        for e in os.listdir(tempfile.gettempdir())
        if e.startswith(UPDATE_DIR_PREFIX)
    )

    with pytest.raises(Exception):
        download_update(url)

    created_dirs_after = set(
        os.path.join(tempfile.gettempdir(), e)
        for e in os.listdir(tempfile.gettempdir())
        if e.startswith(UPDATE_DIR_PREFIX)
    )

    new_dirs = created_dirs_after - created_dirs_before
    assert len(new_dirs) == 0, f"Temp dirs were not cleaned up: {new_dirs}"


def test_apply_update_creates_batch_script(monkeypatch):
    fake_exe = os.path.join(tempfile.gettempdir(), "fake_new.exe")
    with open(fake_exe, "w") as f:
        f.write("fake")

    launched = []
    monkeypatch.setattr("voidstorm_companion.updater.subprocess.Popen", lambda *a, **kw: launched.append((a, kw)))

    try:
        apply_update(fake_exe)

        script_path = os.path.join(tempfile.gettempdir(), f"{UPDATE_DIR_PREFIX}.bat")
        assert os.path.exists(script_path)

        with open(script_path) as f:
            content = f.read()
        assert "@echo off" in content
        assert "timeout /t 3" in content
        assert "copy /y" in content
        assert "if errorlevel 1" in content
        assert fake_exe in content
        assert sys.executable in content
        assert len(launched) == 1
    finally:
        script_path = os.path.join(tempfile.gettempdir(), f"{UPDATE_DIR_PREFIX}.bat")
        if os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(fake_exe):
            os.remove(fake_exe)


def test_apply_update_batch_script_relaunches_old_exe_on_copy_failure(monkeypatch):
    fake_exe = os.path.join(tempfile.gettempdir(), "fake_new.exe")
    with open(fake_exe, "w") as f:
        f.write("fake")

    monkeypatch.setattr("voidstorm_companion.updater.subprocess.Popen", lambda *a, **kw: None)

    try:
        apply_update(fake_exe)

        script_path = os.path.join(tempfile.gettempdir(), f"{UPDATE_DIR_PREFIX}.bat")
        with open(script_path) as f:
            content = f.read()

        errorlevel_idx = content.index("if errorlevel 1")
        old_exe_launch_idx = content.index(f'start "" "{sys.executable}"', errorlevel_idx)
        goto_idx = content.index("goto :cleanup", errorlevel_idx)
        assert old_exe_launch_idx < goto_idx
    finally:
        script_path = os.path.join(tempfile.gettempdir(), f"{UPDATE_DIR_PREFIX}.bat")
        if os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(fake_exe):
            os.remove(fake_exe)


def test_cleanup_old_update():
    stale_dir = tempfile.mkdtemp(prefix=UPDATE_DIR_PREFIX)
    stale_file = os.path.join(tempfile.gettempdir(), f"{UPDATE_DIR_PREFIX}_stale.bat")
    with open(stale_file, "w") as f:
        f.write("stale")

    assert os.path.exists(stale_dir)
    assert os.path.exists(stale_file)

    cleanup_old_update()

    assert not os.path.exists(stale_dir)
    assert not os.path.exists(stale_file)
