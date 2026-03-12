import os
import tempfile
import pytest
from voidstorm_companion.lua_parser import (
    parse_savedvariables,
    parse_savedvariables_full,
    parse_tournaments,
    parse_achievements,
    parse_leagues,
    parse_challenges,
    parse_audit_log,
)
from voidstorm_companion.api_client import ApiClient, _VALID_MODES

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_savedvariables.lua")

ALL_MODES = {
    "DIFFERENCE", "POT", "DEATHROLL", "ODDEVEN", "ELIMINATION",
    "LOTTERY", "POKER", "DOUBLEORNOTHING", "BLACKJACK", "COINFLIP", "WAR",
    "SLOTS", "ROULETTE", "HOTPOTATO", "STREAKBET", "OVERUNDER",
}


def _sessions():
    return parse_savedvariables(FIXTURE_PATH)


def _by_mode(mode: str):
    return next(s for s in _sessions() if s["mode"] == mode)


# --- Core parsing ---


def test_parse_returns_all_13_modes():
    sessions = _sessions()
    assert len(sessions) == 18
    modes_found = {s["mode"] for s in sessions}
    assert modes_found == ALL_MODES


def test_parse_difference_session_fields():
    s = _sessions()[0]
    assert s["id"] == "1740934800-5432"
    assert s["mode"] == "DIFFERENCE"
    assert s["host"] == "Bp"
    assert s["wager"] == 50000
    assert s["channel"] == "GUILD"
    assert s["startedAt"] == 1740934800
    assert s["endedAt"] == 1740934950


def test_parse_round_players():
    players = _sessions()[0]["rounds"][0]["players"]
    assert len(players) == 2
    assert players[0]["name"] == "Bp"
    assert players[0]["realm"] == "Ravencrest"
    assert players[0]["guild"] == "The Axemen"
    assert players[0]["roll"] == 842531
    assert players[0]["rolled"] is True


def test_parse_deathroll_sequence():
    results = _sessions()[1]["rounds"][0]["results"]
    assert results["winner"] == "Bp"
    assert results["loser"] == "Koiebar"
    seq = results["sequence"]
    assert len(seq) == 3
    assert seq[0]["name"] == "Koiebar"
    assert seq[2]["roll"] == 1


# --- New mode validation (v2.2.0+) ---


def test_poker_hand_preserved():
    s = _by_mode("POKER")
    hand = s["rounds"][0]["pokerHand"]
    assert hand["sb"] == 10
    assert hand["bb"] == 20
    assert "Bp" in hand["holeCards"]
    assert len(hand["community"]) == 5
    assert hand["preflop"][0][0] == "Bp"


def test_double_or_nothing_fields():
    s = _by_mode("DOUBLEORNOTHING")
    r = s["rounds"][0]["results"]
    assert r["winner"] == "Bp"
    assert r["amount"] == 100  # doubled from 50 wager


def test_blackjack_fields():
    s = _by_mode("BLACKJACK")
    r = s["rounds"][0]["results"]
    assert r["winner"] == "Bp"
    assert r["winRoll"] == 19
    assert r["pot"] == 200
    assert r["playerCount"] == 2


def test_coinflip_fields():
    s = _by_mode("COINFLIP")
    r = s["rounds"][0]["results"]
    assert r["winRoll"] in (1, 2)
    assert r["amount"] == 500


def test_war_fields():
    s = _by_mode("WAR")
    r = s["rounds"][0]["results"]
    assert r["winRoll"] == 13  # King
    assert r["amount"] == 250


def test_oddeven_fields():
    s = _by_mode("ODDEVEN")
    r = s["rounds"][0]["results"]
    assert r["totalRoll"] == 117
    assert r["parity"] == "odd"


def test_elimination_fields():
    s = _by_mode("ELIMINATION")
    r = s["rounds"][0]["results"]
    assert r["playerCount"] == 3
    assert len(r["eliminated"]) == 2


def test_lottery_ranges():
    s = _by_mode("LOTTERY")
    lr = s["rounds"][0]["lotteryRanges"]
    assert len(lr) == 2
    assert lr[0]["name"] == "Bp"
    assert lr[0]["start"] == 1


def test_pot_fields():
    s = _by_mode("POT")
    r = s["rounds"][0]["results"]
    assert r["pot"] == 150
    assert r["playerCount"] == 3


