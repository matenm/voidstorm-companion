import json
import logging
import os
import threading
import webbrowser
from datetime import datetime, timezone

from voidstorm_companion.config import Config, CONFIG_DIR, STATE_PATH, HISTORY_PATH, STATS_PATH, set_autostart
from voidstorm_companion.lua_parser import (
    parse_savedvariables,
    parse_savedvariables_full,
    parse_leagues,
    parse_challenges,
    parse_audit_log,
    parse_partyledger_export,
)
from voidstorm_companion.diff_engine import DiffEngine
from voidstorm_companion.upload_history import UploadHistory
from voidstorm_companion.api_client import ApiClient, AuthError
from voidstorm_companion.stats_store import StatsStore
from voidstorm_companion.auth_flow import authenticate, get_stored_token, clear_token
from voidstorm_companion.file_watcher import SavedVariablesWatcher
from voidstorm_companion.tray import TrayApp
from voidstorm_companion.window_manager import WindowManager
from voidstorm_companion.group_sync import GroupSync
from voidstorm_companion.keys_integration import KeysIntegration
from voidstorm_companion import analytics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("voidstorm-companion")


def _derive_addon_path(sv_path: str) -> str | None:
    wow_root = sv_path
    for _ in range(5):
        wow_root = os.path.dirname(wow_root)
    candidate = os.path.join(wow_root, "Interface", "AddOns", "VoidstormMatchmaking")
    if os.path.isdir(candidate):
        return candidate
    return None


MODE_NAMES = {
    "DIFFERENCE": "Difference", "POT": "Pot Roll", "DEATHROLL": "Deathroll",
    "ODDEVEN": "Odd/Even", "ELIMINATION": "Elimination", "LOTTERY": "Lottery",
    "POKER": "Poker", "DOUBLEORNOTHING": "Double or Nothing",
    "BLACKJACK": "Blackjack", "COINFLIP": "Coin Flip", "WAR": "War",
    "SLOTS": "Slots",
    "ROULETTE": "Roulette",
}

FORMAT_NAMES = {
    "SINGLE_ELIM": "Single Elimination",
    "DOUBLE_ELIM": "Double Elimination",
    "ROUND_ROBIN": "Round Robin",
    "SWISS": "Swiss",
}

ACHIEVEMENT_DESCRIPTIONS = {
    "FIRST_BLOOD": ("Win your very first gambling session.", 10),
    "CENTURY_CLUB": ("Participate in 100 gambling sessions.", 25),
    "HIGH_ROLLER": ("Wager over 1,000,000g in a single session.", 50),
    "LUCKY_STREAK": ("Win 10 sessions in a row.", 30),
    "BROKE_THE_BANK": ("Win a jackpot on Slots.", 40),
    "TOURNAMENT_WINNER": ("Win a tournament.", 35),
    "POKER_FACE": ("Win a Poker tournament.", 30),
    "ALL_IN": ("Go all-in and win.", 20),
}

SLOT_SYMBOL_EMOJI = {
    "cherry": "\U0001f352",
    "lemon": "\U0001f34b",
    "bar": "\U0001f4ca",
    "seven": "7\ufe0f\u20e3",
    "diamond": "\U0001f48e",
    "skull": "\U0001f480",
}

ROULETTE_COLOR_EMOJI = {
    "red": "\U0001f534",     # red circle
    "black": "\u26ab",       # black circle
    "green": "\U0001f7e2",   # green circle
}


def format_tournament_embed(tournament_data: dict) -> dict:
    """Build a Discord embed dict for a completed tournament.

    Args:
        tournament_data: Normalized tournament dict as produced by
            ``lua_parser.parse_tournaments`` or a compatible structure.

    Returns:
        Discord embed dict suitable for inclusion in a webhook payload.
    """
    name = tournament_data.get("name", "Unknown Tournament")
    mode_key = tournament_data.get("mode", "")
    fmt_key = tournament_data.get("format", "")
    mode = MODE_NAMES.get(mode_key, mode_key or "Unknown")
    fmt = FORMAT_NAMES.get(fmt_key, fmt_key or "Unknown")
    players = tournament_data.get("players", [])
    num_players = len(players)
    buy_in = tournament_data.get("buyIn", 0)
    prize_pool = tournament_data.get("prizePool", 0)
    prizes = tournament_data.get("prizes", [])

    # Build description
    description_parts = [f"{mode} | {fmt} | {num_players} players"]

    # Bracket summary for bracket-format tournaments
    bracket = tournament_data.get("bracket", {})
    if bracket and fmt_key in ("SINGLE_ELIM", "DOUBLE_ELIM"):
        round_count = len(bracket)
        description_parts.append(f"Bracket: {round_count} round(s)")

    description = "\n".join(description_parts)

    # Placement fields
    place_medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
    fields = []

    prizes_by_place = {p["place"]: p for p in prizes if isinstance(p, dict)}
    for place in sorted(prizes_by_place.keys()):
        prize = prizes_by_place[place]
        medal = place_medals.get(place, f"#{place}")
        player_name = prize.get("player", "Unknown")
        amount = prize.get("amount", 0)
        fields.append({
            "name": f"{medal} {'1st' if place == 1 else '2nd' if place == 2 else '3rd' if place == 3 else f'{place}th'} Place",
            "value": f"{player_name} (+{amount:,}g)",
            "inline": True,
        })

    # Summary field for buy-in and prize pool
    fields.append({
        "name": "Buy-in / Prize Pool",
        "value": f"{buy_in:,}g / {prize_pool:,}g",
        "inline": False,
    })

    return {
        "title": f"\U0001f3c6 Tournament Complete \u2014 {name}",
        "description": description,
        "color": 0xFFD700,
        "fields": fields,
    }


