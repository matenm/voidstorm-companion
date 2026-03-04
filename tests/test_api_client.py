from unittest.mock import patch, MagicMock
import pytest
from voidstorm_companion.api_client import ApiClient, AuthError


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _minimal_session(**overrides):
    """Return a minimal valid session dict for use in upload tests."""
    base = {
        "id": "aaa-001",
        "mode": "DIFFERENCE",
        "host": "Bp",
        "wager": 100,
        "startedAt": 1740000000,
        "rounds": [
            {
                "number": 1,
                "mode": "DIFFERENCE",
                "time": 1740000001,
                "players": [
                    {"name": "A", "roll": 1, "rolled": True},
                    {"name": "B", "roll": 2, "rolled": True},
                ],
                "results": {},
            }
        ],
    }
    base.update(overrides)
    return base


def _sample_player_stats():
    return {
        "playerName": "Bp",
        "realm": "Ravencrest",
        "lifetime": {
            "wins": 50,
            "losses": 30,
            "totalWagered": 500000,
            "totalWon": 620000,
            "netProfit": 120000,
            "sessions": 80,
            "playtime": 36000,
        },
        "modeBreakdown": {
            "POKER": {"wins": 20, "losses": 10, "wagered": 200000, "won": 280000, "played": 30},
        },
        "recentSessions": [
            {"mode": "POKER", "result": "win", "netProfit": 5000, "timestamp": 1709299000},
        ],
        "rivals": [
            {"name": "Opponent1", "wins": 10, "losses": 5, "netGold": 30000},
        ],
    }


def test_prepare_payload_converts_sessions():
    client = ApiClient(api_url="http://localhost", token="test-token")
    sessions = [
        {
            "id": "aaa-111",
            "mode": "DIFFERENCE",
            "host": "Bp",
            "wager": 50000,
            "channel": "GUILD",
            "startedAt": 1740934800,
            "endedAt": 1740934950,
            "keyword": "vsg",
            "rounds": [
                {
                    "number": 1,
                    "mode": "DIFFERENCE",
                    "time": 1740934850,
                    "players": [
                        {"name": "Bp", "realm": "Ravencrest", "guild": "The Axemen",
                         "guildRank": "Officer", "roll": 842531, "rolled": True},
                        {"name": "Skatten", "realm": "Ravencrest", "guild": "The Axemen",
                         "guildRank": "Raider", "roll": 312044, "rolled": True},
                    ],
                    "results": {"winner": "Bp", "loser": "Skatten", "amount": 50000},
                },
            ],
        },
    ]
    payload = client.prepare_payload(sessions)
    assert "sessions" in payload
    assert len(payload["sessions"]) == 1
    assert "keyword" not in payload["sessions"][0]
    p = payload["sessions"][0]["rounds"][0]["players"][0]
    assert p["guild"] == "The Axemen"
    assert p["realm"] == "Ravencrest"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0, "errors": []}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload([{"id": "aaa", "mode": "DIFFERENCE", "host": "Bp",
                             "wager": 100, "startedAt": 1740000000,
                             "rounds": [{"number": 1, "mode": "DIFFERENCE",
                                         "time": 1740000001,
                                         "players": [
                                             {"name": "A", "roll": 1, "rolled": True},
                                             {"name": "B", "roll": 2, "rolled": True},
                                         ],
                                         "results": {}}]}])
    assert result["imported"] == 1
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "Bearer test-token" in call_kwargs.kwargs.get("headers", {}).get("Authorization", "")


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_unauthorized(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": "Unauthorized"}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="bad-token")
    with pytest.raises(AuthError):
        client.upload([{"id": "aaa", "mode": "DIFFERENCE", "host": "Bp",
                        "wager": 100, "startedAt": 1740000000,
                        "rounds": [{"number": 1, "mode": "DIFFERENCE",
                                    "time": 1740000001,
                                    "players": [
                                        {"name": "A", "roll": 1, "rolled": True},
                                        {"name": "B", "roll": 2, "rolled": True},
                                    ],
                                    "results": {}}]}])


# ---------------------------------------------------------------------------
# playerStats in upload payload (Phase 3)
# ---------------------------------------------------------------------------


def test_prepare_payload_without_player_stats_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()])
    assert "playerStats" not in payload