# --- Slots mode (Phase 1) ---


def _slots_sessions():
    return [s for s in _sessions() if s["mode"] == "SLOTS"]


def test_slots_mode_in_valid_modes():
    assert "SLOTS" in _VALID_MODES


def test_slots_session_parses_correctly():
    slots = _slots_sessions()
    assert len(slots) == 2
    s = slots[0]
    assert s["id"] == "1740936500-1111"
    assert s["mode"] == "SLOTS"
    assert s["host"] == "Bp"
    r = s["rounds"][0]["results"]
    assert r["reel1"] == "cherry"
    assert r["reel2"] == "cherry"
    assert r["reel3"] == "lemon"
    assert r["jackpot"] is False
    assert r["pot"] == 200
    assert r["winner"] == "Bp"
    assert r["amount"] == 250
    # Check players have bet/payout fields
    players = s["rounds"][0]["players"]
    assert len(players) == 2
    assert players[0]["name"] == "Bp"
    assert players[0]["bet"] == 100
    assert players[0]["payout"] == 250
    assert players[1]["name"] == "Skatten"
    assert players[1]["bet"] == 100
    assert players[1]["payout"] == 0


def test_slots_jackpot_session_parses_correctly():
    slots = _slots_sessions()
    s = slots[1]
    assert s["id"] == "1740936600-2222"
    r = s["rounds"][0]["results"]
    assert r["reel1"] == "seven"
    assert r["reel2"] == "seven"
    assert r["reel3"] == "seven"
    assert r["jackpot"] is True
    assert r["jackpotAmount"] == 50000
    assert r["winner"] == "Skatten"
    assert r["amount"] == 50000


# --- API client validation ---


def test_roulette_session_parses_correctly():
    s = _by_mode("ROULETTE")
    assert s["host"] == "Bp"
    assert s["wager"] == 500
    r = s["rounds"][0]
    assert r["results"]["pocket"] == 14
    assert r["results"]["color"] == "red"
    assert r["results"]["pot"] == 700
    assert len(r["players"]) == 2
    assert r["players"][0]["bet"] == 500
    assert r["players"][0]["payout"] == 1000


def test_roulette_big_win_session_parses_correctly():
    sessions = _sessions()
    roulette_sessions = [s for s in sessions if s["mode"] == "ROULETTE"]
    big_win = roulette_sessions[1]  # second roulette session
    assert big_win["host"] == "Skatten"
    r = big_win["rounds"][0]
    assert r["results"]["pocket"] == 7
    assert r["results"]["amount"] == 35000
    assert r["players"][0]["payout"] == 35000


def test_all_modes_pass_api_validation():
    sessions = _sessions()
    client = ApiClient("http://localhost", "fake-token")
    payload = client.prepare_payload(sessions)
    cleaned = payload["sessions"]
    modes_cleaned = {s["mode"] for s in cleaned}
    assert modes_cleaned == _VALID_MODES
    assert _VALID_MODES == ALL_MODES


def test_poker_hand_survives_payload_cleaning():
    s = _by_mode("POKER")
    client = ApiClient("http://localhost", "fake-token")
    payload = client.prepare_payload([s])
    cleaned_round = payload["sessions"][0]["rounds"][0]
    assert "pokerHand" in cleaned_round


def test_lottery_ranges_survive_payload_cleaning():
    s = _by_mode("LOTTERY")
    client = ApiClient("http://localhost", "fake-token")
    payload = client.prepare_payload([s])
    cleaned_round = payload["sessions"][0]["rounds"][0]
    assert "lotteryRanges" in cleaned_round


# --- Edge cases ---


def test_parse_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        parse_savedvariables("/nonexistent/path.lua")


def test_parse_empty_sessions():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambaDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        f.flush()
        sessions = parse_savedvariables(f.name)
        assert sessions == []
    os.unlink(f.name)


# --- exportedStats parsing (Phase 3) ---


def _exported_stats():
    _, stats, _, _, _, _ = parse_savedvariables_full(FIXTURE_PATH)
    return stats


