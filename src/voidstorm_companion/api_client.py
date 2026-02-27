import requests

_PLAYER_FIELDS = {"name", "roll", "rolled", "realm", "guild", "guildRank"}
_SESSION_FIELDS = {"id", "mode", "host", "wager", "channel", "startedAt", "endedAt", "rounds", "signature"}
_ROUND_FIELDS = {"number", "mode", "time", "players", "results", "pokerHand"}
_VALID_MODES = {"DIFFERENCE", "POT", "DEATHROLL", "ODDEVEN", "ELIMINATION", "LOTTERY", "POKER"}
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
            if s.get("mode") not in _VALID_MODES:
                continue
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
        if not payload["sessions"]:
            return {"imported": 0, "skipped": 0}
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

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_characters(self) -> list[dict]:
        resp = requests.get(
            f"{self.api_url}/api/user/characters",
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        data = resp.json().get("data", {})
        return data.get("characters", []) if isinstance(data, dict) else []

    def create_group(self, payload: dict) -> dict:
        resp = requests.post(
            f"{self.api_url}/api/groups",
            json=payload,
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code not in (200, 201):
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def signup_group(self, group_id: str, payload: dict) -> dict:
        resp = requests.post(
            f"{self.api_url}/api/groups/{group_id}/signup",
            json=payload,
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code not in (200, 201):
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def withdraw_group(self, group_id: str) -> dict:
        resp = requests.delete(
            f"{self.api_url}/api/groups/{group_id}/signup",
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def accept_signup(self, group_id: str, signup_id: str) -> dict:
        resp = requests.patch(
            f"{self.api_url}/api/groups/{group_id}/signup/{signup_id}",
            json={"status": "ACCEPTED"},
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def decline_signup(self, group_id: str, signup_id: str) -> dict:
        resp = requests.patch(
            f"{self.api_url}/api/groups/{group_id}/signup/{signup_id}",
            json={"status": "DECLINED"},
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def start_group(self, group_id: str) -> dict:
        resp = requests.patch(
            f"{self.api_url}/api/groups/{group_id}/start",
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def cancel_group(self, group_id: str) -> dict:
        resp = requests.patch(
            f"{self.api_url}/api/groups/{group_id}/cancel",
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})

    def lock_group(self, group_id: str) -> dict:
        resp = requests.patch(
            f"{self.api_url}/api/groups/{group_id}/lock",
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized — token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Request failed (HTTP {resp.status_code}): {resp.text}")
        return resp.json().get("data", {})