def test_prepare_payload_with_player_stats_includes_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    payload = client.prepare_payload([_minimal_session()], player_stats=ps)
    assert "playerStats" in payload
    assert payload["playerStats"]["playerName"] == "Bp"
    assert payload["playerStats"]["realm"] == "Ravencrest"


def test_prepare_payload_player_stats_lifetime_preserved():
    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    payload = client.prepare_payload([_minimal_session()], player_stats=ps)
    lifetime = payload["playerStats"]["lifetime"]
    assert lifetime["wins"] == 50
    assert lifetime["losses"] == 30
    assert lifetime["netProfit"] == 120000


def test_prepare_payload_player_stats_mode_breakdown_preserved():
    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    payload = client.prepare_payload([_minimal_session()], player_stats=ps)
    breakdown = payload["playerStats"]["modeBreakdown"]
    assert "POKER" in breakdown
    assert breakdown["POKER"]["wins"] == 20


def test_prepare_payload_player_stats_recent_sessions_preserved():
    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    payload = client.prepare_payload([_minimal_session()], player_stats=ps)
    recent = payload["playerStats"]["recentSessions"]
    assert len(recent) == 1
    assert recent[0]["mode"] == "POKER"
    assert recent[0]["result"] == "win"


def test_prepare_payload_player_stats_rivals_preserved():
    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    payload = client.prepare_payload([_minimal_session()], player_stats=ps)
    rivals = payload["playerStats"]["rivals"]
    assert len(rivals) == 1
    assert rivals[0]["name"] == "Opponent1"


def test_prepare_payload_none_player_stats_omits_key():
    """Explicitly passing None must not include playerStats key."""
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], player_stats=None)
    assert "playerStats" not in payload


def test_prepare_payload_empty_player_stats_omits_key():
    """Empty dict is falsy — playerStats key must be omitted."""
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], player_stats={})
    assert "playerStats" not in payload


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_with_player_stats_sends_in_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    client.upload([_minimal_session()], player_stats=ps)

    mock_post.assert_called_once()
    sent_json = mock_post.call_args.kwargs["json"]
    assert "playerStats" in sent_json
    assert sent_json["playerStats"]["playerName"] == "Bp"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_without_player_stats_omits_from_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload([_minimal_session()])

    sent_json = mock_post.call_args.kwargs["json"]
    assert "playerStats" not in sent_json


# ---------------------------------------------------------------------------
# Tournaments in upload payload (Phase 4)
# ---------------------------------------------------------------------------


def _sample_tournament():
    return {
        "id": "T1709234567",
        "name": "Friday Night Poker",
        "mode": "POKER",
        "format": "SINGLE_ELIM",
        "buyIn": 500,
        "maxPlayers": 8,
        "players": ["PlayerOne", "PlayerTwo"],
        "bracket": {},
        "prizePool": 1000,
        "prizes": [
            {"player": "PlayerOne", "amount": 700, "place": 1},
            {"player": "PlayerTwo", "amount": 300, "place": 2},
        ],
        "status": "COMPLETE",
        "startTime": 1709234567,
        "endTime": 1709238167,
    }


def _sample_achievements():
    return {
        "FIRST_BLOOD": {"unlockedAt": 1709234000},
        "HIGH_ROLLER": {"unlockedAt": 1709236000},
    }


def test_prepare_payload_without_tournaments_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()])
    assert "tournaments" not in payload


def test_prepare_payload_with_tournaments_includes_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    tournaments = [_sample_tournament()]
    payload = client.prepare_payload([_minimal_session()], tournaments=tournaments)
    assert "tournaments" in payload
    assert len(payload["tournaments"]) == 1
    assert payload["tournaments"][0]["id"] == "T1709234567"