def test_parse_full_returns_sessions_and_exported_stats():
    sessions, stats, tournaments, achievements, leagues, audit_log = parse_savedvariables_full(FIXTURE_PATH)
    assert len(sessions) == 18
    assert isinstance(stats, dict)
    assert stats != {}


def test_exported_stats_timestamp():
    stats = _exported_stats()
    assert stats["timestamp"] == 1709300000


def test_exported_stats_lifetime_fields():
    lifetime = _exported_stats()["lifetime"]
    assert lifetime["wins"] == 50
    assert lifetime["losses"] == 30
    assert lifetime["totalWagered"] == 500000
    assert lifetime["totalWon"] == 620000
    assert lifetime["netProfit"] == 120000
    assert lifetime["sessions"] == 80
    assert lifetime["playtime"] == 36000


def test_exported_stats_mode_breakdown_keys():
    breakdown = _exported_stats()["modeBreakdown"]
    assert set(breakdown.keys()) == {"POKER", "SLOTS", "ROULETTE"}


def test_exported_stats_mode_breakdown_poker():
    poker = _exported_stats()["modeBreakdown"]["POKER"]
    assert poker["wins"] == 20
    assert poker["losses"] == 10
    assert poker["wagered"] == 200000
    assert poker["won"] == 280000
    assert poker["played"] == 30


def test_exported_stats_mode_breakdown_slots():
    slots = _exported_stats()["modeBreakdown"]["SLOTS"]
    assert slots["wins"] == 15
    assert slots["losses"] == 12
    assert slots["played"] == 27


def test_exported_stats_mode_breakdown_roulette():
    roulette = _exported_stats()["modeBreakdown"]["ROULETTE"]
    assert roulette["wins"] == 15
    assert roulette["losses"] == 8
    assert roulette["played"] == 23


def test_exported_stats_recent_sessions_count():
    recent = _exported_stats()["recentSessions"]
    assert len(recent) == 2


def test_exported_stats_recent_sessions_first_entry():
    first = _exported_stats()["recentSessions"][0]
    assert first["mode"] == "POKER"
    assert first["result"] == "win"
    assert first["netProfit"] == 5000
    assert first["timestamp"] == 1709299000


def test_exported_stats_recent_sessions_second_entry():
    second = _exported_stats()["recentSessions"][1]
    assert second["mode"] == "SLOTS"
    assert second["result"] == "loss"
    assert second["netProfit"] == -2000


def test_exported_stats_rivals_count():
    rivals = _exported_stats()["rivals"]
    assert len(rivals) == 2


def test_exported_stats_rival_opponent1():
    rival = _exported_stats()["rivals"][0]
    assert rival["name"] == "Opponent1"
    assert rival["wins"] == 10
    assert rival["losses"] == 5
    assert rival["netGold"] == 30000


def test_exported_stats_rival_opponent2():
    rival = _exported_stats()["rivals"][1]
    assert rival["name"] == "Opponent2"
    assert rival["wins"] == 3
    assert rival["losses"] == 8
    assert rival["netGold"] == -15000


def test_parse_full_no_exported_stats_returns_empty_dict():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambaDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        fname = f.name
    try:
        _, stats, _, _, _, _ = parse_savedvariables_full(fname)
        assert stats == {}
    finally:
        os.unlink(fname)


def test_parse_savedvariables_backward_compat():
    """parse_savedvariables must still return only sessions (no regression)."""
    sessions = parse_savedvariables(FIXTURE_PATH)
    assert len(sessions) == 18


# ---------------------------------------------------------------------------
# Tournament parsing (Phase 4)
# ---------------------------------------------------------------------------


def _tournaments():
    _, _, tournaments, _, _, _ = parse_savedvariables_full(FIXTURE_PATH)
    return tournaments


def test_parse_full_returns_tournaments_list():
    _, _, tournaments, _, _, _ = parse_savedvariables_full(FIXTURE_PATH)
    assert isinstance(tournaments, list)
    assert len(tournaments) == 2


def test_parse_tournaments_sorted_by_start_time():
    tournaments = _tournaments()
    start_times = [t["startTime"] for t in tournaments]
    assert start_times == sorted(start_times)