def format_achievement_embed(achievement_data: dict) -> dict:
    """Build a Discord embed dict for a newly unlocked achievement.

    Args:
        achievement_data: Dict with keys:
            - ``achievementKey``: Internal achievement key string.
            - ``achievementName``: Human-readable display name.
            - ``playerName``: Name of the player who unlocked the achievement.
            - ``unlockedAt``: Unix timestamp when it was unlocked (optional).
            - ``iconUrl``: URL to the achievement icon image (optional).
            - ``points``: Integer point value of the achievement (optional).

    Returns:
        Discord embed dict suitable for inclusion in a webhook payload.
    """
    achievement_key = achievement_data.get("achievementKey", "")
    achievement_name = achievement_data.get("achievementName", achievement_key)
    player_name = achievement_data.get("playerName", "Unknown")
    icon_url = achievement_data.get("iconUrl", "")
    points = int(achievement_data.get("points", 0))

    # Look up description and default points from the registry
    ach_desc, default_points = ACHIEVEMENT_DESCRIPTIONS.get(achievement_key, ("", 10))
    if not points:
        points = default_points

    # Gold color for rare achievements (30+ points), purple otherwise
    color = 0xFFD700 if points >= 30 else 0x9B59B6

    fields = []
    if ach_desc:
        fields.append({
            "name": "Description",
            "value": ach_desc,
            "inline": False,
        })
    if points:
        fields.append({
            "name": "Points",
            "value": str(points),
            "inline": True,
        })

    embed: dict = {
        "title": "\U0001f3c5 Achievement Unlocked!",
        "description": f"{player_name} earned **{achievement_name}**",
        "color": color,
        "fields": fields,
    }

    if icon_url:
        embed["thumbnail"] = {"url": icon_url}

    return embed


def format_slots_embed(session: dict) -> dict:
    """Build a Discord embed dict for a SLOTS session."""
    rounds = session.get("rounds", [])
    last_round = rounds[-1] if rounds else {}
    results = last_round.get("results", {})

    reel1 = SLOT_SYMBOL_EMOJI.get(results.get("reel1", ""), "?")
    reel2 = SLOT_SYMBOL_EMOJI.get(results.get("reel2", ""), "?")
    reel3 = SLOT_SYMBOL_EMOJI.get(results.get("reel3", ""), "?")
    reels_line = f"{reel1} {reel2} {reel3}"

    is_jackpot = results.get("jackpot", False)
    winner = results.get("winner", "")
    amount = results.get("amount", 0)
    pot = results.get("pot", 0)

    fields = []

    # Reel result
    fields.append({"name": "Reels", "value": reels_line, "inline": False})

    # Players and payouts
    players = last_round.get("players", [])
    payouts = []
    for p in players:
        pname = p.get("name", "Unknown")
        ppayout = p.get("payout", 0)
        pbet = p.get("bet", 0)
        if ppayout > 0:
            payouts.append(f"**{pname}**: +{ppayout:,}g (bet {pbet:,}g)")
        else:
            payouts.append(f"{pname}: -{pbet:,}g")
    if payouts:
        fields.append({"name": "Players", "value": "\n".join(payouts), "inline": False})

    if pot:
        fields.append({"name": "Pot", "value": f"{pot:,}g", "inline": True})

    if is_jackpot:
        jackpot_amount = results.get("jackpotAmount", amount)
        title = "\U0001f3b0 JACKPOT! \U0001f3b0 Slots Result"
        description = f"\U0001f389 **{winner}** hit the JACKPOT for **{jackpot_amount:,}g**! \U0001f389"
        color = 0xffd700  # gold
    else:
        title = "\U0001f3b0 Slots Result"
        summary = results.get("summary", "")
        description = summary or ("Game completed" if not winner else f"{winner} wins {amount:,}g!")
        color = 0x89b4fa

    return {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
    }


def format_roulette_embed(session: dict) -> dict:
    """Build a Discord embed dict for a ROULETTE session."""
    rounds = session.get("rounds", [])
    last_round = rounds[-1] if rounds else {}
    results = last_round.get("results", {})
    players = last_round.get("players", [])

    pocket = results.get("pocket", "?")
    color = results.get("color", "")
    color_emoji = ROULETTE_COLOR_EMOJI.get(color, "")
    pot = results.get("pot", 0)
    winner = results.get("winner", "")
    amount = results.get("amount", 0)
    summary = results.get("summary", "")

    # Determine pocket properties
    props = []
    if isinstance(pocket, int) and pocket > 0:
        props.append("Odd" if pocket % 2 != 0 else "Even")
        props.append("High (19-36)" if pocket >= 19 else "Low (1-18)")
        if pocket <= 12:
            props.append("1st Dozen")
        elif pocket <= 24:
            props.append("2nd Dozen")
        else:
            props.append("3rd Dozen")
    elif isinstance(pocket, int) and pocket == 0:
        props.append("Zero")

    fields = []
    fields.append({
        "name": "Result",
        "value": f"{color_emoji} **{pocket}** ({color.title()})" if color else f"**{pocket}**",
        "inline": True,
    })
    if props:
        fields.append({"name": "Properties", "value": " | ".join(props), "inline": True})

    # Player payouts
    payouts_lines = []
    big_win = False
    for p in players:
        name = p.get("name", "Unknown")
        bet = p.get("bet", 0)
        payout = p.get("payout", 0)
        bet_type = p.get("betType", "")
        bet_label = f" ({bet_type})" if bet_type else ""
        if payout > 0:
            payouts_lines.append(f"**{name}**: +{payout:,}g{bet_label} (bet {bet:,}g)")
            if payout >= 5000:
                big_win = True
        else:
            payouts_lines.append(f"{name}: -{bet:,}g{bet_label}")

    if payouts_lines:
        fields.append({"name": "Players", "value": "\n".join(payouts_lines), "inline": False})

    if pot:
        fields.append({"name": "Pot", "value": f"{pot:,}g", "inline": True})

    if big_win:
        title = "\U0001f3af BIG WIN! \U0001f3b0 Roulette Result"
        description = (
            f"\U0001f389 **{winner}** wins big on roulette for **{amount:,}g**!"
            if winner else "Big win on roulette!"
        )
        embed_color = 0xffd700
    else:
        title = "\U0001f3af Roulette Result"
        description = summary or (f"{winner} wins {amount:,}g!" if winner else "Game completed")
        embed_color = 0x89b4fa

    return {
        "title": title,
        "description": description,
        "color": embed_color,
        "fields": fields,
    }