def test_prepare_payload_tournaments_data_preserved():
    client = ApiClient(api_url="http://localhost", token="test-token")
    tournaments = [_sample_tournament()]
    payload = client.prepare_payload([_minimal_session()], tournaments=tournaments)
    t = payload["tournaments"][0]
    assert t["name"] == "Friday Night Poker"
    assert t["mode"] == "POKER"
    assert t["format"] == "SINGLE_ELIM"
    assert t["buyIn"] == 500
    assert t["prizePool"] == 1000
    assert len(t["prizes"]) == 2


def test_prepare_payload_none_tournaments_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], tournaments=None)
    assert "tournaments" not in payload


def test_prepare_payload_empty_tournaments_list_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], tournaments=[])
    assert "tournaments" not in payload


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_with_tournaments_sends_in_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    tournaments = [_sample_tournament()]
    client.upload([_minimal_session()], tournaments=tournaments)

    mock_post.assert_called_once()
    sent_json = mock_post.call_args.kwargs["json"]
    assert "tournaments" in sent_json
    assert sent_json["tournaments"][0]["id"] == "T1709234567"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_without_tournaments_omits_from_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload([_minimal_session()])

    sent_json = mock_post.call_args.kwargs["json"]
    assert "tournaments" not in sent_json


# ---------------------------------------------------------------------------
# Achievements in upload payload (Phase 4)
# ---------------------------------------------------------------------------


def test_prepare_payload_without_achievements_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()])
    assert "achievements" not in payload


def test_prepare_payload_with_achievements_includes_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    achievements = _sample_achievements()
    payload = client.prepare_payload([_minimal_session()], achievements=achievements)
    assert "achievements" in payload
    assert "FIRST_BLOOD" in payload["achievements"]
    assert "HIGH_ROLLER" in payload["achievements"]


def test_prepare_payload_achievements_data_preserved():
    client = ApiClient(api_url="http://localhost", token="test-token")
    achievements = _sample_achievements()
    payload = client.prepare_payload([_minimal_session()], achievements=achievements)
    assert payload["achievements"]["FIRST_BLOOD"]["unlockedAt"] == 1709234000
    assert payload["achievements"]["HIGH_ROLLER"]["unlockedAt"] == 1709236000


def test_prepare_payload_none_achievements_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], achievements=None)
    assert "achievements" not in payload


def test_prepare_payload_empty_achievements_dict_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], achievements={})
    assert "achievements" not in payload


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_with_achievements_sends_in_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    achievements = _sample_achievements()
    client.upload([_minimal_session()], achievements=achievements)

    mock_post.assert_called_once()
    sent_json = mock_post.call_args.kwargs["json"]
    assert "achievements" in sent_json
    assert "FIRST_BLOOD" in sent_json["achievements"]


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_without_achievements_omits_from_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload([_minimal_session()])

    sent_json = mock_post.call_args.kwargs["json"]
    assert "achievements" not in sent_json


def test_prepare_payload_all_fields_together():
    """All optional payload fields can be included simultaneously."""
    client = ApiClient(api_url="http://localhost", token="test-token")
    ps = _sample_player_stats()
    tournaments = [_sample_tournament()]
    achievements = _sample_achievements()
    payload = client.prepare_payload(
        [_minimal_session()],
        player_stats=ps,
        tournaments=tournaments,
        achievements=achievements,
    )
    assert "sessions" in payload
    assert "playerStats" in payload
    assert "tournaments" in payload
    assert "achievements" in payload


