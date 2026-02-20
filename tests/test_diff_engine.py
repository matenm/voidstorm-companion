import os
import tempfile
import pytest
from voidstorm_companion.diff_engine import DiffEngine


@pytest.fixture
def tmp_state_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_new_engine_has_empty_state(tmp_state_file):
    os.unlink(tmp_state_file)
    engine = DiffEngine(tmp_state_file)
    assert engine.uploaded_ids == set()


def test_filter_new_sessions(tmp_state_file):
    os.unlink(tmp_state_file)
    engine = DiffEngine(tmp_state_file)
    sessions = [
        {"id": "aaa-111", "mode": "DIFFERENCE"},
        {"id": "bbb-222", "mode": "POT"},
        {"id": "ccc-333", "mode": "DEATHROLL"},
    ]
    new = engine.filter_new(sessions)
    assert len(new) == 3


def test_mark_uploaded_persists(tmp_state_file):
    os.unlink(tmp_state_file)
    engine = DiffEngine(tmp_state_file)
    engine.mark_uploaded(["aaa-111", "bbb-222"])
    engine2 = DiffEngine(tmp_state_file)
    assert "aaa-111" in engine2.uploaded_ids
    assert "bbb-222" in engine2.uploaded_ids


def test_filter_excludes_uploaded(tmp_state_file):
    os.unlink(tmp_state_file)
    engine = DiffEngine(tmp_state_file)
    engine.mark_uploaded(["aaa-111"])
    sessions = [
        {"id": "aaa-111", "mode": "DIFFERENCE"},
        {"id": "bbb-222", "mode": "POT"},
    ]
    new = engine.filter_new(sessions)
    assert len(new) == 1
    assert new[0]["id"] == "bbb-222"