def format_webhook_embed(session: dict) -> dict:
    """Build a Discord embed dict for any session, tournament, or achievement.

    Dispatches to the appropriate formatter based on the ``"type"`` key (for
    non-session payloads) or the session ``"mode"`` key.

    Args:
        session: Session dict (or a dict with a ``"type"`` key of
            ``"tournament"`` or ``"achievement"``).

    Returns:
        Discord embed dict.
    """
    embed_type = session.get("type", "")

    if embed_type == "tournament":
        return format_tournament_embed(session)

    if embed_type == "achievement":
        return format_achievement_embed(session)

    if embed_type == "league":
        return format_league_embed(session)

    mode_key = session.get("mode", "")

    if mode_key == "SLOTS":
        return format_slots_embed(session)

    elif mode_key == "ROULETTE":
        return format_roulette_embed(session)

    mode = MODE_NAMES.get(mode_key, mode_key or "Unknown")
    wager = session.get("wager", 0)
    rounds = session.get("rounds", [])
    last_round = rounds[-1] if rounds else {}
    results = last_round.get("results", {})
    summary = results.get("summary", "")
    winner = results.get("winner", "")
    fields = []
    if winner:
        fields.append({"name": "Winner", "value": winner, "inline": True})
    if wager:
        fields.append({"name": "Wager", "value": f"{wager:,}g", "inline": True})
    return {
        "title": f"{mode} Result",
        "description": summary or "Game completed",
        "color": 0x89b4fa,
        "fields": fields,
    }


def format_stats_summary_embed(player_stats: dict) -> dict:
    """Build a Discord embed dict summarising a player's lifetime stats.

    Args:
        player_stats: Dict with keys ``playerName``, ``realm``, ``lifetime``,
            ``modeBreakdown``, ``recentSessions``, and ``rivals`` — as
            produced by :func:`build_player_stats`.

    Returns:
        Discord embed dict suitable for inclusion in a webhook payload.
    """
    player_name = player_stats.get("playerName", "Unknown")
    realm = player_stats.get("realm", "")
    lifetime = player_stats.get("lifetime", {})
    mode_breakdown = player_stats.get("modeBreakdown", {})
    recent_sessions = player_stats.get("recentSessions", [])
    rivals = player_stats.get("rivals", [])

    wins = lifetime.get("wins", 0)
    losses = lifetime.get("losses", 0)
    total_games = wins + losses
    win_rate = (wins / total_games * 100) if total_games > 0 else 0.0
    net_profit = lifetime.get("netProfit", 0)

    # Session P/L from recentSessions
    recent_pl = sum(r.get("netProfit", 0) for r in recent_sessions)
    pl_sign = "+" if recent_pl >= 0 else ""
    pl_color_label = "\U0001f7e2" if recent_pl >= 0 else "\U0001f534"  # green / red circle

    # Favorite mode (most played)
    favorite_mode = ""
    if mode_breakdown:
        favorite_mode_key = max(mode_breakdown, key=lambda k: mode_breakdown[k].get("played", 0))
        favorite_mode = MODE_NAMES.get(favorite_mode_key, favorite_mode_key)

    # Top rival (highest wins)
    top_rival = ""
    if rivals:
        best = max(rivals, key=lambda r: r.get("wins", 0))
        top_rival = best.get("name", "")

    # Current streak from recentSessions (consecutive same result from most recent)
    streak = 0
    if recent_sessions:
        first_result = recent_sessions[0].get("result", "")
        for r in recent_sessions:
            if r.get("result", "") == first_result:
                streak += 1 if first_result == "win" else -1
            else:
                break

    fields = []

    # Session P/L
    fields.append({
        "name": f"{pl_color_label} Session P/L",
        "value": f"{pl_sign}{recent_pl:,}g",
        "inline": True,
    })

    # Lifetime W/L and win rate
    fields.append({
        "name": "\U0001f3c6 Lifetime W/L",
        "value": f"{wins}W / {losses}L ({win_rate:.1f}%)",
        "inline": True,
    })

    # Net profit
    profit_sign = "+" if net_profit >= 0 else ""
    fields.append({
        "name": "\U0001f4b0 Net Profit",
        "value": f"{profit_sign}{net_profit:,}g",
        "inline": True,
    })

    # Favorite mode
    if favorite_mode:
        fields.append({
            "name": "\U0001f3ae Favorite Mode",
            "value": favorite_mode,
            "inline": True,
        })

    # Top rival
    if top_rival:
        fields.append({
            "name": "\u2694\ufe0f Top Rival",
            "value": top_rival,
            "inline": True,
        })

    # Current streak
    if streak != 0:
        streak_label = f"+{streak} win streak" if streak > 0 else f"{streak} loss streak"
        fields.append({
            "name": "\U0001f525 Current Streak",
            "value": streak_label,
            "inline": True,
        })

    title_name = f"{player_name}-{realm}" if realm else player_name

    return {
        "title": f"\U0001f4ca Stats Update \u2014 {title_name}",
        "color": 0x3498DB,
        "fields": fields,
    }


def _standard_footer(timestamp: int | None = None) -> dict:
    """Build a standardized footer dict for Discord embeds.

    Args:
        timestamp: Optional Unix timestamp to include in the footer text.

    Returns:
        Footer dict with ``text`` key ready for use in a Discord embed.
    """
    if timestamp:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        return {"text": f"Voidstorm Gambling \u2022 {ts_str}"}
    return {"text": "Voidstorm Gambling"}