def test_parse_tournament_single_elim_fields():
    tournaments = _tournaments()
    t = next(t for t in tournaments if t["id"] == "T1709234567")
    assert t["name"] == "Friday Night Poker"
    assert t["mode"] == "POKER"
    assert t["format"] == "SINGLE_ELIM"
    assert t["buyIn"] == 500
    assert t["maxPlayers"] == 8
    assert t["prizePool"] == 4000
    assert t["status"] == "COMPLETE"
    assert t["startTime"] == 1709234567
    assert t["endTime"] == 1709238167


def test_parse_tournament_single_elim_players():
    t = next(t for t in _tournaments() if t["id"] == "T1709234567")
    assert len(t["players"]) == 8
    assert "PlayerOne" in t["players"]
    assert "PlayerEight" in t["players"]


def test_parse_tournament_single_elim_prizes():
    t = next(t for t in _tournaments() if t["id"] == "T1709234567")
    prizes = t["prizes"]
    assert len(prizes) == 4
    first = next(p for p in prizes if p["place"] == 1)
    assert first["player"] == "PlayerOne"
    assert first["amount"] == 2400
    second = next(p for p in prizes if p["place"] == 2)
    assert second["player"] == "PlayerFive"
    assert second["amount"] == 1000


def test_parse_tournament_single_elim_bracket():
    t = next(t for t in _tournaments() if t["id"] == "T1709234567")
    bracket = t["bracket"]
    assert "round1" in bracket
    assert "round2" in bracket
    assert "finals" in bracket
    assert len(bracket["round1"]) == 4
    assert len(bracket["finals"]) == 1
    finals_match = bracket["finals"][0]
    assert finals_match["winner"] == "PlayerOne"
    assert finals_match["loser"] == "PlayerFive"


def test_parse_tournament_round_robin_fields():
    t = next(t for t in _tournaments() if t["id"] == "T1709300000")
    assert t["name"] == "Saturday Round Robin"
    assert t["mode"] == "DEATHROLL"
    assert t["format"] == "ROUND_ROBIN"
    assert t["buyIn"] == 200
    assert t["maxPlayers"] == 4
    assert t["prizePool"] == 800


def test_parse_tournament_round_robin_players():
    t = next(t for t in _tournaments() if t["id"] == "T1709300000")
    assert len(t["players"]) == 4
    assert "Alpha" in t["players"]
    assert "Delta" in t["players"]


def test_parse_tournament_prizes_sorted_by_place():
    t = next(t for t in _tournaments() if t["id"] == "T1709234567")
    places = [p["place"] for p in t["prizes"]]
    assert places == sorted(places)


def test_parse_tournaments_from_data_dict():
    """parse_tournaments() works directly on a data dict."""
    data = {
        "tournaments": {
            "TX001": {
                "id": "TX001",
                "name": "Test Tourney",
                "mode": "POKER",
                "format": "SINGLE_ELIM",
                "buyIn": 100,
                "maxPlayers": 4,
                "players": {"1": "A", "2": "B", "3": "C", "4": "D"},
                "bracket": {},
                "prizePool": 400,
                "prizes": {
                    "1": {"player": "A", "amount": 240, "place": 1},
                    "2": {"player": "B", "amount": 100, "place": 2},
                },
                "status": "COMPLETE",
                "startTime": 1700000000,
                "endTime": 1700003600,
            }
        }
    }
    result = parse_tournaments(data)
    assert len(result) == 1
    assert result[0]["id"] == "TX001"
    assert result[0]["name"] == "Test Tourney"
    assert len(result[0]["players"]) == 4
    assert len(result[0]["prizes"]) == 2


def test_parse_tournaments_empty_when_no_tournaments_key():
    data = {"sessions": {}, "settings": {}}
    result = parse_tournaments(data)
    assert result == []


def test_parse_tournaments_empty_when_tournaments_not_dict():
    data = {"tournaments": []}
    result = parse_tournaments(data)
    assert result == []


def test_parse_full_no_tournaments_returns_empty_list():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambaDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        fname = f.name
    try:
        _, _, tournaments, _, _, _ = parse_savedvariables_full(fname)
        assert tournaments == []
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Achievement parsing (Phase 4)
# ---------------------------------------------------------------------------


def _achievements():
    _, _, _, achievements, _, _ = parse_savedvariables_full(FIXTURE_PATH)
    return achievements


