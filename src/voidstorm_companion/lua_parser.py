from slpp import slpp as lua


def parse_lua_table(content: str, var_name: str) -> dict:
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


def _normalize_exported_stats(raw: dict) -> dict:
    """Normalize raw exportedStats table from Lua into a clean Python dict.

    Args:
        raw: Raw dict decoded from the Lua exportedStats table.

    Returns:
        Normalized dict with keys: timestamp, lifetime, modeBreakdown,
        recentSessions, rivals.
    """
    if not isinstance(raw, dict):
        return {}

    result: dict = {}

    timestamp = raw.get("timestamp")
    if timestamp is not None:
        result["timestamp"] = int(timestamp)

    # lifetime block
    lifetime = raw.get("lifetime")
    if isinstance(lifetime, dict):
        result["lifetime"] = {
            "wins": int(lifetime.get("wins", 0)),
            "losses": int(lifetime.get("losses", 0)),
            "totalWagered": int(lifetime.get("totalWagered", 0)),
            "totalWon": int(lifetime.get("totalWon", 0)),
            "netProfit": int(lifetime.get("netProfit", 0)),
            "sessions": int(lifetime.get("sessionsPlayed", lifetime.get("sessions", 0))),
            "playtime": int(lifetime.get("totalPlaytime", lifetime.get("playtime", 0))),
        }

    # modeBreakdown block
    mode_breakdown = raw.get("modeBreakdown")
    if isinstance(mode_breakdown, dict):
        normalized_breakdown: dict[str, dict] = {}
        for mode_key, mode_data in mode_breakdown.items():
            if isinstance(mode_data, dict):
                normalized_breakdown[str(mode_key)] = {
                    "wins": int(mode_data.get("wins", 0)),
                    "losses": int(mode_data.get("losses", 0)),
                    "wagered": int(mode_data.get("wagered", 0)),
                    "won": int(mode_data.get("won", 0)),
                    "played": int(mode_data.get("played", 0)),
                }
        result["modeBreakdown"] = normalized_breakdown

    # recentSessions list
    recent = raw.get("recentSessions")
    if isinstance(recent, (list, dict)):
        if isinstance(recent, dict):
            recent = [recent[k] for k in sorted(recent.keys(), key=str)]
        normalized_recent = []
        for entry in recent:
            if isinstance(entry, dict):
                normalized_recent.append({
                    "mode": str(entry.get("mode", "")),
                    "result": str(entry.get("result", "")),
                    "netProfit": int(entry.get("netProfit", 0)),
                    "timestamp": int(entry.get("timestamp", 0)),
                })
        result["recentSessions"] = normalized_recent

    # rivals list
    rivals = raw.get("rivals")
    if isinstance(rivals, (list, dict)):
        if isinstance(rivals, dict):
            rivals = [rivals[k] for k in sorted(rivals.keys(), key=str)]
        normalized_rivals = []
        for rival in rivals:
            if isinstance(rival, dict):
                normalized_rivals.append({
                    "name": str(rival.get("name", "")),
                    "wins": int(rival.get("wins", 0)),
                    "losses": int(rival.get("losses", 0)),
                    "netGold": int(rival.get("netGold", 0)),
                })
        result["rivals"] = normalized_rivals

    return result