def _apply_verbosity(embed: dict, verbosity: str) -> dict:
    """Adjust embed fields according to the configured verbosity level.

    Args:
        embed: Discord embed dict to adjust in-place (a copy is returned).
        verbosity: One of ``"minimal"``, ``"normal"``, or ``"verbose"``.
            - ``"minimal"``: Strip all fields; keep only title, description,
              color, and footer.
            - ``"normal"``: Return the embed unchanged (current behavior).
            - ``"verbose"``: Return the embed unchanged; callers may add
              extra fields before or after calling this function.

    Returns:
        Adjusted embed dict.  The original is not mutated.
    """
    embed = dict(embed)
    if verbosity == "minimal":
        embed.pop("fields", None)
        embed.pop("thumbnail", None)
        embed.pop("author", None)
    # "normal" and "verbose" are no-ops here — verbose additions are handled
    # per-formatter when the verbosity value is explicitly checked.
    return embed


def format_league_embed(league: dict) -> dict:
    """Build a Discord embed dict for a completed league season.

    Args:
        league: Normalized league dict as produced by
            ``lua_parser.parse_leagues`` or a compatible structure.

    Returns:
        Discord embed dict suitable for inclusion in a webhook payload.
    """
    name = league.get("name", "Unknown League")
    guild = league.get("guild", "")
    season = league.get("season", 0)
    standings = league.get("standings", [])

    medal_emojis = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}

    fields = []

    # Build standings table
    table_lines = []
    mvp_name = ""
    mvp_points = -1
    for rank, entry in enumerate(standings, start=1):
        player = entry.get("name", "Unknown")
        points = entry.get("points", 0)
        wins = entry.get("wins", 0)
        losses = entry.get("losses", 0)
        draws = entry.get("draws", 0)
        net_gold = entry.get("netGold", 0)
        medal = medal_emojis.get(rank, f"#{rank}")
        net_sign = "+" if net_gold >= 0 else ""
        table_lines.append(
            f"{medal} **{player}** — {points}pts ({wins}W/{losses}L/{draws}D) {net_sign}{net_gold:,}g"
        )
        if points > mvp_points:
            mvp_points = points
            mvp_name = player

    if table_lines:
        fields.append({
            "name": "Final Standings",
            "value": "\n".join(table_lines),
            "inline": False,
        })

    if mvp_name:
        fields.append({
            "name": "\U0001f31f MVP",
            "value": f"{mvp_name} ({mvp_points} points)",
            "inline": True,
        })

    footer_text = f"Season {season}"
    if guild:
        footer_text = f"Season {season} \u2022 {guild}"

    return {
        "title": f"\U0001f3c5 League Season Complete \u2014 {name}",
        "color": 0xFFD700,
        "fields": fields,
        "footer": {"text": footer_text},
    }


def format_league_milestone_embed(player_name: str, league_name: str) -> dict:
    """Build a Discord embed dict for a league lead-change milestone.

    Args:
        player_name: Name of the player who has taken the lead.
        league_name: Display name of the league.

    Returns:
        Discord embed dict suitable for inclusion in a webhook payload.
    """
    return {
        "title": f"\U0001f451 {player_name} takes the lead in {league_name}!",
        "color": 0xFFD700,
        "fields": [],
    }


def build_player_stats(exported_stats: dict, player_name: str = "", realm: str = "") -> dict:
    """Build the playerStats payload from parsed exportedStats.

    Args:
        exported_stats: Dict returned by :func:`lua_parser._normalize_exported_stats`.
        player_name: Character name to embed in the payload.
        realm: Realm name to embed in the payload.

    Returns:
        Dict suitable for the ``playerStats`` key in the upload payload.
    """
    return {
        "playerName": player_name,
        "realm": realm,
        "lifetime": exported_stats.get("lifetime", {}),
        "modeBreakdown": exported_stats.get("modeBreakdown", {}),
        "recentSessions": exported_stats.get("recentSessions", []),
        "rivals": exported_stats.get("rivals", []),
    }


_STATS_SUMMARY_STATE_PATH = os.path.join(
    os.path.expanduser("~"), ".voidstorm-companion", "stats_summary_state.json"
)


