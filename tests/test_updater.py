import os
import sys
import tempfile
import zipfile

import pytest

from voidstorm_companion.updater import (
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


@pytest.fixture
def fake_update_zip():
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "fake_update.zip")
    exe_content = b"FAKE_EXE_CONTENT"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("VoidstormCompanion.exe", exe_content)
    yield zip_path, exe_content
    if os.path.exists(tmp_dir):
        import shutil
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

    import shutil
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

    import shutil
    shutil.rmtree(tmp_dir)


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
        assert "timeout /t 2" in content
        assert "copy /y" in content
        assert fake_exe in content
        assert sys.executable in content
        assert len(launched) == 1
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