def _normalize_tournament(raw: dict) -> dict:
    """Normalize a single raw tournament record into a clean Python dict.

    Args:
        raw: Raw dict decoded from a single Lua tournament entry.

    Returns:
        Normalized tournament dict with all expected fields present.
    """
    if not isinstance(raw, dict):
        return {}

    # Normalize players list
    players_raw = raw.get("players", [])
    if isinstance(players_raw, dict):
        players_raw = [players_raw[k] for k in sorted(players_raw.keys(), key=str)]
    players = [str(p) for p in players_raw if p is not None]

    # Normalize prizes list
    prizes_raw = raw.get("prizes", [])
    if isinstance(prizes_raw, dict):
        prizes_raw = [prizes_raw[k] for k in sorted(prizes_raw.keys(), key=str)]
    prizes = []
    for prize in prizes_raw:
        if isinstance(prize, dict):
            prizes.append({
                "player": str(prize.get("player", "")),
                "amount": int(prize.get("amount", 0)),
                "place": int(prize.get("place", 0)),
            })

    # Sort prizes by place
    prizes.sort(key=lambda p: p["place"])

    # Normalize bracket
    bracket_raw = raw.get("bracket", {})
    if not isinstance(bracket_raw, dict):
        bracket_raw = {}
    bracket: dict = {}
    for round_key, matches in bracket_raw.items():
        if isinstance(matches, dict):
            matches = [matches[k] for k in sorted(matches.keys(), key=str)]
        if isinstance(matches, list):
            norm_matches = []
            for m in matches:
                if isinstance(m, dict):
                    norm_matches.append({
                        "winner": str(m.get("winner", "")),
                        "loser": str(m.get("loser", "")),
                    })
            bracket[str(round_key)] = norm_matches

    return {
        "id": str(raw.get("id", "")),
        "name": str(raw.get("name", "")),
        "mode": str(raw.get("mode", "")),
        "format": str(raw.get("format", "")),
        "buyIn": int(raw.get("buyIn", 0)),
        "maxPlayers": int(raw.get("maxPlayers", 0)),
        "players": players,
        "bracket": bracket,
        "prizePool": int(raw.get("prizePool", 0)),
        "prizes": prizes,
        "status": str(raw.get("status", "")),
        "startTime": int(raw.get("startTime", 0)),
        "endTime": int(raw.get("endTime", 0)),
    }


def parse_tournaments(data: dict) -> list[dict]:
    """Extract and normalize tournament records from a parsed SavedVariables dict.

    Args:
        data: Full decoded Lua table as a Python dict (VoidstormGambaDB).

    Returns:
        List of normalized tournament dicts, empty if none present.
    """
    raw_tournaments = data.get("tournaments")
    if not isinstance(raw_tournaments, dict):
        return []

    result = []
    for _key, raw_t in raw_tournaments.items():
        if isinstance(raw_t, dict):
            normalized = _normalize_tournament(raw_t)
            if normalized.get("id"):
                result.append(normalized)

    # Sort by startTime for deterministic ordering
    result.sort(key=lambda t: t.get("startTime", 0))
    return result


def parse_achievements(data: dict) -> dict[str, dict]:
    """Extract and normalize achievement records from a parsed SavedVariables dict.

    Args:
        data: Full decoded Lua table as a Python dict (VoidstormGambaDB).

    Returns:
        Dict mapping achievement key -> {unlockedAt: int}, empty if none present.
    """
    raw_achievements = data.get("achievements")
    if not isinstance(raw_achievements, dict):
        return {}

    result: dict[str, dict] = {}
    for ach_key, ach_data in raw_achievements.items():
        if isinstance(ach_data, dict):
            result[str(ach_key)] = {
                "unlockedAt": int(ach_data.get("unlockedAt", 0)),
            }
    return result


def _normalize_league_standing(raw: dict) -> dict:
    """Normalize a single league standing entry.

    Args:
        raw: Raw dict for one standing row.

    Returns:
        Normalized standing dict with all fields present and typed.
    """
    return {
        "name": str(raw.get("name", "")),
        "points": int(raw.get("points", 0)),
        "wins": int(raw.get("wins", 0)),
        "losses": int(raw.get("losses", 0)),
        "draws": int(raw.get("draws", 0)),
        "netGold": int(raw.get("netGold", 0)),
    }