class StatsSummaryState:
    """Tracks how many sessions have been uploaded since the last stats summary.

    Args:
        state_path: Path to the JSON file used to persist state between runs.
    """

    def __init__(self, state_path: str = _STATS_SUMMARY_STATE_PATH):
        self._path = state_path
        self._sessions_since_summary: int = 0
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                self._sessions_since_summary = int(
                    data.get("sessions_since_summary", 0)
                )
            except (json.JSONDecodeError, OSError, ValueError):
                pass

    def _save(self):
        import tempfile
        dir_ = os.path.dirname(self._path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"sessions_since_summary": self._sessions_since_summary}, f)
            os.replace(tmp_path, self._path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @property
    def sessions_since_summary(self) -> int:
        """Number of uploaded sessions accumulated since last summary post."""
        return self._sessions_since_summary

    def add_sessions(self, count: int):
        """Increment the counter by *count* and persist to disk.

        Args:
            count: Number of newly uploaded sessions to add.
        """
        self._sessions_since_summary += count
        self._save()

    def reset(self):
        """Reset the counter to zero and persist to disk."""
        self._sessions_since_summary = 0
        self._save()

    def should_post_summary(self, threshold: int) -> bool:
        """Return ``True`` when enough sessions have accumulated.

        Args:
            threshold: Minimum number of sessions required to trigger a summary.

        Returns:
            ``True`` when :attr:`sessions_since_summary` >= *threshold*.
        """
        return self._sessions_since_summary >= threshold


_PARTYLEDGER_STATE_PATH = os.path.join(CONFIG_DIR, "partyledger_state.json")


class PartyLedgerState:
    """Tracks the last-uploaded exportedAt timestamp for PartyLedger data.

    Args:
        state_path: Path to the JSON file used to persist state between runs.
    """

    def __init__(self, state_path: str = _PARTYLEDGER_STATE_PATH):
        self._path = state_path
        self._last_exported_at: int = 0
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                self._last_exported_at = int(data.get("lastExportedAt", 0))
            except (json.JSONDecodeError, OSError, ValueError):
                pass

    def _save(self):
        import tempfile
        dir_ = os.path.dirname(self._path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"lastExportedAt": self._last_exported_at}, f)
            os.replace(tmp_path, self._path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @property
    def last_exported_at(self) -> int:
        """Unix timestamp of the last successfully uploaded export."""
        return self._last_exported_at

    def update(self, exported_at: int):
        """Record a successful upload and persist to disk.

        Args:
            exported_at: The exportedAt timestamp from the uploaded payload.
        """
        self._last_exported_at = exported_at
        self._save()

    def is_newer(self, exported_at: int) -> bool:
        """Return True when the given timestamp is newer than the last upload.

        Args:
            exported_at: Candidate exportedAt timestamp to compare.
        """
        return exported_at > self._last_exported_at


class App:
    def __init__(self):
        self.config = Config()
        self.diff = DiffEngine(STATE_PATH)
        self.history = UploadHistory(HISTORY_PATH)
        self.stats = StatsStore(STATS_PATH)
        self.summary_state = StatsSummaryState()
        self.watchers: dict[str, SavedVariablesWatcher] = {}
        self.partyledger_watchers: dict[str, SavedVariablesWatcher] = {}
        self.partyledger_state = PartyLedgerState()
        self._reputation_retry_paths: set[str] = set()
        self.tray: TrayApp | None = None
        self.client: ApiClient | None = None
        self._client_lock = threading.Lock()
        self.window_manager = WindowManager()
        self._group_sync: GroupSync | None = None
        self._keys_integration: KeysIntegration | None = None
        self._quit_event = threading.Event()

    def _reputation_sync_path(self) -> str | None:
        if not self.config.partyledger_paths:
            return None
        sv_path = self.config.partyledger_paths[0]
        parts = sv_path.replace("\\", "/").split("/WTF/")
        if len(parts) < 2:
            return None
        wow_root = parts[0]
        return os.path.join(wow_root, "Interface", "AddOns", "VoidstormPartyLedger", "VoidstormReputationSync.lua")

    def _write_reputation_sync(self, player_data: dict) -> None:
        import time
        out_path = self._reputation_sync_path()
        if not out_path:
            log.warning("Cannot determine reputation sync path")
            return
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        synced_at = int(time.time())
        lines: list[str] = []
        lines.append("VoidstormReputationSyncDB = {")
        lines.append(f"\tsyncedAt = {synced_at},")
        lines.append("\tplayers = {")
        for name, data in player_data.items():
            escaped = name.replace('"', '\\"')
            lines.append(f'\t\t["{escaped}"] = {{')
            reliability = data.get("reliability")
            if reliability is not None:
                lines.append(f"\t\t\treliability = {reliability},")
            else:
                lines.append("\t\t\treliability = nil,")
            lines.append(f'\t\t\ttotalEncounters = {int(data.get("totalEncounters", 0))},')
            lines.append(f'\t\t\tcompletedEncounters = {int(data.get("completedEncounters", 0))},')
            lines.append(f'\t\t\tendorsements = {int(data.get("endorsements", 0))},')
            lines.append(f'\t\t\tuniqueEndorsers = {int(data.get("uniqueEndorsers", 0))},')
            top_tags = data.get("topTags") or {}
            lines.append("\t\t\ttopTags = {")
            for tag, count in top_tags.items():
                safe_tag = str(tag).replace('"', '\\"')
                lines.append(f'\t\t\t\t["{safe_tag}"] = {int(count)},')
            lines.append("\t\t\t},")
            negative_tags = data.get("negativeTags") or {}
            lines.append("\t\t\tnegativeTags = {")
            for tag, count in negative_tags.items():
                safe_tag = str(tag).replace('"', '\\"')
                lines.append(f'\t\t\t\t["{safe_tag}"] = {int(count)},')
            lines.append("\t\t\t},")
            badges = data.get("badges") or []
            lines.append("\t\t\tbadges = {")
            for badge in badges:
                safe_badge = str(badge).replace('"', '\\"')
                lines.append(f'\t\t\t\t"{safe_badge}",')
            lines.append("\t\t\t},")
            lines.append("\t\t},")
        lines.append("\t},")
        lines.append("}")
        content = "\n".join(lines) + "\n"
        import tempfile
        dir_ = os.path.dirname(out_path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, out_path)
            log.info(f"Reputation sync written: {len(player_data)} player(s) -> {out_path}")
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _do_reputation_sync(self) -> None:
        with self._client_lock:
            client = self.client
        if not client:
            return
        paths = list(self.config.partyledger_paths)
        if not paths:
            return
        all_players: set[str] = set()
        for pl_path in paths:
            try:
                payload = parse_partyledger_export(pl_path)
                if not payload:
                    continue
                for enc in payload.get("encounters", {}).values():
                    for member_name in enc.get("members", {}).keys():
                        all_players.add(str(member_name))
            except Exception as e:
                log.warning(f"Reputation sync: failed to parse {pl_path}: {e}")
        if not all_players:
            return
        try:
            player_data = client.fetch_reputation_bulk(list(all_players))
        except Exception as e:
            log.warning(f"Reputation bulk fetch failed: {e}")
            return
        if not player_data:
            return
        try:
            self._write_reputation_sync(player_data)
        except Exception as e:
            log.error(f"Failed to write reputation sync file: {e}")

    def _ensure_auth(self) -> bool:
        token = get_stored_token()
        if token:
            with self._client_lock:
                self.client = ApiClient(self.config.api_url, token)
            return True
        return False

    def _start_group_sync(self):
        with self._client_lock:
            client = self.client
        if not client:
            return
        addon_path = None
        sv_dirs = []
        for sv_path in self.config.savedvariables_paths:
            if not addon_path:
                addon_path = _derive_addon_path(sv_path)
            sv_dir = os.path.dirname(sv_path)
            if os.path.isdir(sv_dir) and sv_dir not in sv_dirs:
                sv_dirs.append(sv_dir)
        if not addon_path:
            log.warning("GroupSync: addon path not found, skipping")
            return
        if self._group_sync:
            self._group_sync.stop()
        self._group_sync = GroupSync(self.config.api_url, client.token, addon_path, sv_dirs)
        self._group_sync.start()

    def _start_keys_integration(self):
        with self._client_lock:
            client = self.client
        if not client or not self.config.keys_paths:
            return
        for keys_path in self.config.keys_paths:
            wow_path = keys_path
            for _ in range(5):
                wow_path = os.path.dirname(wow_path)
            account = os.path.basename(os.path.dirname(os.path.dirname(keys_path)))
            if self._keys_integration:
                self._keys_integration.stop()
            self._keys_integration = KeysIntegration(wow_path, account, client)
            self._keys_integration.start()
            log.info(f"VoidstormKeys integration started for {account}")
            break

    def _do_login(self):
        threading.Thread(target=self._login_worker, daemon=True).start()

    def _login_worker(self):
        log.info("Starting Battle.net login flow...")
        if self.tray:
            self.tray.set_status("Logging in...")
        token = authenticate(self.config.api_url)
        if token:
            with self._client_lock:
                self.client = ApiClient(self.config.api_url, token)
            log.info("Login successful!")
            analytics.track("login")
            self._start_group_sync()
            if self.tray:
                self.tray.set_status("Authenticated", logged_in=True)
        else:
            log.error("Login failed or timed out")
            if self.tray:
                self.tray.set_status("Login failed", logged_in=False)

    def _do_logout(self):
        log.info("Logging out...")
        with self._client_lock:
            self.client = None
        clear_token()
        if self.tray:
            self.tray.set_status("Logged out", logged_in=False)

    def _do_upload(self, path: str | None = None, _is_retry: bool = False):
        paths = [path] if path else list(self.config.savedvariables_paths)
        if not paths:
            log.warning("No SavedVariables paths configured")
            return

        with self._client_lock:
            client = self.client
        if not client:
            if not self._ensure_auth():
                log.warning("Not authenticated — skipping upload")
                return
            with self._client_lock:
                client = self.client

        total_imported = 0
        total_skipped = 0

        for sv_path in paths:
            try:
                if self.tray:
                    self.tray.set_status("Parsing...")

                sessions, exported_stats, tournaments, achievements, leagues, audit_log = (
                    parse_savedvariables_full(sv_path)
                )
                self.stats.update(sessions)
                new_sessions = self.diff.filter_new(sessions)

                if not new_sessions:
                    log.info(f"No new sessions in {sv_path}")
                    continue

                log.info(f"Uploading {len(new_sessions)} new session(s) from {sv_path}...")
                if self.tray:
                    self.tray.set_status(f"Uploading {len(new_sessions)}...")

                player_stats: dict | None = None
                if exported_stats:
                    player_stats = build_player_stats(exported_stats)

                result = client.upload(
                    new_sessions,
                    player_stats=player_stats,
                    leagues=leagues if leagues else None,
                    challenges=None,  # challenges are uploaded via audit endpoint
                    audit_log=audit_log if audit_log else None,
                )

                # Upload audit log to dedicated endpoint when present
                if audit_log:
                    try:
                        client.upload_audit(audit_log)
                        log.info(f"Audit log uploaded: {len(audit_log)} entries")
                    except Exception as audit_err:
                        log.warning(f"Audit log upload failed: {audit_err}")

                # Post league webhook when league data is present
                if leagues and self.config.league_webhook_url:
                    threading.Thread(
                        target=self._fire_league_webhook,
                        args=(leagues,),
                        daemon=True,
                    ).start()

                uploaded_ids = [s["id"] for s in new_sessions]
                self.diff.mark_uploaded(uploaded_ids)

                imported = result.get('imported', 0)
                skipped = result.get('skipped', 0)
                total_imported += imported
                total_skipped += skipped

                log.info(f"Upload complete: {imported} imported, {skipped} skipped")

            except AuthError:
                if _is_retry:
                    log.error("Re-authentication failed — please log in manually")
                    self.history.record(0, 0, error="Auth failed")
                    if self.tray:
                        self.tray.set_status("Auth failed", logged_in=False)
                    self._update_tray_tooltip()
                    return
                log.warning("Token expired — re-authenticating...")
                with self._client_lock:
                    self.client = None
                clear_token()
                if self.tray:
                    self.tray.set_status("Re-authenticating...", logged_in=False)
                self._login_worker()
                with self._client_lock:
                    if self.client:
                        self._do_upload(path=path, _is_retry=True)
                return
            except FileNotFoundError:
                log.error(f"SavedVariables not found: {sv_path}")
                continue
            except Exception as e:
                log.error(f"Upload error for {sv_path}: {e}")
                self.history.record(0, 0, error=str(e))
                continue

        if total_imported or total_skipped:
            self.history.record(total_imported, total_skipped)
            analytics.track("upload", {"sessions": total_imported})
        if self.tray:
            self.tray.set_status(f"Synced {total_imported}" if total_imported else "Up to date")
        self._update_tray_tooltip()
        if total_imported and self.tray:
            self.tray.notify("Voidstorm Companion", f"Uploaded {total_imported} session(s)")
        if total_imported and self.config.webhook_url:
            # Determine whether to post a stats summary alongside session embeds
            self.summary_state.add_sessions(total_imported)
            post_summary = self.summary_state.should_post_summary(
                self.config.stats_summary_threshold
            )
            # Collect the most recently parsed player_stats for the summary
            _summary_player_stats: dict | None = None
            if post_summary:
                for sv_path in paths:
                    try:
                        _, _es, _, _, _, _ = parse_savedvariables_full(sv_path)
                        if _es:
                            _summary_player_stats = build_player_stats(_es)
                            break
                    except Exception:
                        pass
                self.summary_state.reset()
            threading.Thread(
                target=self._fire_webhook,
                args=(total_imported, new_sessions, _summary_player_stats if post_summary else None),
                daemon=True,
            ).start()

    def _do_upload_async(self, path: str | None = None):
        threading.Thread(target=self._do_upload, args=(path,), daemon=True).start()

    def _on_file_change(self, filepath: str):
        log.info(f"File change detected: {filepath}")
        if not self.config.auto_upload:
            log.info("Auto-upload disabled, skipping")
            return
        threading.Thread(target=self._do_upload, args=(filepath,), daemon=True).start()

    def _do_reputation_upload(self, path: str | None = None, _is_retry: bool = False):
        """Parse and upload PartyLedger reputation data.

        Args:
            path: Specific PartyLedger SavedVariables path to process.
                When ``None``, all configured ``partyledger_paths`` are tried.
            _is_retry: Internal flag to prevent infinite re-auth loops.
        """
        paths = [path] if path else list(self.config.partyledger_paths)
        if not paths:
            log.debug("No PartyLedger paths configured — skipping reputation upload")
            return

        with self._client_lock:
            client = self.client
        if not client:
            if not self._ensure_auth():
                log.warning("Not authenticated — skipping reputation upload")
                return
            with self._client_lock:
                client = self.client

        for pl_path in paths:
            try:
                payload = parse_partyledger_export(pl_path)
                if payload is None:
                    log.debug(f"No exportedData in {pl_path}")
                    continue

                exported_at = payload.get("exportedAt", 0)
                is_retry = pl_path in self._reputation_retry_paths
                if not is_retry and not self.partyledger_state.is_newer(exported_at):
                    log.info(f"PartyLedger data not newer than last upload, skipping {pl_path}")
                    continue

                encounters = payload.get("encounters", [])
                tags = payload.get("tags", [])
                log.info(
                    f"Uploading reputation data from {pl_path}: "
                    f"{len(encounters)} encounter(s), {len(tags)} tag(s)"
                )

                result = client.upload_reputation(payload)
                self.partyledger_state.update(exported_at)
                self._reputation_retry_paths.discard(pl_path)
                log.info(f"Reputation upload complete: {result}")

            except AuthError:
                if _is_retry:
                    log.error("Re-authentication failed for reputation upload")
                    return
                log.warning("Token expired during reputation upload — re-authenticating...")
                with self._client_lock:
                    self.client = None
                clear_token()
                self._login_worker()
                with self._client_lock:
                    if self.client:
                        self._do_reputation_upload(path=path, _is_retry=True)
                return
            except FileNotFoundError:
                log.error(f"PartyLedger SavedVariables not found: {pl_path}")
                continue
            except Exception as e:
                log.error(f"Reputation upload error for {pl_path}: {e}")
                self._reputation_retry_paths.add(pl_path)
                continue

    def _on_partyledger_change(self, filepath: str):
        """Callback triggered when a PartyLedger SavedVariables file changes."""
        log.info(f"PartyLedger file change detected: {filepath}")
        if not self.config.auto_upload:
            log.info("Auto-upload disabled, skipping reputation upload")
            return
        retry_paths = set(self._reputation_retry_paths) - {filepath}
        for rp in retry_paths:
            log.info(f"Retrying previously failed reputation upload: {rp}")
            threading.Thread(target=self._do_reputation_upload, args=(rp,), daemon=True).start()
        threading.Thread(target=self._do_reputation_upload, args=(filepath,), daemon=True).start()

    def _do_settings(self):
        self.window_manager.open_settings(self.config)

    def _do_history(self):
        self.window_manager.open_history(self.history)

    def _do_dashboard(self):
        self.window_manager.open_dashboard(self.stats, list(self.config.savedvariables_paths))

    def _do_group_finder(self):
        with self._client_lock:
            client = self.client
        if not client or not self._group_sync:
            return
        analytics.track("group_finder")
        self.window_manager.open_group_finder(self._group_sync, client)

    def _do_debt_manager(self):
        self.window_manager.open_debt_manager(list(self.config.savedvariables_paths))

    def _fire_webhook(
        self,
        imported_count: int,
        sessions: list[dict],
        stats_player_stats: dict | None = None,
    ):
        import requests
        url = self.config.webhook_url
        if not url:
            return
        try:
            embeds = []
            for s in sessions[:5]:
                embeds.append(format_webhook_embed(s))
            payload = {
                "username": "Voidstorm Gamba",
                "embeds": embeds,
            }
            requests.post(url, json=payload, timeout=10)
            log.info("Webhook fired: %d session(s)", len(embeds))
        except Exception as e:
            log.warning("Webhook failed: %s", e)

        if stats_player_stats:
            stats_url = self.config.stats_webhook_url or self.config.webhook_url
            try:
                summary_embed = format_stats_summary_embed(stats_player_stats)
                stats_payload = {
                    "username": "Voidstorm Gamba",
                    "embeds": [summary_embed],
                }
                requests.post(stats_url, json=stats_payload, timeout=10)
                log.info("Stats summary webhook fired")
            except Exception as e:
                log.warning("Stats summary webhook failed: %s", e)

    def _fire_league_webhook(self, leagues: list[dict]):
        import requests
        url = self.config.league_webhook_url
        if not url:
            return
        try:
            embeds = [format_league_embed(lg) for lg in leagues[:5]]
            payload = {
                "username": "Voidstorm Gamba",
                "embeds": embeds,
            }
            requests.post(url, json=payload, timeout=10)
            log.info("League webhook fired: %d league(s)", len(embeds))
        except Exception as e:
            log.warning("League webhook failed: %s", e)

    def _apply_autostart(self):
        set_autostart(self.config.start_with_windows, self.config.start_minimized)

    def _update_tray_tooltip(self):
        if not self.tray:
            return
        total = self.history.total_imported()
        last = self.history.last_upload_time()
        if last:
            dt = datetime.fromisoformat(last).astimezone()
            last_str = dt.strftime("%m/%d %H:%M")
        else:
            last_str = None
        self.tray.set_tooltip(total, last_str, watching=bool(self.watchers))

    def _check_update(self):
        from voidstorm_companion.updater import check_for_update
        info = check_for_update()
        if info and self.tray:
            log.info(f"Update available: v{info['version']}")
            self.tray.set_update(info)

    def _do_update(self):
        if not self.tray or not self.tray.update_info:
            return

        download_url = self.tray.update_info.get("download_url")
        if not download_url:
            self._open_release_page()
            return

        try:
            from voidstorm_companion.updater import download_update, apply_update

            analytics.track("update_started")
            self.tray.set_status("Downloading update...")
            new_exe = download_update(download_url)

            self.tray.set_status("Installing update...")
            apply_update(new_exe)

            self.tray.quit()
        except Exception as e:
            log.error(f"Auto-update failed: {e}")
            self._open_release_page()

    def _do_update_async(self):
        threading.Thread(target=self._do_update, daemon=True).start()

    def _open_release_page(self):
        if self.tray and self.tray.update_info and self.tray.update_info.get("url"):
            webbrowser.open(self.tray.update_info["url"])

    def _on_quit(self):
        self._quit_event.set()
        if self._group_sync:
            self._group_sync.stop()
        if self._keys_integration:
            self._keys_integration.stop()
        for watcher in self.watchers.values():
            watcher.stop()
        for watcher in self.partyledger_watchers.values():
            watcher.stop()
        self.window_manager.stop()
        log.info("Shutting down")

    def run(self):
        from voidstorm_companion.updater import cleanup_old_update
        cleanup_old_update()

        log.info("Voidstorm Companion starting...")

        analytics.init(self.config.analytics)

        self.window_manager.start()

        if not self.config.savedvariables_paths:
            from voidstorm_companion.config import detect_savedvariables
            found = detect_savedvariables()
            if found:
                self.config.savedvariables_paths = found
                self.config.save()
                log.info(f"Auto-detected {len(found)} SavedVariables path(s)")
            else:
                log.warning("Could not auto-detect WoW SavedVariables path")

        if not self.config.partyledger_paths:
            from voidstorm_companion.config import detect_partyledger_savedvariables
            found_pl = detect_partyledger_savedvariables()
            if found_pl:
                self.config.partyledger_paths = found_pl
                self.config.save()
                log.info(f"Auto-detected {len(found_pl)} PartyLedger path(s)")
            else:
                log.debug("No PartyLedger SavedVariables found")

        if not self.config.keys_paths:
            from voidstorm_companion.config import detect_keys_savedvariables
            found_keys = detect_keys_savedvariables()
            if found_keys:
                self.config.keys_paths = found_keys
                self.config.save()
                log.info(f"Auto-detected {len(found_keys)} VoidstormKeys path(s)")
            else:
                log.debug("No VoidstormKeys SavedVariables found")

        self._ensure_auth()
        self._start_group_sync()
        self._start_keys_integration()

        self._apply_autostart()

        for sv_path in self.config.savedvariables_paths:
            watcher = SavedVariablesWatcher(sv_path, self._on_file_change)
            watcher.start()
            self.watchers[sv_path] = watcher
            log.info(f"Watching: {sv_path}")

        for pl_path in self.config.partyledger_paths:
            watcher = SavedVariablesWatcher(pl_path, self._on_partyledger_change)
            watcher.start()
            self.partyledger_watchers[pl_path] = watcher
            log.info(f"Watching PartyLedger: {pl_path}")

        self.tray = TrayApp(
            on_upload_now=self._do_upload_async,
            on_login=self._do_login,
            on_logout=self._do_logout,
            on_quit=self._on_quit,
            on_settings=self._do_settings,
            on_history=self._do_history,
            on_dashboard=self._do_dashboard,
            on_group_finder=self._do_group_finder,
            on_update=self._do_update_async,
            on_debt_manager=self._do_debt_manager,
        )

        if self.client and self.watchers:
            threading.Thread(target=self._do_upload, daemon=True).start()

        if self.client and self.partyledger_watchers:
            threading.Thread(target=self._do_reputation_upload, daemon=True).start()

        def _reputation_sync_loop():
            while not self._quit_event.is_set():
                self._do_reputation_sync()
                self._quit_event.wait(300)

        threading.Thread(target=_reputation_sync_loop, daemon=True).start()

        is_authed = self.client is not None
        if is_authed and self.watchers:
            self.tray.set_status("Watching", logged_in=True)
        elif is_authed:
            self.tray.set_status("No WoW path", logged_in=True)
        else:
            self.tray.set_status("Not logged in", logged_in=False)

        self._update_tray_tooltip()

        threading.Thread(target=self._check_update, daemon=True).start()

        from voidstorm_companion.updater import CURRENT_VERSION
        analytics.track("app_start", {"version": CURRENT_VERSION})

        self.tray.run()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Voidstorm Companion")
    parser.add_argument("--dev", action="store_true", help="Use development API server (dev.voidstorm.cc)")
    parser.add_argument("--minimized", action="store_true", help="Start minimized to tray")
    args = parser.parse_args()

    app = App()

    if args.dev:
        from voidstorm_companion.config import DEV_API_URL
        app.config.api_url = DEV_API_URL

    app.run()


if __name__ == "__main__":
    main()
