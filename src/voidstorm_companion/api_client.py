import re
import time

import requests

_PLAYER_FIELDS = {"name", "roll", "rolled", "realm", "guild", "guildRank", "bet", "payout"}
_SESSION_FIELDS = {"id", "mode", "host", "wager", "channel", "startedAt", "endedAt", "rounds", "signature"}
_ROUND_FIELDS = {"number", "mode", "time", "players", "results", "pokerHand", "lotteryRanges", "pocket", "color", "betType"}
_VALID_MODES = {
    "DIFFERENCE", "POT", "DEATHROLL", "ODDEVEN", "ELIMINATION", "LOTTERY",
    "POKER", "DOUBLEORNOTHING", "BLACKJACK", "COINFLIP", "WAR", "SLOTS",
    "ROULETTE", "OVERUNDER", "HOTPOTATO", "STREAKBET",
}
_MAX_WAGER = 1_000_000

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0

_ID_PATTERN = re.compile(r'^[\w-]+$')


def _validate_id(value: str, label: str = "id") -> None:
    if not _ID_PATTERN.match(value):
        raise ValueError(f"Invalid {label}: {value!r}")


class UploadError(Exception):
    pass


class AuthError(UploadError):
    pass


class ApiClient:
    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip("/")
        self.token = token

    def _post_with_retry(self, url: str, json_data: dict) -> requests.Response:
        """POST with exponential backoff retry on transient failures."""
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(
                    url,
                    json=json_data,
                    headers=self._headers(),
                    timeout=30,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            if resp.status_code == 401:
                raise AuthError("Unauthorized — token may be expired")
            if 500 <= resp.status_code < 600:
                last_exc = UploadError(f"Server error (HTTP {resp.status_code}): {resp.text}")
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            if resp.status_code not in (200, 201) and resp.status_code >= 400:
                raise UploadError(f"Upload failed (HTTP {resp.status_code}): {resp.text}")
            return resp
        raise UploadError(f"Upload failed after {MAX_RETRIES} attempts") from last_exc

    def prepare_payload(
        self,
        sessions: list[dict],
        player_stats: dict | None = None,
        tournaments: list[dict] | None = None,
        achievements: dict | None = None,
        leagues: list[dict] | None = None,
        challenges: list[dict] | None = None,
        audit_log: list[dict] | None = None,
    ) -> dict:
        """Build the upload payload from raw sessions and optional supplementary data.

        Args:
            sessions: Raw session dicts parsed from SavedVariables.
            player_stats: Optional pre-built playerStats dict to include in the
                payload alongside sessions.  When ``None`` or empty the key is
                omitted so existing API callers are unaffected.
            tournaments: Optional list of normalized tournament dicts.  When
                ``None`` or empty the key is omitted.
            achievements: Optional dict mapping achievement key -> metadata.
                When ``None`` or empty the key is omitted.
            leagues: Optional list of normalized league dicts.  When ``None``
                or empty the key is omitted.
            challenges: Optional list of normalized challenge dicts.  When
                ``None`` or empty the key is omitted.
            audit_log: Optional list of normalized audit log entry dicts.  When
                ``None`` or empty the key is omitted.

        Returns:
            Dict with at minimum a ``"sessions"`` key; optional keys
            ``"playerStats"``, ``"tournaments"``, ``"achievements"``,
            ``"leagues"``, ``"challenges"``, and ``"auditLog"`` are included
            when the corresponding arguments are provided and non-empty.
        """
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
        payload: dict = {"sessions": cleaned}
        if player_stats:
            payload["playerStats"] = player_stats
        if tournaments:
            payload["tournaments"] = tournaments
        if achievements:
            payload["achievements"] = achievements
        if leagues:
            payload["leagues"] = leagues
        if challenges:
            payload["challenges"] = challenges
        if audit_log:
            payload["auditLog"] = audit_log
        return payload

    def upload(
        self,
        sessions: list[dict],
        player_stats: dict | None = None,
        tournaments: list[dict] | None = None,
        achievements: dict | None = None,
        leagues: list[dict] | None = None,
        challenges: list[dict] | None = None,
        audit_log: list[dict] | None = None,
    ) -> dict:
        """Upload sessions (and optional supplementary data) to the API.

        Args:
            sessions: Raw session dicts to upload.
            player_stats: Optional playerStats dict built from exportedStats.
                Included in the request body when provided; omitted otherwise.
            tournaments: Optional list of normalized tournament dicts to include
                in the request body alongside sessions.
            achievements: Optional dict of achievement data to include in the
                request body alongside sessions.
            leagues: Optional list of normalized league dicts to include in
                the request body alongside sessions.
            challenges: Optional list of normalized challenge dicts to include
                in the request body alongside sessions.
            audit_log: Optional list of normalized audit log entries to include
                in the request body alongside sessions.

        Returns:
            Dict with ``imported`` and ``skipped`` counts from the server.

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the server responds with any other non-200 status.
        """
        payload = self.prepare_payload(
            sessions,
            player_stats=player_stats,
            tournaments=tournaments,
            achievements=achievements,
            leagues=leagues,
            challenges=challenges,
            audit_log=audit_log,
        )
        if not payload["sessions"]:
            return {"imported": 0, "skipped": 0}
        resp = self._post_with_retry(f"{self.api_url}/api/gambling/upload", payload)
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data

    def upload_tournament(self, tournament_data: dict) -> dict:
        """Post a completed tournament result to the API.

        Args:
            tournament_data: Normalized tournament dict as produced by
                ``lua_parser.parse_tournaments``.  Must contain an ``"id"`` key.

        Returns:
            Response body dict from the server (unwrapped from ``"data"`` envelope
            when present).

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the server responds with any other non-200/201 status.
        """
        tournament_id = tournament_data.get("id", "")
        _validate_id(tournament_id, "tournament_id")
        resp = self._post_with_retry(
            f"{self.api_url}/api/v1/gambling/tournaments/{tournament_id}/result",
            tournament_data,
        )
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data

    def upload_audit(self, audit_entries: list[dict]) -> dict:
        """Post audit log entries to the dedicated audit endpoint.

        Args:
            audit_entries: List of normalized audit log entry dicts as produced
                by ``lua_parser.parse_audit_log``.

        Returns:
            Response body dict from the server (unwrapped from ``"data"`` envelope
            when present).

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the server responds with any other non-200/201 status.
        """
        resp = self._post_with_retry(
            f"{self.api_url}/api/v1/gambling/audit",
            {"entries": audit_entries},
        )
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data

    def upload_reputation(self, payload: dict) -> dict:
        """Upload reputation data (encounters + tags) to the website.

        Args:
            payload: Dict with keys ``exportedAt``, ``version``, ``encounters``,
                ``tags`` as produced by ``lua_parser.parse_partyledger_export``.

        Returns:
            Response body dict from the server (unwrapped from ``"data"`` envelope
            when present).

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the server responds with any other non-200 status.
        """
        resp = self._post_with_retry(f"{self.api_url}/api/reputation/upload", payload)
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Client-Version": "voidstorm-companion/1.0.0",
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
        _validate_id(group_id, "group_id")
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
        _validate_id(group_id, "group_id")
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
        _validate_id(group_id, "group_id")
        _validate_id(signup_id, "signup_id")
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
        _validate_id(group_id, "group_id")
        _validate_id(signup_id, "signup_id")
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
        _validate_id(group_id, "group_id")
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
        _validate_id(group_id, "group_id")
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
        _validate_id(group_id, "group_id")
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

    def upload_keys(self, runs: list[dict], team: dict | None = None) -> dict:
        """Upload M+ run data (and optional team history) to the keys API.

        Args:
            runs: List of normalized run dicts to upload.
            team: Optional dict mapping player name to team history data.

        Returns:
            Response body dict from the server (unwrapped from ``"data"``
            envelope when present).

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the server responds with any other non-200/201 status.
        """
        payload = {"runs": runs}
        if team:
            payload["team"] = team
        resp = requests.post(
            f"{self.api_url}/api/keys/upload",
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized -- token may be expired")
        if resp.status_code not in (200, 201):
            raise UploadError(f"Keys upload failed (HTTP {resp.status_code}): {resp.text}")
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data

    def fetch_player_elo(self, player_name: str) -> dict:
        resp = requests.get(
            f"{self.api_url}/api/v1/gambling/elo/{requests.utils.quote(player_name)}",
            headers=self._headers(),
            timeout=10,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized -- token may be expired")
        if resp.status_code == 404:
            return {}
        if resp.status_code != 200:
            raise UploadError(f"ELO fetch failed (HTTP {resp.status_code}): {resp.text}")
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data

    def fetch_reputation_bulk(self, players: list[str]) -> dict:
        if not players:
            return {}
        batches = [players[i:i + 100] for i in range(0, len(players), 100)]
        merged: dict = {}
        for batch in batches:
            params = ",".join(batch)
            resp = requests.get(
                f"{self.api_url}/api/reputation/bulk",
                params={"players": params},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            if resp.status_code not in (200, 201):
                continue
            data = resp.json()
            if data.get("success") and data.get("data", {}).get("players"):
                merged.update(data["data"]["players"])
        return merged

    def fetch_keys_comps(self, dungeon: str, affix: str) -> dict:
        """Fetch top comp data for a dungeon/affix combination.

        Args:
            dungeon: Dungeon map ID or identifier string.
            affix: Current affix identifier string.

        Returns:
            Comp data dict from the server (unwrapped from ``"data"``
            envelope when present).

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the request fails.
        """
        resp = requests.get(
            f"{self.api_url}/api/keys/comps/{dungeon}/{affix}",
            headers=self._headers(),
            timeout=15,
        )
        if resp.status_code == 401:
            raise AuthError("Unauthorized -- token may be expired")
        if resp.status_code != 200:
            raise UploadError(f"Keys comps fetch failed (HTTP {resp.status_code}): {resp.text}")
        data = resp.json()
        if "data" in data:
            return data["data"]
        return data
