from unittest.mock import patch, MagicMock
import pytest
from voidstorm_companion.api_client import ApiClient, AuthError


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
