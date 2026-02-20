from slpp import slpp as lua


def parse_savedvariables(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    eq_pos = content.index("=")
    raw_table = content[eq_pos + 1 :].strip()
    data = lua.decode(raw_table)

    if not data or "sessions" not in data:
        return []

    sessions = data["sessions"]
    if isinstance(sessions, dict):
        sessions = [sessions[k] for k in sorted(sessions.keys())]

    return sessions if sessions else []