def test_parse_full_returns_achievements_dict():
    _, _, _, achievements, _, _ = parse_savedvariables_full(FIXTURE_PATH)
    assert isinstance(achievements, dict)
    assert len(achievements) == 3


def test_parse_achievements_keys():
    achievements = _achievements()
    assert "FIRST_BLOOD" in achievements
    assert "CENTURY_CLUB" in achievements
    assert "HIGH_ROLLER" in achievements


def test_parse_achievement_first_blood():
    ach = _achievements()["FIRST_BLOOD"]
    assert ach["unlockedAt"] == 1709234000


def test_parse_achievement_century_club():
    ach = _achievements()["CENTURY_CLUB"]
    assert ach["unlockedAt"] == 1709235000


def test_parse_achievement_high_roller():
    ach = _achievements()["HIGH_ROLLER"]
    assert ach["unlockedAt"] == 1709236000


def test_parse_achievements_from_data_dict():
    """parse_achievements() works directly on a data dict."""
    data = {
        "achievements": {
            "FIRST_BLOOD": {"unlockedAt": 1700000001},
            "ALL_IN": {"unlockedAt": 1700000002},
        }
    }
    result = parse_achievements(data)
    assert len(result) == 2
    assert result["FIRST_BLOOD"]["unlockedAt"] == 1700000001
    assert result["ALL_IN"]["unlockedAt"] == 1700000002


def test_parse_achievements_empty_when_no_key():
    data = {"sessions": {}}
    result = parse_achievements(data)
    assert result == {}


def test_parse_achievements_empty_when_not_dict():
    data = {"achievements": []}
    result = parse_achievements(data)
    assert result == {}


def test_parse_full_no_achievements_returns_empty_dict():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambaDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        fname = f.name
    try:
        _, _, _, achievements, _, _ = parse_savedvariables_full(fname)
        assert achievements == {}
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Backward compatibility — old SavedVars without tournament/achievement data
# ---------------------------------------------------------------------------


def test_old_savedvars_without_tournaments_parses_ok():
    """Files without the tournaments block must parse cleanly."""
    lua_content = '''VoidstormGambaDB = {
["sessions"] = {
    {
        ["id"] = "old-001",
        ["mode"] = "DIFFERENCE",
        ["host"] = "Bp",
        ["wager"] = 1000,
        ["startedAt"] = 1700000000,
        ["endedAt"] = 1700000060,
        ["rounds"] = {
            {
                ["number"] = 1,
                ["mode"] = "DIFFERENCE",
                ["time"] = 1700000050,
                ["players"] = {
                    { ["name"] = "Bp", ["roll"] = 500, ["rolled"] = true },
                    { ["name"] = "X", ["roll"] = 300, ["rolled"] = true },
                },
                ["results"] = { ["winner"] = "Bp", ["summary"] = "Bp wins" },
            },
        },
    },
},
["settings"] = {},
}'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write(lua_content)
        fname = f.name
    try:
        sessions, stats, tournaments, achievements, leagues, audit_log = parse_savedvariables_full(fname)
        assert len(sessions) == 1
        assert stats == {}
        assert tournaments == []
        assert achievements == {}
        assert leagues == []
        assert audit_log == []
    finally:
        os.unlink(fname)


def test_old_savedvars_without_achievements_parses_ok():
    """Files with tournaments but no achievements must parse cleanly."""
    lua_content = '''VoidstormGambaDB = {
["sessions"] = {},
["tournaments"] = {
    ["T001"] = {
        ["id"] = "T001",
        ["name"] = "Old Tourney",
        ["mode"] = "POKER",
        ["format"] = "SINGLE_ELIM",
        ["buyIn"] = 100,
        ["maxPlayers"] = 2,
        ["players"] = { "A", "B" },
        ["bracket"] = {},
        ["prizePool"] = 200,
        ["prizes"] = { { ["player"] = "A", ["amount"] = 200, ["place"] = 1 } },
        ["status"] = "COMPLETE",
        ["startTime"] = 1700000000,
        ["endTime"] = 1700003600,
    },
},
}'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write(lua_content)
        fname = f.name
    try:
        sessions, stats, tournaments, achievements, leagues, audit_log = parse_savedvariables_full(fname)
        assert sessions == []
        assert tournaments == [{"id": "T001", "name": "Old Tourney", "mode": "POKER",
                                "format": "SINGLE_ELIM", "buyIn": 100, "maxPlayers": 2,
                                "players": ["A", "B"], "bracket": {}, "prizePool": 200,
                                "prizes": [{"player": "A", "amount": 200, "place": 1}],
                                "status": "COMPLETE", "startTime": 1700000000, "endTime": 1700003600}]
        assert achievements == {}
        assert leagues == []
        assert audit_log == []
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Phase 5: 6-tuple return value
# ---------------------------------------------------------------------------