# ---------------------------------------------------------------------------
# upload_tournament method (Phase 4)
# ---------------------------------------------------------------------------


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_posts_to_correct_endpoint(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"status": "recorded"}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload_tournament(_sample_tournament())

    mock_post.assert_called_once()
    url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url", "")
    assert "/api/v1/gambling/tournaments/T1709234567/result" in url


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_sends_tournament_data_as_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    t = _sample_tournament()
    client.upload_tournament(t)

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["id"] == "T1709234567"
    assert sent_json["name"] == "Friday Night Poker"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_includes_auth_header(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="my-secret-token")
    client.upload_tournament(_sample_tournament())

    headers = mock_post.call_args.kwargs.get("headers", {})
    assert "Bearer my-secret-token" in headers.get("Authorization", "")


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_returns_data_unwrapped(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"status": "recorded", "id": "T1709234567"}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload_tournament(_sample_tournament())
    assert result["status"] == "recorded"
    assert result["id"] == "T1709234567"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_returns_raw_when_no_data_envelope(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload_tournament(_sample_tournament())
    assert result["status"] == "ok"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_raises_auth_error_on_401(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": "Unauthorized"}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="bad-token")
    from voidstorm_companion.api_client import AuthError
    with pytest.raises(AuthError):
        client.upload_tournament(_sample_tournament())


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_raises_upload_error_on_500(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.json.return_value = {}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    from voidstorm_companion.api_client import UploadError
    with pytest.raises(UploadError):
        client.upload_tournament(_sample_tournament())


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_tournament_accepts_201_response(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"data": {"created": True}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload_tournament(_sample_tournament())
    assert result["created"] is True


# ---------------------------------------------------------------------------
# Phase 5: leagues, challenges, audit_log in upload payload
# ---------------------------------------------------------------------------


def _sample_leagues():
    return [
        {
            "leagueKey": "GuildLeague1",
            "name": "Friday Night League",
            "guild": "Voidstorm",
            "season": 3,
            "standings": [
                {"name": "Player1", "points": 15, "wins": 5, "losses": 2, "draws": 0, "netGold": 12500},
            ],
            "history": [],
            "startedAt": 1709234567,
        }
    ]


def _sample_challenges():
    return [
        {"challenger": "Player1", "opponent": "Player2", "mode": "DEATHROLL", "wager": 5000, "result": "challenger_win", "timestamp": 1709234567},
        {"challenger": "Player2", "opponent": "Player3", "mode": "COINFLIP", "wager": 2500, "result": "opponent_win", "timestamp": 1709235000},
    ]


def _sample_audit_log():
    return [
        {"timestamp": 1709234567, "eventType": "GAME_START", "players": ["P1", "P2"], "mode": "DEATHROLL", "amounts": [5000], "result": "", "severity": "INFO"},
        {"timestamp": 1709234700, "eventType": "GAME_RESULT", "players": ["P1", "P2"], "mode": "DEATHROLL", "amounts": [5000], "result": "P1", "severity": "INFO"},
        {"timestamp": 1709234800, "eventType": "SUSPICIOUS_PATTERN", "players": ["P2"], "mode": "DEATHROLL", "amounts": [5000], "result": "", "severity": "WARN"},
    ]


def test_prepare_payload_without_leagues_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()])
    assert "leagues" not in payload


def test_prepare_payload_with_leagues_includes_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    leagues = _sample_leagues()
    payload = client.prepare_payload([_minimal_session()], leagues=leagues)
    assert "leagues" in payload
    assert len(payload["leagues"]) == 1
    assert payload["leagues"][0]["name"] == "Friday Night League"


def test_prepare_payload_none_leagues_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], leagues=None)
    assert "leagues" not in payload


def test_prepare_payload_empty_leagues_list_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], leagues=[])
    assert "leagues" not in payload


def test_prepare_payload_without_challenges_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()])
    assert "challenges" not in payload


def test_prepare_payload_with_challenges_includes_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    challenges = _sample_challenges()
    payload = client.prepare_payload([_minimal_session()], challenges=challenges)
    assert "challenges" in payload
    assert len(payload["challenges"]) == 2
    assert payload["challenges"][0]["challenger"] == "Player1"


def test_prepare_payload_none_challenges_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], challenges=None)
    assert "challenges" not in payload


def test_prepare_payload_empty_challenges_list_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], challenges=[])
    assert "challenges" not in payload


def test_prepare_payload_without_audit_log_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()])
    assert "auditLog" not in payload


