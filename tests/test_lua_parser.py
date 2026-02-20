import os
import tempfile
import pytest
from voidstorm_companion.lua_parser import parse_savedvariables

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_savedvariables.lua")


def test_parse_returns_sessions_list():
    sessions = parse_savedvariables(FIXTURE_PATH)
    assert isinstance(sessions, list)
    assert len(sessions) == 2


def test_parse_difference_session_fields():
    sessions = parse_savedvariables(FIXTURE_PATH)
    s = sessions[0]
    assert s["id"] == "1740934800-5432"
    assert s["mode"] == "DIFFERENCE"
    assert s["host"] == "Bp"
    assert s["wager"] == 50000
    assert s["channel"] == "GUILD"
    assert s["startedAt"] == 1740934800
    assert s["endedAt"] == 1740934950


def test_parse_round_players():
    sessions = parse_savedvariables(FIXTURE_PATH)
    players = sessions[0]["rounds"][0]["players"]
    assert len(players) == 2
    assert players[0]["name"] == "Bp"
    assert players[0]["realm"] == "Ravencrest"
    assert players[0]["guild"] == "The Axemen"
    assert players[0]["roll"] == 842531
    assert players[0]["rolled"] is True


def test_parse_deathroll_sequence():
    sessions = parse_savedvariables(FIXTURE_PATH)
    results = sessions[1]["rounds"][0]["results"]
    assert results["winner"] == "Bp"
    assert results["loser"] == "Koiebar"
    seq = results["sequence"]
    assert len(seq) == 3
    assert seq[0]["name"] == "Koiebar"
    assert seq[2]["roll"] == 1


def test_parse_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        parse_savedvariables("/nonexistent/path.lua")


def test_parse_empty_sessions():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambleDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        f.flush()
        sessions = parse_savedvariables(f.name)
        assert sessions == []
    os.unlink(f.name)