def test_parse_savedvariables_full_returns_6_tuple():
    """parse_savedvariables_full must return a 6-tuple."""
    result = parse_savedvariables_full(FIXTURE_PATH)
    assert len(result) == 6


def test_parse_savedvariables_full_6tuple_types():
    sessions, stats, tournaments, achievements, leagues, audit_log = parse_savedvariables_full(FIXTURE_PATH)
    assert isinstance(sessions, list)
    assert isinstance(stats, dict)
    assert isinstance(tournaments, list)
    assert isinstance(achievements, dict)
    assert isinstance(leagues, list)
    assert isinstance(audit_log, list)


# ---------------------------------------------------------------------------
# Phase 5: League parsing
# ---------------------------------------------------------------------------


def _leagues():
    _, _, _, _, leagues, _ = parse_savedvariables_full(FIXTURE_PATH)
    return leagues


def test_parse_full_returns_leagues_list():
    _, _, _, _, leagues, _ = parse_savedvariables_full(FIXTURE_PATH)
    assert isinstance(leagues, list)
    assert len(leagues) == 1


def test_parse_league_name():
    lg = _leagues()[0]
    assert lg["name"] == "Friday Night League"


def test_parse_league_guild():
    lg = _leagues()[0]
    assert lg["guild"] == "Voidstorm"


def test_parse_league_season():
    lg = _leagues()[0]
    assert lg["season"] == 3


def test_parse_league_started_at():
    lg = _leagues()[0]
    assert lg["startedAt"] == 1709234567


def test_parse_league_standings_count():
    lg = _leagues()[0]
    assert len(lg["standings"]) == 3


def test_parse_league_standing_first_place():
    standing = _leagues()[0]["standings"][0]
    assert standing["name"] == "Player1"
    assert standing["points"] == 15
    assert standing["wins"] == 5
    assert standing["losses"] == 2
    assert standing["draws"] == 0
    assert standing["netGold"] == 12500


def test_parse_league_standing_second_place():
    standing = _leagues()[0]["standings"][1]
    assert standing["name"] == "Player2"
    assert standing["points"] == 12
    assert standing["netGold"] == 8200


def test_parse_league_standing_third_place():
    standing = _leagues()[0]["standings"][2]
    assert standing["name"] == "Player3"
    assert standing["points"] == 9
    assert standing["netGold"] == -3000


def test_parse_league_history_count():
    lg = _leagues()[0]
    assert len(lg["history"]) == 1


def test_parse_league_history_entry():
    hist = _leagues()[0]["history"][0]
    assert hist["season"] == 1
    assert hist["winner"] == "Player3"


def test_parse_league_key_preserved():
    lg = _leagues()[0]
    assert lg["leagueKey"] == "GuildLeague1"


def test_parse_leagues_from_data_dict():
    """parse_leagues() works directly on a data dict."""
    data = {
        "leagues": {
            "TestLeague": {
                "name": "Test League",
                "guild": "Testers",
                "season": 1,
                "standings": {
                    1: {"name": "Alpha", "points": 10, "wins": 3, "losses": 1, "draws": 0, "netGold": 5000},
                },
                "history": {},
                "startedAt": 1700000000,
            }
        }
    }
    result = parse_leagues(data)
    assert len(result) == 1
    assert result[0]["name"] == "Test League"
    assert result[0]["guild"] == "Testers"
    assert result[0]["season"] == 1
    assert len(result[0]["standings"]) == 1
    assert result[0]["standings"][0]["name"] == "Alpha"


def test_parse_leagues_empty_when_no_leagues_key():
    data = {"sessions": {}}
    assert parse_leagues(data) == []


def test_parse_leagues_empty_when_leagues_not_dict():
    data = {"leagues": []}
    assert parse_leagues(data) == []