def _normalize_league(league_key: str, raw: dict) -> dict:
    """Normalize a single raw league record into a clean Python dict.

    Args:
        league_key: The Lua table key identifying this league.
        raw: Raw dict decoded from a single Lua league entry.

    Returns:
        Normalized league dict with all expected fields present.
    """
    if not isinstance(raw, dict):
        return {}

    # Normalize standings — keyed by integer index in Lua
    standings_raw = raw.get("standings", {})
    standings: list[dict] = []
    if isinstance(standings_raw, dict):
        for k in sorted(standings_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            entry = standings_raw[k]
            if isinstance(entry, dict):
                standings.append(_normalize_league_standing(entry))
    elif isinstance(standings_raw, list):
        for entry in standings_raw:
            if isinstance(entry, dict):
                standings.append(_normalize_league_standing(entry))

    # Normalize history list
    history_raw = raw.get("history", {})
    history: list[dict] = []
    if isinstance(history_raw, dict):
        for k in sorted(history_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            entry = history_raw[k]
            if isinstance(entry, dict):
                history.append({
                    "season": int(entry.get("season", 0)),
                    "winner": str(entry.get("winner", "")),
                    "standings": entry.get("standings", []),
                })
    elif isinstance(history_raw, list):
        for entry in history_raw:
            if isinstance(entry, dict):
                history.append({
                    "season": int(entry.get("season", 0)),
                    "winner": str(entry.get("winner", "")),
                    "standings": entry.get("standings", []),
                })

    return {
        "leagueKey": str(league_key),
        "name": str(raw.get("name", "")),
        "guild": str(raw.get("guild", "")),
        "season": int(raw.get("season", 0)),
        "standings": standings,
        "history": history,
        "startedAt": int(raw.get("startedAt", 0)),
    }


def parse_leagues(data: dict) -> list[dict]:
    """Extract and normalize league records from a parsed SavedVariables dict.

    Args:
        data: Full decoded Lua table as a Python dict (VoidstormGambaDB).

    Returns:
        List of normalized league dicts, empty if none present.
    """
    raw_leagues = data.get("leagues")
    if not isinstance(raw_leagues, dict):
        return []

    result = []
    for league_key, raw_league in raw_leagues.items():
        if isinstance(raw_league, dict):
            normalized = _normalize_league(league_key, raw_league)
            if normalized.get("name"):
                result.append(normalized)

    # Sort by startedAt for deterministic ordering
    result.sort(key=lambda lg: lg.get("startedAt", 0))
    return result


def _normalize_challenge(raw: dict) -> dict:
    """Normalize a single challenge record.

    Args:
        raw: Raw dict for one challenge entry.

    Returns:
        Normalized challenge dict with all fields present and typed.
    """
    return {
        "challenger": str(raw.get("challenger", "")),
        "opponent": str(raw.get("opponent", "")),
        "mode": str(raw.get("mode", "")),
        "wager": int(raw.get("wager", 0)),
        "result": str(raw.get("result", "")),
        "timestamp": int(raw.get("timestamp", 0)),
    }


def parse_challenges(data: dict) -> list[dict]:
    """Extract and normalize challenge records from a parsed SavedVariables dict.

    Args:
        data: Full decoded Lua table as a Python dict (VoidstormGambaDB).

    Returns:
        List of normalized challenge dicts, empty if none present.
    """
    raw_challenges = data.get("challenges")
    if not isinstance(raw_challenges, (dict, list)):
        return []

    entries: list = []
    if isinstance(raw_challenges, dict):
        for k in sorted(raw_challenges.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            entries.append(raw_challenges[k])
    else:
        entries = list(raw_challenges)

    result = []
    for entry in entries:
        if isinstance(entry, dict):
            result.append(_normalize_challenge(entry))

    return result


def _normalize_audit_entry(raw: dict) -> dict:
    """Normalize a single audit log entry.

    Args:
        raw: Raw dict for one audit log entry.

    Returns:
        Normalized audit entry dict with all fields present and typed.
    """
    # Normalize players list (may be a Lua sequential table -> dict with int keys)
    players_raw = raw.get("players", [])
    if isinstance(players_raw, dict):
        players_raw = [players_raw[k] for k in sorted(players_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)]
    players = [str(p) for p in players_raw if p is not None]

    # Normalize amounts list
    amounts_raw = raw.get("amounts", [])
    if isinstance(amounts_raw, dict):
        amounts_raw = [amounts_raw[k] for k in sorted(amounts_raw.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)]
    amounts = [int(a) for a in amounts_raw if a is not None]

    return {
        "timestamp": int(raw.get("timestamp", 0)),
        "eventType": str(raw.get("eventType", "")),
        "players": players,
        "mode": str(raw.get("mode", "")),
        "amounts": amounts,
        "result": str(raw.get("result", "")),
        "severity": str(raw.get("severity", "INFO")),
    }


def parse_audit_log(data: dict) -> list[dict]:
    """Extract and normalize audit log entries from a parsed SavedVariables dict.

    Args:
        data: Full decoded Lua table as a Python dict (VoidstormGambaDB).

    Returns:
        List of normalized audit entry dicts, empty if none present.
    """
    raw_audit = data.get("auditLog")
    if not isinstance(raw_audit, (dict, list)):
        return []

    entries: list = []
    if isinstance(raw_audit, dict):
        for k in sorted(raw_audit.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            entries.append(raw_audit[k])
    else:
        entries = list(raw_audit)

    result = []
    for entry in entries:
        if isinstance(entry, dict):
            result.append(_normalize_audit_entry(entry))

    return result


def validate_savedvariables_meta(data: dict) -> dict | None:
    """Check _meta block for version and session count integrity."""
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        return None
    result = {
        "version": str(meta.get("version", "")),
        "lastSaveAt": int(meta.get("lastSaveAt", 0)),
        "sessionCount": int(meta.get("sessionCount", 0)),
    }
    sessions = data.get("sessions")
    if isinstance(sessions, (dict, list)):
        actual = len(sessions) if isinstance(sessions, list) else len(sessions)
        result["actualSessionCount"] = actual
        result["consistent"] = actual == result["sessionCount"]
    else:
        result["actualSessionCount"] = 0
        result["consistent"] = result["sessionCount"] == 0
    return result


def parse_savedvariables_full(
    filepath: str,
) -> tuple[list[dict], dict, list[dict], dict, list[dict], list[dict]]:
    """Parse a SavedVariables Lua file and return sessions, exportedStats,
    tournaments, achievements, leagues, and audit_log.

    Args:
        filepath: Absolute path to the SavedVariables .lua file.

    Returns:
        A 6-tuple of (sessions, exported_stats, tournaments, achievements,
        leagues, audit_log) where each optional component defaults to an
        empty collection when the respective block is absent from the file.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    try:
        eq_pos = content.index("=")
    except ValueError:
        return [], {}, [], {}, [], []

    raw_table = content[eq_pos + 1:].strip()
    if not raw_table:
        return [], {}, [], {}, [], []

    data = lua.decode(raw_table)

    if not data:
        return [], {}, [], {}, [], []

    # --- sessions ---
    sessions: list[dict] = []
    if "sessions" in data:
        raw_sessions = data["sessions"]
        if isinstance(raw_sessions, dict):
            raw_sessions = [raw_sessions[k] for k in sorted(raw_sessions.keys(), key=str)]
        if raw_sessions:
            sessions = raw_sessions

    # --- exportedStats ---
    exported_stats: dict = {}
    raw_exported = data.get("exportedStats")
    if isinstance(raw_exported, dict):
        exported_stats = _normalize_exported_stats(raw_exported)

    # --- tournaments ---
    tournaments = parse_tournaments(data)

    # --- achievements ---
    achievements = parse_achievements(data)

    # --- leagues ---
    leagues = parse_leagues(data)

    # --- audit log ---
    audit_log = parse_audit_log(data)

    return sessions, exported_stats, tournaments, achievements, leagues, audit_log


def parse_savedvariables(filepath: str) -> list[dict]:
    """Parse a SavedVariables Lua file and return only the sessions list.

    Args:
        filepath: Absolute path to the SavedVariables .lua file.

    Returns:
        List of session dicts, empty if the file has no sessions.
    """
    sessions, _, _, _, _, _ = parse_savedvariables_full(filepath)
    return sessions


def _normalize_encounters(raw: dict) -> dict:
    """Normalize raw encounters table from Lua into clean Python dicts.

    Args:
        raw: Raw dict decoded from the Lua encounters table.

    Returns:
        Dict mapping encounter ID -> normalized encounter dict.
    """
    if not isinstance(raw, dict):
        return {}
    result = {}
    for eid, enc in raw.items():
        if not isinstance(enc, dict):
            continue
        members_raw = enc.get("members", {})
        members = {}
        if isinstance(members_raw, dict):
            for name, info in members_raw.items():
                if isinstance(info, dict):
                    parts = str(name).split("-", 1)
                    members[str(name)] = {
                        "playerName": parts[0],
                        "realm": parts[1] if len(parts) > 1 else None,
                        "playerClass": str(info.get("class", "")) if info.get("class") else None,
                        "role": str(info.get("role", "")) if info.get("role") else None,
                        "joinedAt": int(info.get("joinedAt", 0)) if info.get("joinedAt") else None,
                        "leftAt": int(info.get("leftAt", 0)) if info.get("leftAt") else None,
                    }
        result[str(eid)] = {
            "id": str(eid),
            "timestamp": int(enc.get("timestamp", 0)),
            "duration": int(enc.get("duration", 0)) if enc.get("duration") else None,
            "contentType": str(enc.get("contentType", "")),
            "contentName": str(enc.get("contentName", "")) if enc.get("contentName") else None,
            "outcome": str(enc.get("outcome", "unknown")),
            "keystoneLevel": int(enc.get("keystoneLevel", 0)) if enc.get("keystoneLevel") else None,
            "keystoneTimed": bool(enc.get("keystoneTimed")) if enc.get("keystoneTimed") is not None else None,
            "members": members,
        }
    return result


def _normalize_tags(raw: dict) -> dict:
    """Normalize raw tags table from Lua into clean Python dicts.

    Args:
        raw: Raw dict decoded from the Lua tags table.

    Returns:
        Dict mapping player name -> list of normalized tag dicts.
    """
    if not isinstance(raw, dict):
        return {}
    result = {}
    for player_name, tags in raw.items():
        if isinstance(tags, dict):
            tags = [tags[k] for k in sorted(tags.keys(), key=lambda x: int(x) if str(x).isdigit() else 0)]
        if not isinstance(tags, list):
            continue
        normalized = []
        for entry in tags:
            if isinstance(entry, dict):
                normalized.append({
                    "tag": str(entry.get("tag", "")),
                    "encounterID": str(entry.get("encounterID", "")) if entry.get("encounterID") else None,
                    "timestamp": int(entry.get("timestamp", 0)),
                })
        if normalized:
            result[str(player_name)] = normalized
    return result


def parse_partyledger_export(filepath: str) -> dict | None:
    """Parse VoidstormPartyLedger SavedVariables and return exportedData.

    Args:
        filepath: Absolute path to the VoidstormPartyLedger SavedVariables .lua file.

    Returns:
        Normalized dict with keys exportedAt, version, encounters, tags,
        or None if the file cannot be parsed or has no exportedData.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    try:
        eq_pos = content.index("=")
    except ValueError:
        return None

    raw_table = content[eq_pos + 1:].strip()
    if not raw_table:
        return None

    raw = lua.decode(raw_table)
    if not isinstance(raw, dict):
        return None

    exported = raw.get("exportedData")
    if not isinstance(exported, dict):
        return None

    reporter = exported.get("reporter")

    return {
        "exportedAt": int(exported.get("exportedAt", 0)),
        "version": str(exported.get("version", "")),
        "reporter": str(reporter) if reporter else None,
        "encounters": _normalize_encounters(exported.get("encounters", {})),
        "tags": _normalize_tags(exported.get("tags", {})),
    }
