import json
import logging
import os
import tempfile
import threading

from slpp import slpp as lua

from voidstorm_companion.api_client import ApiClient, AuthError, UploadError
from voidstorm_companion.file_watcher import SavedVariablesWatcher

log = logging.getLogger("voidstorm-companion")

_KEYS_SV_NAME = "VoidstormKeys.lua"
_KEYS_COMPANION_SV_NAME = "VoidstormKeysCompanionData.lua"
_KEYS_STATE_FILENAME = "keys_state.json"


def _parse_keys_savedvariables(filepath: str) -> dict:
    """Parse VoidstormKeysGlobalDB from a SavedVariables Lua file.

    Args:
        filepath: Absolute path to the VoidstormKeys.lua SavedVariables file.

    Returns:
        Parsed dict from the Lua table, or empty dict on failure.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    try:
        eq_pos = content.index("=")
    except ValueError:
        return {}

    raw_table = content[eq_pos + 1:].strip()
    if not raw_table:
        return {}

    result = lua.decode(raw_table)
    if isinstance(result, dict):
        return result
    return {}


def _normalize_member(raw: dict) -> dict:
    """Normalize a single group member dict from a run record.

    Args:
        raw: Raw member dict decoded from Lua.

    Returns:
        Normalized member dict with all expected fields.
    """
    return {
        "name": str(raw.get("name", "")),
        "classFile": str(raw.get("classFile", "")) if raw.get("classFile") else None,
        "role": str(raw.get("role", "")) if raw.get("role") else None,
    }


def _normalize_run(raw: dict) -> dict:
    """Normalize a single run record from VoidstormKeysGlobalDB.

    Args:
        raw: Raw run dict decoded from Lua.

    Returns:
        Normalized run dict with all expected fields present and typed.
    """
    if not isinstance(raw, dict):
        return {}

    members_raw = raw.get("members", [])
    if isinstance(members_raw, dict):
        members_raw = [members_raw[k] for k in sorted(members_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)]
    members = []
    for m in members_raw:
        if isinstance(m, dict):
            members.append(_normalize_member(m))

    affixes_raw = raw.get("affixes", [])
    if isinstance(affixes_raw, dict):
        affixes_raw = [affixes_raw[k] for k in sorted(affixes_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)]
    affixes = [int(a) for a in affixes_raw if a is not None]

    totals_raw = raw.get("totals", {})
    totals = None
    if isinstance(totals_raw, dict) and totals_raw:
        totals = {}
        for stat_key in ("damage", "healing", "interrupts", "deaths", "avoidable"):
            stat_raw = totals_raw.get(stat_key, {})
            if isinstance(stat_raw, dict):
                totals[stat_key] = {str(k): int(v) if isinstance(v, (int, float)) else 0 for k, v in stat_raw.items()}

    return {
        "mapID": int(raw.get("mapID", 0)),
        "dungeonName": str(raw.get("dungeonName", "")) if raw.get("dungeonName") else None,
        "level": int(raw.get("level", 0)),
        "time": float(raw.get("time", 0)),
        "timeLimit": int(raw.get("timeLimit", 0)) if raw.get("timeLimit") else None,
        "timed": bool(raw.get("timed")),
        "upgrades": int(raw.get("upgrades", 0)),
        "practiceRun": bool(raw.get("practiceRun")) if raw.get("practiceRun") is not None else False,
        "members": members,
        "timestamp": int(raw.get("timestamp", 0)),
        "affixes": affixes,
        "totals": totals,
    }


def _normalize_team_player(name: str, raw: dict) -> dict:
    """Normalize a single team history player record.

    Args:
        name: Player name key from the team table.
        raw: Raw player data dict decoded from Lua.

    Returns:
        Normalized player dict with all expected fields.
    """
    if not isinstance(raw, dict):
        return {}

    dungeons_raw = raw.get("dungeons", {})
    dungeons = {}
    if isinstance(dungeons_raw, dict):
        for dname, ddata in dungeons_raw.items():
            if isinstance(ddata, dict):
                dungeons[str(dname)] = {
                    "runs": int(ddata.get("runs", 0)),
                    "timed": int(ddata.get("timed", 0)),
                }

    return {
        "name": str(name),
        "runs": int(raw.get("runs", 0)),
        "timed": int(raw.get("timed", 0)),
        "depleted": int(raw.get("depleted", 0)),
        "firstRun": int(raw.get("firstRun", 0)),
        "lastRun": int(raw.get("lastRun", 0)),
        "classFile": str(raw.get("classFile", "")) if raw.get("classFile") else None,
        "rating": int(raw.get("rating", 0)),
        "favorite": bool(raw.get("favorite")),
        "avoid": bool(raw.get("avoid")),
        "dungeons": dungeons,
    }


def parse_keys_data(filepath: str) -> tuple[list[dict], dict]:
    """Parse VoidstormKeys SavedVariables and return runs and team data.

    Args:
        filepath: Absolute path to the VoidstormKeys.lua SavedVariables file.

    Returns:
        A 2-tuple of (runs, team) where runs is a list of normalized run dicts
        and team is a dict mapping player name to normalized player data.
    """
    data = _parse_keys_savedvariables(filepath)
    if not data:
        return [], {}

    runs_raw = data.get("runs", [])
    if isinstance(runs_raw, dict):
        runs_raw = [runs_raw[k] for k in sorted(runs_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)]

    runs = []
    for r in runs_raw:
        if isinstance(r, dict):
            normalized = _normalize_run(r)
            if normalized.get("mapID"):
                runs.append(normalized)

    team_raw = data.get("team", {})
    team = {}
    if isinstance(team_raw, dict):
        for player_name, player_data in team_raw.items():
            if isinstance(player_data, dict):
                normalized = _normalize_team_player(player_name, player_data)
                if normalized.get("name"):
                    team[str(player_name)] = normalized

    return runs, team


class KeysState:
    """Tracks the last-uploaded run count for deduplication.

    Args:
        state_path: Path to the JSON file used to persist state between runs.
    """

    def __init__(self, state_path: str):
        self._path = state_path
        self._last_run_count: int = 0
        self._last_run_timestamp: int = 0
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                self._last_run_count = int(data.get("lastRunCount", 0))
                self._last_run_timestamp = int(data.get("lastRunTimestamp", 0))
            except (json.JSONDecodeError, OSError, ValueError):
                pass

    def _save(self):
        dir_ = os.path.dirname(self._path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "lastRunCount": self._last_run_count,
                    "lastRunTimestamp": self._last_run_timestamp,
                }, f)
            os.replace(tmp_path, self._path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @property
    def last_run_count(self) -> int:
        """Number of runs that were present at last successful upload."""
        return self._last_run_count

    @property
    def last_run_timestamp(self) -> int:
        """Timestamp of the most recent run at last successful upload."""
        return self._last_run_timestamp

    def update(self, run_count: int, latest_timestamp: int):
        """Record a successful upload and persist to disk.

        Args:
            run_count: Total number of runs in the SavedVariables at upload time.
            latest_timestamp: Timestamp of the most recent run uploaded.
        """
        self._last_run_count = run_count
        self._last_run_timestamp = latest_timestamp
        self._save()

    def filter_new_runs(self, runs: list[dict]) -> list[dict]:
        """Return only runs that are newer than the last upload.

        Args:
            runs: Full list of normalized run dicts.

        Returns:
            List of runs with timestamps strictly greater than the last
            uploaded timestamp.
        """
        if self._last_run_timestamp == 0:
            return runs
        return [r for r in runs if r.get("timestamp", 0) > self._last_run_timestamp]


class KeysWatcher:
    """Watches VoidstormKeys SavedVariables for changes and triggers callbacks.

    Args:
        sv_path: Absolute path to the VoidstormKeys.lua SavedVariables file.
        on_change: Callback invoked with (runs, team) when the file changes.
        debounce_sec: Debounce interval in seconds.
    """

    def __init__(self, sv_path: str, on_change, debounce_sec: float = 2.0):
        self._sv_path = sv_path
        self._on_change = on_change
        self._watcher = SavedVariablesWatcher(
            filepath=sv_path,
            on_change=self._handle_change,
            debounce_sec=debounce_sec,
        )

    def _handle_change(self, filepath: str):
        try:
            runs, team = parse_keys_data(filepath)
            log.info("VoidstormKeys file changed: %d run(s), %d team member(s)", len(runs), len(team))
            self._on_change(runs, team)
        except FileNotFoundError:
            log.warning("VoidstormKeys SavedVariables not found: %s", filepath)
        except Exception:
            log.exception("Error parsing VoidstormKeys SavedVariables: %s", filepath)

    def start(self):
        """Start watching the SavedVariables file."""
        self._watcher.start()
        log.info("KeysWatcher started for %s", self._sv_path)

    def stop(self):
        """Stop watching the SavedVariables file."""
        self._watcher.stop()
        log.info("KeysWatcher stopped")


class KeysUploader:
    """Uploads M+ run data to the Voidstorm API.

    Args:
        api_client: Authenticated ApiClient instance.
    """

    def __init__(self, api_client: ApiClient):
        self._client = api_client

    def upload_runs(self, runs: list[dict], team: dict | None = None) -> dict:
        """Upload run data (and optional team history) to the API.

        Args:
            runs: List of normalized run dicts to upload.
            team: Optional dict mapping player name to team history data.

        Returns:
            Response body dict from the server.

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the server responds with any other non-200/201 status.
        """
        if not runs:
            return {"imported": 0, "skipped": 0}
        return self._client.upload_keys(runs, team=team)

    def fetch_comp_data(self, dungeon: str, affix: str) -> dict:
        """Fetch top comp data for a dungeon/affix combination.

        Args:
            dungeon: Dungeon map ID or identifier string.
            affix: Current affix identifier string.

        Returns:
            Dict of comp data from the API.

        Raises:
            AuthError: When the server responds with HTTP 401.
            UploadError: When the request fails.
        """
        return self._client.fetch_keys_comps(dungeon, affix)


class KeysCompanionWriter:
    """Writes companion-fetched comp data to a Lua SavedVariables file.

    The addon reads this file via DataBridge as fallback comp data when the
    Raider.io addon is not installed.

    Args:
        sv_path: Absolute path to the VoidstormKeysCompanionData.lua file.
    """

    def __init__(self, sv_path: str):
        self._sv_path = sv_path

    def write(self, comp_data: dict):
        """Write comp data to the SavedVariables file atomically.

        Args:
            comp_data: Dict mapping dungeon map ID to comp data. Written as
                ``VoidstormKeysCompData = { comps = { ... } }``.
        """
        lines = ["VoidstormKeysCompData = {"]
        lines.append("  comps = {")
        for map_id, comps in comp_data.items():
            lines.append(f'    ["{self._esc(str(map_id))}"] = {{')
            if isinstance(comps, list):
                for comp in comps:
                    if isinstance(comp, dict):
                        lines.append("      {")
                        for k, v in comp.items():
                            if isinstance(v, bool):
                                lines.append(f'        {k} = {"true" if v else "false"},')
                            elif isinstance(v, (int, float)):
                                lines.append(f"        {k} = {v},")
                            elif isinstance(v, list):
                                inner = ", ".join(f'"{self._esc(str(i))}"' for i in v)
                                lines.append(f"        {k} = {{{inner}}},")
                            elif v is not None:
                                lines.append(f'        {k} = "{self._esc(str(v))}",')
                        lines.append("      },")
            lines.append("    },")
        lines.append("  },")
        lines.append("}")

        content = "\n".join(lines) + "\n"
        dir_ = os.path.dirname(self._sv_path)
        os.makedirs(dir_, exist_ok=True)
        tmp_path = self._sv_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, self._sv_path)
            log.info("Wrote companion comp data to %s", self._sv_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def _esc(s: str) -> str:
        return (s
            .replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace('\n', '\\n')
            .replace('\r', '\\r')
            .replace('\t', '\\t')
            .replace('\0', '\\0')
            .replace('\a', '\\a')
            .replace('\b', '\\b'))


class KeysIntegration:
    """Ties together watching, uploading, and companion data writing for VoidstormKeys.

    Args:
        wow_path: Root WoW install path (e.g. ``E:\\Games\\World of Warcraft\\_retail_``).
        account: WoW account name used in the WTF path.
        api_client: Authenticated ApiClient instance.
    """

    def __init__(self, wow_path: str, account: str, api_client: ApiClient):
        self._wow_path = wow_path
        self._account = account
        self._api_client = api_client

        sv_dir = os.path.join(wow_path, "WTF", "Account", account, "SavedVariables")
        self._keys_sv_path = os.path.join(sv_dir, _KEYS_SV_NAME)
        self._companion_sv_path = os.path.join(sv_dir, _KEYS_COMPANION_SV_NAME)

        config_dir = os.path.join(os.path.expanduser("~"), ".voidstorm-companion")
        state_path = os.path.join(config_dir, _KEYS_STATE_FILENAME)

        self._state = KeysState(state_path)
        self._watcher = KeysWatcher(self._keys_sv_path, on_change=self._on_keys_changed)
        self._uploader = KeysUploader(api_client)
        self._writer = KeysCompanionWriter(self._companion_sv_path)
        self._running = False

    def _on_keys_changed(self, runs: list[dict], team: dict):
        """Callback when VoidstormKeys SavedVariables file changes."""
        new_runs = self._state.filter_new_runs(runs)
        if not new_runs:
            log.info("KeysIntegration: no new runs to upload")
            return

        log.info("KeysIntegration: uploading %d new run(s)", len(new_runs))
        threading.Thread(
            target=self._upload_runs,
            args=(runs, new_runs, team),
            daemon=True,
        ).start()

    def _upload_runs(self, all_runs: list[dict], new_runs: list[dict], team: dict):
        """Upload new runs in a background thread.

        Args:
            all_runs: Full list of runs (for state tracking).
            new_runs: Only the new runs to upload.
            team: Team history data to include in the upload.
        """
        try:
            result = self._uploader.upload_runs(new_runs, team=team if team else None)
            imported = result.get("imported", 0)
            skipped = result.get("skipped", 0)
            log.info("KeysIntegration upload complete: %d imported, %d skipped", imported, skipped)

            latest_ts = max((r.get("timestamp", 0) for r in all_runs), default=0)
            self._state.update(len(all_runs), latest_ts)
        except AuthError:
            log.error("KeysIntegration: authentication failed during upload")
        except UploadError as e:
            log.error("KeysIntegration: upload failed: %s", e)
        except Exception:
            log.exception("KeysIntegration: unexpected upload error")

    def start(self):
        """Start watching VoidstormKeys SavedVariables for changes."""
        if self._running:
            return
        self._running = True
        self._watcher.start()
        log.info("KeysIntegration started")

    def stop(self):
        """Stop watching and clean up."""
        if not self._running:
            return
        self._running = False
        self._watcher.stop()
        log.info("KeysIntegration stopped")

    def sync(self):
        """Manual sync: parse current data, upload new runs, fetch comp data.

        This method runs synchronously. For async usage, wrap in a thread.
        """
        log.info("KeysIntegration: manual sync started")

        try:
            runs, team = parse_keys_data(self._keys_sv_path)
        except FileNotFoundError:
            log.warning("KeysIntegration: SavedVariables not found: %s", self._keys_sv_path)
            return
        except Exception:
            log.exception("KeysIntegration: error parsing SavedVariables")
            return

        new_runs = self._state.filter_new_runs(runs)
        if new_runs:
            log.info("KeysIntegration: uploading %d new run(s)", len(new_runs))
            try:
                result = self._uploader.upload_runs(new_runs, team=team if team else None)
                imported = result.get("imported", 0)
                skipped = result.get("skipped", 0)
                log.info("KeysIntegration sync upload: %d imported, %d skipped", imported, skipped)

                latest_ts = max((r.get("timestamp", 0) for r in runs), default=0)
                self._state.update(len(runs), latest_ts)
            except AuthError:
                log.error("KeysIntegration: authentication failed during sync upload")
            except UploadError as e:
                log.error("KeysIntegration: sync upload failed: %s", e)
            except Exception:
                log.exception("KeysIntegration: unexpected sync upload error")
        else:
            log.info("KeysIntegration: no new runs to upload")

        log.info("KeysIntegration: manual sync complete")