def test_parse_leagues_missing_fields_use_defaults():
    data = {
        "leagues": {
            "Minimal": {
                "name": "Minimal League",
            }
        }
    }
    result = parse_leagues(data)
    assert len(result) == 1
    lg = result[0]
    assert lg["name"] == "Minimal League"
    assert lg["guild"] == ""
    assert lg["season"] == 0
    assert lg["standings"] == []
    assert lg["history"] == []
    assert lg["startedAt"] == 0


def test_parse_full_no_leagues_returns_empty_list():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambaDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        fname = f.name
    try:
        _, _, _, _, leagues, _ = parse_savedvariables_full(fname)
        assert leagues == []
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Phase 5: Challenge parsing
# ---------------------------------------------------------------------------


def _challenges():
    from slpp import slpp as _lua
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    eq_pos = content.index("=")
    data = _lua.decode(content[eq_pos + 1:].strip())
    return parse_challenges(data)


def test_parse_challenges_count():
    challenges = _challenges()
    assert len(challenges) == 3


def test_parse_challenge_challenger_win():
    ch = _challenges()[0]
    assert ch["challenger"] == "Player1"
    assert ch["opponent"] == "Player2"
    assert ch["mode"] == "DEATHROLL"
    assert ch["wager"] == 5000
    assert ch["result"] == "challenger_win"
    assert ch["timestamp"] == 1709234567


def test_parse_challenge_opponent_win():
    ch = _challenges()[1]
    assert ch["result"] == "opponent_win"
    assert ch["mode"] == "COINFLIP"
    assert ch["wager"] == 2500


def test_parse_challenge_draw():
    ch = _challenges()[2]
    assert ch["result"] == "draw"
    assert ch["mode"] == "BLACKJACK"
    assert ch["wager"] == 10000


def test_parse_challenges_from_data_dict():
    data = {
        "challenges": {
            1: {"challenger": "A", "opponent": "B", "mode": "WAR", "wager": 100, "result": "challenger_win", "timestamp": 1700000001},
            2: {"challenger": "B", "opponent": "C", "mode": "COINFLIP", "wager": 200, "result": "opponent_win", "timestamp": 1700000002},
        }
    }
    result = parse_challenges(data)
    assert len(result) == 2
    assert result[0]["challenger"] == "A"
    assert result[1]["mode"] == "COINFLIP"


def test_parse_challenges_empty_when_no_key():
    data = {"sessions": {}}
    assert parse_challenges(data) == []


def test_parse_challenges_empty_when_wrong_type():
    data = {"challenges": "not-a-table"}
    assert parse_challenges(data) == []


def test_parse_challenges_missing_fields_use_defaults():
    data = {"challenges": {1: {"challenger": "X"}}}
    result = parse_challenges(data)
    assert len(result) == 1
    ch = result[0]
    assert ch["challenger"] == "X"
    assert ch["opponent"] == ""
    assert ch["mode"] == ""
    assert ch["wager"] == 0
    assert ch["result"] == ""
    assert ch["timestamp"] == 0


# ---------------------------------------------------------------------------
# Phase 5: Audit log parsing
# ---------------------------------------------------------------------------


def _audit_log_entries():
    from slpp import slpp as _lua
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    eq_pos = content.index("=")
    data = _lua.decode(content[eq_pos + 1:].strip())
    return parse_audit_log(data)


def test_parse_audit_log_count():
    entries = _audit_log_entries()
    assert len(entries) == 5


def test_parse_audit_game_start_entry():
    entry = _audit_log_entries()[0]
    assert entry["eventType"] == "GAME_START"
    assert entry["mode"] == "DEATHROLL"
    assert entry["timestamp"] == 1709234567
    assert "Player1" in entry["players"]
    assert "Player2" in entry["players"]
    assert entry["amounts"] == [5000]
    assert entry["severity"] == "INFO"


def test_parse_audit_bet_placed_entry():
    entry = _audit_log_entries()[1]
    assert entry["eventType"] == "BET_PLACED"
    assert entry["players"] == ["Player1"]
    assert entry["severity"] == "INFO"


def test_parse_audit_game_result_entry():
    entry = _audit_log_entries()[2]
    assert entry["eventType"] == "GAME_RESULT"
    assert entry["result"] == "Player1"


