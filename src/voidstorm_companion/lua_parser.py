from slpp import slpp as lua


def parse_savedvariables(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    try:
        eq_pos = content.index("=")
    except ValueError:
        return []

    raw_table = content[eq_pos + 1 :].strip()
    if not raw_table:
        return []

    data = lua.decode(raw_table)

    if not data or "sessions" not in data:
        return []

    sessions = data["sessions"]
    if isinstance(sessions, dict):
        sessions = [sessions[k] for k in sorted(sessions.keys(), key=str)]

    return sessions if sessions else []
