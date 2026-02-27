import json
import os
import threading
import time

import pytest

from voidstorm_companion import analytics


@pytest.fixture(autouse=True)
def _reset_analytics(monkeypatch):
    monkeypatch.setattr(analytics, "_enabled", False)
    monkeypatch.setattr(analytics, "_session_id", "")


@pytest.fixture
def tmp_session_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(analytics, "SESSION_ID_PATH", str(tmp_path / "analytics_id"))
    monkeypatch.setattr(analytics, "CONFIG_DIR", str(tmp_path))
    return tmp_path


def _wait_for_analytics_threads(timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        threads = [t for t in threading.enumerate() if t.daemon and t.name != "MainThread"]
        if not threads:
            return
        for t in threads:
            t.join(timeout=0.1)


def test_track_sends_correct_payload(httpserver, monkeypatch, tmp_session_dir):
    httpserver.expect_request("/api/send").respond_with_data("ok")

    monkeypatch.setattr(analytics, "UMAMI_URL", httpserver.url_for(""))
    monkeypatch.setattr(analytics, "WEBSITE_ID", "test-website-id")

    analytics.init(True)
    analytics.track("app_start", {"sessions": 5})

    _wait_for_analytics_threads()

    req = httpserver.log[0][0]
    body = json.loads(req.data)

    assert body["type"] == "event"
    assert body["payload"]["website"] == "test-website-id"
    assert body["payload"]["hostname"] == "companion-app"
    assert body["payload"]["url"] == "/app"
    assert body["payload"]["name"] == "app_start"
    assert body["payload"]["data"]["sessions"] == 5
    assert "version" in body["payload"]["data"]
    assert body["payload"]["id"] == analytics._session_id
    assert "VoidstormCompanion/" in req.headers.get("User-Agent", "")


def test_track_swallows_connection_errors(monkeypatch, tmp_session_dir):
    monkeypatch.setattr(analytics, "UMAMI_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(analytics, "WEBSITE_ID", "test-website-id")

    analytics.init(True)
    analytics.track("app_start")

    _wait_for_analytics_threads()


def test_disabled_analytics_skips_post(httpserver, monkeypatch, tmp_session_dir):
    httpserver.expect_request("/api/send").respond_with_data("ok")
    monkeypatch.setattr(analytics, "UMAMI_URL", httpserver.url_for(""))

    analytics.init(False)
    analytics.track("app_start")

    assert len(httpserver.log) == 0


def test_session_id_persists(tmp_session_dir):
    analytics.init(True)
    first_id = analytics._session_id
    assert first_id

    analytics._session_id = ""
    analytics.init(True)
    assert analytics._session_id == first_id


def test_session_id_file_created(tmp_session_dir):
    analytics.init(True)
    assert os.path.exists(str(tmp_session_dir / "analytics_id"))
    with open(str(tmp_session_dir / "analytics_id")) as f:
        assert f.read().strip() == analytics._session_id