def test_parse_audit_payout_entry():
    entry = _audit_log_entries()[3]
    assert entry["eventType"] == "PAYOUT"
    assert entry["result"] == "Player1"


def test_parse_audit_suspicious_pattern_entry():
    entry = _audit_log_entries()[4]
    assert entry["eventType"] == "SUSPICIOUS_PATTERN"
    assert entry["severity"] == "WARN"
    assert entry["players"] == ["Player2"]


def test_parse_audit_log_from_data_dict():
    data = {
        "auditLog": {
            1: {
                "timestamp": 1700000001, "eventType": "GAME_START",
                "players": {1: "A", 2: "B"}, "mode": "SLOTS",
                "amounts": {1: 100}, "result": "", "severity": "INFO",
            },
            2: {
                "timestamp": 1700000002, "eventType": "PAYOUT",
                "players": {1: "A"}, "mode": "SLOTS",
                "amounts": {1: 200}, "result": "A", "severity": "INFO",
            },
        }
    }
    result = parse_audit_log(data)
    assert len(result) == 2
    assert result[0]["eventType"] == "GAME_START"
    assert result[0]["players"] == ["A", "B"]
    assert result[0]["amounts"] == [100]
    assert result[1]["eventType"] == "PAYOUT"


def test_parse_audit_log_empty_when_no_key():
    data = {"sessions": {}}
    assert parse_audit_log(data) == []


def test_parse_audit_log_empty_when_wrong_type():
    data = {"auditLog": "not-a-table"}
    assert parse_audit_log(data) == []


def test_parse_audit_log_severity_levels():
    data = {
        "auditLog": {
            1: {"timestamp": 1, "eventType": "X", "players": {}, "mode": "", "amounts": {}, "result": "", "severity": "ERROR"},
        }
    }
    result = parse_audit_log(data)
    assert result[0]["severity"] == "ERROR"


def test_parse_audit_log_missing_fields_use_defaults():
    data = {"auditLog": {1: {"eventType": "GAME_START"}}}
    result = parse_audit_log(data)
    assert len(result) == 1
    entry = result[0]
    assert entry["timestamp"] == 0
    assert entry["players"] == []
    assert entry["amounts"] == []
    assert entry["mode"] == ""
    assert entry["result"] == ""
    assert entry["severity"] == "INFO"


def test_parse_full_no_audit_log_returns_empty_list():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write('VoidstormGambaDB = {\n["sessions"] = {},\n["settings"] = {},\n}')
        fname = f.name
    try:
        _, _, _, _, _, audit_log = parse_savedvariables_full(fname)
        assert audit_log == []
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Phase 5: parse_savedvariables backward compatibility (6-tuple)
# ---------------------------------------------------------------------------


def test_parse_savedvariables_still_returns_sessions_only():
    """parse_savedvariables() must still return just the list of sessions."""
    sessions = parse_savedvariables(FIXTURE_PATH)
    assert isinstance(sessions, list)
    assert len(sessions) == 18


def test_old_savedvars_without_leagues_challenges_auditlog():
    """Old files without the new Phase 5 blocks parse cleanly returning empties."""
    lua_content = '''VoidstormGambaDB = {
["sessions"] = {
    {
        ["id"] = "legacy-001",
        ["mode"] = "DEATHROLL",
        ["host"] = "Bp",
        ["wager"] = 1000,
        ["startedAt"] = 1700000000,
        ["endedAt"] = 1700000060,
        ["rounds"] = {
            {
                ["number"] = 1,
                ["mode"] = "DEATHROLL",
                ["time"] = 1700000050,
                ["players"] = {
                    { ["name"] = "Bp", ["roll"] = nil, ["rolled"] = true },
                    { ["name"] = "X", ["roll"] = nil, ["rolled"] = true },
                },
                ["results"] = { ["winner"] = "Bp", ["summary"] = "Bp wins" },
            },
        },
    },
},
["settings"] = {},
}'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
        f.write(lua_content)
        fname = f.name
    try:
        sessions, stats, tournaments, achievements, leagues, audit_log = parse_savedvariables_full(fname)
        assert len(sessions) == 1
        assert leagues == []
        assert audit_log == []
    finally:
        os.unlink(fname)

