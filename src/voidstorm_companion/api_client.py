import requests

_PLAYER_FIELDS = {"name", "roll", "rolled", "realm", "guild", "guildRank"}
_SESSION_FIELDS = {"id", "mode", "host", "wager", "channel", "startedAt", "endedAt", "rounds"}
_ROUND_FIELDS = {"number", "mode", "time", "players", "results"}
_MAX_WAGER = 1_000_000


class UploadError(Exception):
    pass


class AuthError(UploadError):
    pass


class ApiClient:
    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip("/")
        self.token = token

    def prepare_payload(self, sessions: list[dict]) -> dict:
        cleaned = []
        for s in sessions:
            rounds = s.get("rounds", [])
            if not rounds:
                continue
            wager = s.get("wager", 0)
            if isinstance(wager, (int, float)) and wager > _MAX_WAGER:
                wager = _MAX_WAGER
            clean_session = {k: v for k, v in s.items() if k in _SESSION_FIELDS}
            clean_session["wager"] = int(wager)
            clean_rounds = []
            for r in clean_session.get("rounds", []):
                clean_round = {k: v for k, v in r.items() if k in _ROUND_FIELDS}
                clean_players = []
                for p in clean_round.get("players", []):
                    cp = {k: v for k, v in p.items() if k in _PLAYER_FIELDS}
                    if "roll" not in cp or cp["roll"] is None:
                        cp["roll"] = None
                    else:
                        cp["roll"] = int(cp["roll"])
                    clean_players.append(cp)
                clean_round["players"] = clean_players
                clean_rounds.append(clean_round)
            clean_session["rounds"] = clean_rounds
            cleaned.append(clean_session)
        return {"sessions": cleaned}

    def upload(self, sessions: list[dict]) -> dict:
        payload = self.prepare_payload(sessions)
        resp = requests.post(
            f"{self.api_url}/api/gambling/upload",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")

        if resp.status_code != 200:
            raise UploadError(f"Upload failed (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        if "data" in data:
            return data["data"]
        return data