def test_prepare_payload_with_audit_log_includes_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    audit_log = _sample_audit_log()
    payload = client.prepare_payload([_minimal_session()], audit_log=audit_log)
    assert "auditLog" in payload
    assert len(payload["auditLog"]) == 3
    assert payload["auditLog"][0]["eventType"] == "GAME_START"


def test_prepare_payload_none_audit_log_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], audit_log=None)
    assert "auditLog" not in payload


def test_prepare_payload_empty_audit_log_omits_key():
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload([_minimal_session()], audit_log=[])
    assert "auditLog" not in payload


def test_prepare_payload_all_7_fields_together():
    """All 7 optional payload fields can be included simultaneously."""
    client = ApiClient(api_url="http://localhost", token="test-token")
    payload = client.prepare_payload(
        [_minimal_session()],
        player_stats=_sample_player_stats(),
        tournaments=[_sample_tournament()],
        achievements=_sample_achievements(),
        leagues=_sample_leagues(),
        challenges=_sample_challenges(),
        audit_log=_sample_audit_log(),
    )
    assert "sessions" in payload
    assert "playerStats" in payload
    assert "tournaments" in payload
    assert "achievements" in payload
    assert "leagues" in payload
    assert "challenges" in payload
    assert "auditLog" in payload


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_with_leagues_sends_in_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload([_minimal_session()], leagues=_sample_leagues())

    sent_json = mock_post.call_args.kwargs["json"]
    assert "leagues" in sent_json
    assert sent_json["leagues"][0]["name"] == "Friday Night League"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_without_leagues_omits_from_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload([_minimal_session()])

    sent_json = mock_post.call_args.kwargs["json"]
    assert "leagues" not in sent_json


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_with_audit_log_sends_in_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"imported": 1, "skipped": 0}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload([_minimal_session()], audit_log=_sample_audit_log())

    sent_json = mock_post.call_args.kwargs["json"]
    assert "auditLog" in sent_json
    assert len(sent_json["auditLog"]) == 3


# ---------------------------------------------------------------------------
# Phase 5: upload_audit() method
# ---------------------------------------------------------------------------


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_posts_to_correct_endpoint(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"recorded": 3}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    client.upload_audit(_sample_audit_log())

    mock_post.assert_called_once()
    url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs.get("url", "")
    assert "/api/v1/gambling/audit" in url


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_sends_entries_in_body(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    entries = _sample_audit_log()
    client.upload_audit(entries)

    sent_json = mock_post.call_args.kwargs["json"]
    assert "entries" in sent_json
    assert len(sent_json["entries"]) == 3
    assert sent_json["entries"][0]["eventType"] == "GAME_START"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_includes_auth_header(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="audit-secret-token")
    client.upload_audit(_sample_audit_log())

    headers = mock_post.call_args.kwargs.get("headers", {})
    assert "Bearer audit-secret-token" in headers.get("Authorization", "")


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_returns_data_unwrapped(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"recorded": 3, "suspicious": 1}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload_audit(_sample_audit_log())
    assert result["recorded"] == 3
    assert result["suspicious"] == 1


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_returns_raw_when_no_data_envelope(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload_audit(_sample_audit_log())
    assert result["status"] == "ok"


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_raises_auth_error_on_401(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": "Unauthorized"}
    mock_post.return_value = mock_resp

    from voidstorm_companion.api_client import AuthError
    client = ApiClient(api_url="http://localhost", token="bad-token")
    with pytest.raises(AuthError):
        client.upload_audit(_sample_audit_log())


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_raises_upload_error_on_500(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.json.return_value = {}
    mock_post.return_value = mock_resp

    from voidstorm_companion.api_client import UploadError
    client = ApiClient(api_url="http://localhost", token="test-token")
    with pytest.raises(UploadError):
        client.upload_audit(_sample_audit_log())


@patch("voidstorm_companion.api_client.requests.post")
def test_upload_audit_accepts_201_response(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"data": {"created": True}}
    mock_post.return_value = mock_resp

    client = ApiClient(api_url="http://localhost", token="test-token")
    result = client.upload_audit(_sample_audit_log())
    assert result["created"] is True
