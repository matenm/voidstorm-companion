import json
import os
import tempfile

import pytest
from voidstorm_companion.main import (
    format_webhook_embed,
    format_slots_embed,
    SLOT_SYMBOL_EMOJI,
    format_roulette_embed,
    ROULETTE_COLOR_EMOJI,
    format_stats_summary_embed,
    format_tournament_embed,
    format_achievement_embed,
    format_league_embed,
    format_league_milestone_embed,
    _apply_verbosity,
    build_player_stats,
    StatsSummaryState,
)


def _make_slots_session(reel1="cherry", reel2="lemon", reel3="cherry",
                         jackpot=False, jackpot_amount=0, winner="Bp",
                         amount=250, pot=200):
    session = {
        "id": "test-slots-1",
        "mode": "SLOTS",
        "host": "Bp",
        "wager": 100,
        "channel": "SAY",
        "startedAt": 1740936500,
        "endedAt": 1740936560,
        "rounds": [
            {
                "number": 1,
                "mode": "SLOTS",
                "time": 1740936550,
                "players": [
                    {"name": "Bp", "realm": "Ravencrest", "bet": 100, "payout": amount if winner == "Bp" else 0},
                    {"name": "Skatten", "realm": "Ravencrest", "bet": 100, "payout": amount if winner == "Skatten" else 0},
                ],
                "results": {
                    "reel1": reel1,
                    "reel2": reel2,
                    "reel3": reel3,
                    "jackpot": jackpot,
                    "pot": pot,
                    "winner": winner,
                    "amount": amount,
                    "summary": f"{winner} wins {amount}g on the slots!",
                },
            },
        ],
    }
    if jackpot and jackpot_amount:
        session["rounds"][0]["results"]["jackpotAmount"] = jackpot_amount
    return session


# --- Emoji mapping ---


def test_slot_symbol_emoji_mapping():
    assert SLOT_SYMBOL_EMOJI["cherry"] == "\U0001f352"
    assert SLOT_SYMBOL_EMOJI["lemon"] == "\U0001f34b"
    assert SLOT_SYMBOL_EMOJI["bar"] == "\U0001f4ca"
    assert SLOT_SYMBOL_EMOJI["seven"] == "7\ufe0f\u20e3"
    assert SLOT_SYMBOL_EMOJI["diamond"] == "\U0001f48e"
    assert SLOT_SYMBOL_EMOJI["skull"] == "\U0001f480"
    assert len(SLOT_SYMBOL_EMOJI) == 6


# --- Slots webhook formatting ---


def test_slots_embed_shows_reel_emojis():
    session = _make_slots_session(reel1="cherry", reel2="lemon", reel3="bar")
    embed = format_slots_embed(session)
    reels_field = next(f for f in embed["fields"] if f["name"] == "Reels")
    assert "\U0001f352" in reels_field["value"]  # cherry
    assert "\U0001f34b" in reels_field["value"]  # lemon
    assert "\U0001f4ca" in reels_field["value"]  # bar


def test_slots_embed_shows_all_symbol_emojis():
    for symbol, emoji in SLOT_SYMBOL_EMOJI.items():
        session = _make_slots_session(reel1=symbol, reel2=symbol, reel3=symbol)
        embed = format_slots_embed(session)
        reels_field = next(f for f in embed["fields"] if f["name"] == "Reels")
        assert emoji in reels_field["value"]


def test_slots_embed_shows_winner_payout():
    session = _make_slots_session(winner="Bp", amount=250)
    embed = format_slots_embed(session)
    players_field = next(f for f in embed["fields"] if f["name"] == "Players")
    assert "Bp" in players_field["value"]
    assert "+250" in players_field["value"]


def test_slots_embed_shows_pot():
    session = _make_slots_session(pot=500)
    embed = format_slots_embed(session)
    pot_field = next(f for f in embed["fields"] if f["name"] == "Pot")
    assert "500" in pot_field["value"]


def test_slots_embed_normal_color():
    session = _make_slots_session(jackpot=False)
    embed = format_slots_embed(session)
    assert embed["color"] == 0x89b4fa


# --- Jackpot special formatting ---


def test_slots_jackpot_embed_has_gold_color():
    session = _make_slots_session(
        reel1="seven", reel2="seven", reel3="seven",
        jackpot=True, jackpot_amount=50000, winner="Skatten", amount=50000,
    )
    embed = format_slots_embed(session)
    assert embed["color"] == 0xffd700  # gold


def test_slots_jackpot_embed_has_celebratory_title():
    session = _make_slots_session(
        reel1="seven", reel2="seven", reel3="seven",
        jackpot=True, jackpot_amount=50000, winner="Skatten", amount=50000,
    )
    embed = format_slots_embed(session)
    assert "JACKPOT" in embed["title"]


def test_slots_jackpot_embed_mentions_winner_and_amount():
    session = _make_slots_session(
        reel1="seven", reel2="seven", reel3="seven",
        jackpot=True, jackpot_amount=50000, winner="Skatten", amount=50000,
    )
    embed = format_slots_embed(session)
    assert "Skatten" in embed["description"]
    assert "50,000" in embed["description"]


def test_slots_jackpot_reels_show_triple_sevens():
    session = _make_slots_session(
        reel1="seven", reel2="seven", reel3="seven",
        jackpot=True, jackpot_amount=50000, winner="Skatten", amount=50000,
    )
    embed = format_slots_embed(session)
    reels_field = next(f for f in embed["fields"] if f["name"] == "Reels")
    seven_emoji = SLOT_SYMBOL_EMOJI["seven"]
    expected = f"{seven_emoji} {seven_emoji} {seven_emoji}"
    assert reels_field["value"] == expected


# --- format_webhook_embed dispatches correctly ---


def test_format_webhook_embed_dispatches_slots():
    session = _make_slots_session()
    embed = format_webhook_embed(session)
    assert "Slots" in embed["title"]
    assert any(f["name"] == "Reels" for f in embed["fields"])


def _make_roulette_session(
    pocket=14,
    color="red",
    pot=700,
    winner="Bp",
    amount=1000,
    players=None,
    summary="",
    big_win=False,
):
    if players is None:
        players = [
            {"name": "Bp", "realm": "Ravencrest", "bet": 500, "payout": 1000, "betType": "red"},
            {"name": "Skatten", "realm": "Ravencrest", "bet": 200, "payout": 0, "betType": "straight_17"},
        ]
    results = {
        "pocket": pocket,
        "color": color,
        "pot": pot,
        "winner": winner,
        "amount": amount,
        "summary": summary,
    }
    return {
        "id": "test-roulette-1",
        "mode": "ROULETTE",
        "host": "Bp",
        "wager": 500,
        "channel": "SAY",
        "startedAt": 1740937000,
        "endedAt": 1740937060,
        "rounds": [
            {
                "number": 1,
                "mode": "ROULETTE",
                "time": 1740937050,
                "players": players,
                "results": results,
            }
        ],
    }


# --- Roulette emoji mapping ---


def test_roulette_color_emoji_mapping():
    assert ROULETTE_COLOR_EMOJI["red"] == "\U0001f534"
    assert ROULETTE_COLOR_EMOJI["black"] == "\u26ab"
    assert ROULETTE_COLOR_EMOJI["green"] == "\U0001f7e2"


# --- Roulette embed ---


def test_roulette_embed_shows_pocket_with_color():
    embed = format_roulette_embed(_make_roulette_session(pocket=14, color="red"))
    result_field = next(f for f in embed["fields"] if f["name"] == "Result")
    assert "14" in result_field["value"]
    assert "\U0001f534" in result_field["value"]  # red emoji


def test_roulette_embed_shows_properties():
    embed = format_roulette_embed(_make_roulette_session(pocket=14, color="red"))
    props_field = next(f for f in embed["fields"] if f["name"] == "Properties")
    assert "Even" in props_field["value"]
    assert "Low" in props_field["value"]
    assert "2nd Dozen" in props_field["value"]


def test_roulette_embed_zero_properties():
    embed = format_roulette_embed(_make_roulette_session(pocket=0, color="green"))
    props_field = next(f for f in embed["fields"] if f["name"] == "Properties")
    assert "Zero" in props_field["value"]


def test_roulette_embed_shows_player_payouts():
    embed = format_roulette_embed(_make_roulette_session())
    players_field = next(f for f in embed["fields"] if f["name"] == "Players")
    assert "Bp" in players_field["value"]
    assert "+1,000g" in players_field["value"]
    assert "Skatten" in players_field["value"]


def test_roulette_embed_shows_pot():
    embed = format_roulette_embed(_make_roulette_session(pot=700))
    pot_field = next(f for f in embed["fields"] if f["name"] == "Pot")
    assert "700" in pot_field["value"]


def test_roulette_embed_normal_color():
    embed = format_roulette_embed(_make_roulette_session())
    assert embed["color"] == 0x89b4fa


def test_roulette_embed_big_win_color():
    big_players = [
        {"name": "Bp", "realm": "Ravencrest", "bet": 1000, "payout": 35000, "betType": "straight_7"},
    ]
    embed = format_roulette_embed(_make_roulette_session(
        pocket=7, color="red", amount=35000, winner="Bp", players=big_players
    ))
    assert embed["color"] == 0xffd700


def test_roulette_embed_title_normal():
    embed = format_roulette_embed(_make_roulette_session())
    assert "Roulette" in embed["title"]
    assert "BIG WIN" not in embed["title"]


def test_roulette_embed_title_big_win():
    big_players = [
        {"name": "Bp", "realm": "Ravencrest", "bet": 1000, "payout": 35000, "betType": "straight_7"},
    ]
    embed = format_roulette_embed(_make_roulette_session(players=big_players))
    assert "BIG WIN" in embed["title"]


def test_format_webhook_embed_dispatches_roulette():
    session = _make_roulette_session()
    embed = format_webhook_embed(session)
    assert "Roulette" in embed["title"]


def test_format_webhook_embed_non_slots_mode():
    session = {
        "mode": "DIFFERENCE",
        "wager": 50000,
        "rounds": [{
            "results": {
                "winner": "Bp",
                "summary": "Bp wins 50000g",
            },
        }],
    }
    embed = format_webhook_embed(session)
    assert embed["title"] == "Difference Result"
    assert embed["description"] == "Bp wins 50000g"
    winners = [f for f in embed["fields"] if f["name"] == "Winner"]
    assert len(winners) == 1
    assert winners[0]["value"] == "Bp"


# ---------------------------------------------------------------------------
# Helpers for Phase 3 stats summary tests
# ---------------------------------------------------------------------------


def _make_player_stats(
    player_name="Bp",
    realm="Ravencrest",
    wins=50,
    losses=30,
    total_wagered=500000,
    total_won=620000,
    net_profit=120000,
    sessions=80,
    playtime=36000,
    mode_breakdown=None,
    recent_sessions=None,
    rivals=None,
):
    if mode_breakdown is None:
        mode_breakdown = {
            "POKER": {"wins": 20, "losses": 10, "wagered": 200000, "won": 280000, "played": 30},
            "SLOTS": {"wins": 15, "losses": 12, "wagered": 150000, "won": 170000, "played": 27},
            "ROULETTE": {"wins": 15, "losses": 8, "wagered": 150000, "won": 170000, "played": 23},
        }
    if recent_sessions is None:
        recent_sessions = [
            {"mode": "POKER", "result": "win", "netProfit": 5000, "timestamp": 1709299000},
            {"mode": "SLOTS", "result": "loss", "netProfit": -2000, "timestamp": 1709298000},
        ]
    if rivals is None:
        rivals = [
            {"name": "Opponent1", "wins": 10, "losses": 5, "netGold": 30000},
            {"name": "Opponent2", "wins": 3, "losses": 8, "netGold": -15000},
        ]
    return {
        "playerName": player_name,
        "realm": realm,
        "lifetime": {
            "wins": wins,
            "losses": losses,
            "totalWagered": total_wagered,
            "totalWon": total_won,
            "netProfit": net_profit,
            "sessions": sessions,
            "playtime": playtime,
        },
        "modeBreakdown": mode_breakdown,
        "recentSessions": recent_sessions,
        "rivals": rivals,
    }


# ---------------------------------------------------------------------------
# format_stats_summary_embed — title and color
# ---------------------------------------------------------------------------


def test_stats_summary_embed_title_contains_player_name():
    embed = format_stats_summary_embed(_make_player_stats(player_name="Bp", realm="Ravencrest"))
    assert "Bp" in embed["title"]


def test_stats_summary_embed_title_contains_realm():
    embed = format_stats_summary_embed(_make_player_stats(player_name="Bp", realm="Ravencrest"))
    assert "Ravencrest" in embed["title"]


def test_stats_summary_embed_title_has_stats_update_label():
    embed = format_stats_summary_embed(_make_player_stats())
    assert "Stats Update" in embed["title"]


def test_stats_summary_embed_title_no_realm_when_empty():
    embed = format_stats_summary_embed(_make_player_stats(player_name="Bp", realm=""))
    assert "Bp" in embed["title"]
    # Only "Bp", no hyphen separator
    assert "-" not in embed["title"]


def test_stats_summary_embed_color_is_blue():
    embed = format_stats_summary_embed(_make_player_stats())
    assert embed["color"] == 0x3498DB


# ---------------------------------------------------------------------------
# format_stats_summary_embed — fields
# ---------------------------------------------------------------------------


def test_stats_summary_embed_has_session_pl_field():
    embed = format_stats_summary_embed(_make_player_stats())
    pl_fields = [f for f in embed["fields"] if "Session P/L" in f["name"]]
    assert len(pl_fields) == 1


def test_stats_summary_embed_session_pl_positive_green():
    ps = _make_player_stats(recent_sessions=[
        {"mode": "POKER", "result": "win", "netProfit": 10000, "timestamp": 1},
    ])
    embed = format_stats_summary_embed(ps)
    pl_field = next(f for f in embed["fields"] if "Session P/L" in f["name"])
    # Green circle emoji in field name
    assert "\U0001f7e2" in pl_field["name"]
    assert "+10,000g" in pl_field["value"]


def test_stats_summary_embed_session_pl_negative_red():
    ps = _make_player_stats(recent_sessions=[
        {"mode": "SLOTS", "result": "loss", "netProfit": -3000, "timestamp": 1},
    ])
    embed = format_stats_summary_embed(ps)
    pl_field = next(f for f in embed["fields"] if "Session P/L" in f["name"])
    assert "\U0001f534" in pl_field["name"]
    assert "-3,000g" in pl_field["value"]


def test_stats_summary_embed_lifetime_wl_field():
    embed = format_stats_summary_embed(_make_player_stats(wins=50, losses=30))
    wl_field = next(f for f in embed["fields"] if "Lifetime W/L" in f["name"])
    assert "50W" in wl_field["value"]
    assert "30L" in wl_field["value"]


def test_stats_summary_embed_win_rate_in_wl_field():
    embed = format_stats_summary_embed(_make_player_stats(wins=50, losses=50))
    wl_field = next(f for f in embed["fields"] if "Lifetime W/L" in f["name"])
    assert "50.0%" in wl_field["value"]


def test_stats_summary_embed_win_rate_zero_games():
    ps = _make_player_stats(wins=0, losses=0)
    embed = format_stats_summary_embed(ps)
    wl_field = next(f for f in embed["fields"] if "Lifetime W/L" in f["name"])
    assert "0.0%" in wl_field["value"]


def test_stats_summary_embed_net_profit_positive():
    embed = format_stats_summary_embed(_make_player_stats(net_profit=120000))
    profit_field = next(f for f in embed["fields"] if "Net Profit" in f["name"])
    assert "+120,000g" in profit_field["value"]


def test_stats_summary_embed_net_profit_negative():
    embed = format_stats_summary_embed(_make_player_stats(net_profit=-50000))
    profit_field = next(f for f in embed["fields"] if "Net Profit" in f["name"])
    assert "-50,000g" in profit_field["value"]


def test_stats_summary_embed_favorite_mode_is_most_played():
    # POKER has highest played count (30)
    embed = format_stats_summary_embed(_make_player_stats())
    mode_field = next(f for f in embed["fields"] if "Favorite Mode" in f["name"])
    assert "Poker" in mode_field["value"]


def test_stats_summary_embed_top_rival_most_wins():
    # Opponent1 has 10 wins — should be top rival
    embed = format_stats_summary_embed(_make_player_stats())
    rival_field = next(f for f in embed["fields"] if "Top Rival" in f["name"])
    assert "Opponent1" in rival_field["value"]


def test_stats_summary_embed_win_streak_positive():
    ps = _make_player_stats(recent_sessions=[
        {"mode": "POKER", "result": "win", "netProfit": 5000, "timestamp": 3},
        {"mode": "SLOTS", "result": "win", "netProfit": 2000, "timestamp": 2},
        {"mode": "POKER", "result": "loss", "netProfit": -1000, "timestamp": 1},
    ])
    embed = format_stats_summary_embed(ps)
    streak_fields = [f for f in embed["fields"] if "Streak" in f["name"]]
    assert len(streak_fields) == 1
    assert "win" in streak_fields[0]["value"]
    assert "2" in streak_fields[0]["value"]


def test_stats_summary_embed_loss_streak_negative():
    ps = _make_player_stats(recent_sessions=[
        {"mode": "POKER", "result": "loss", "netProfit": -1000, "timestamp": 3},
        {"mode": "SLOTS", "result": "loss", "netProfit": -2000, "timestamp": 2},
        {"mode": "POKER", "result": "win", "netProfit": 5000, "timestamp": 1},
    ])
    embed = format_stats_summary_embed(ps)
    streak_fields = [f for f in embed["fields"] if "Streak" in f["name"]]
    assert len(streak_fields) == 1
    assert "loss" in streak_fields[0]["value"]


def test_stats_summary_embed_no_streak_field_when_no_recent_sessions():
    ps = _make_player_stats(recent_sessions=[])
    embed = format_stats_summary_embed(ps)
    streak_fields = [f for f in embed["fields"] if "Streak" in f["name"]]
    assert len(streak_fields) == 0


def test_stats_summary_embed_no_rival_field_when_no_rivals():
    ps = _make_player_stats(rivals=[])
    embed = format_stats_summary_embed(ps)
    rival_fields = [f for f in embed["fields"] if "Rival" in f["name"]]
    assert len(rival_fields) == 0


def test_stats_summary_embed_no_mode_field_when_no_breakdown():
    ps = _make_player_stats(mode_breakdown={})
    embed = format_stats_summary_embed(ps)
    mode_fields = [f for f in embed["fields"] if "Favorite Mode" in f["name"]]
    assert len(mode_fields) == 0


# ---------------------------------------------------------------------------
# build_player_stats
# ---------------------------------------------------------------------------


def test_build_player_stats_includes_player_name_and_realm():
    exported = {
        "lifetime": {"wins": 10, "losses": 5},
        "modeBreakdown": {},
        "recentSessions": [],
        "rivals": [],
    }
    ps = build_player_stats(exported, player_name="Bp", realm="Ravencrest")
    assert ps["playerName"] == "Bp"
    assert ps["realm"] == "Ravencrest"


def test_build_player_stats_lifetime_forwarded():
    exported = {
        "lifetime": {"wins": 50, "losses": 30, "netProfit": 120000},
        "modeBreakdown": {},
        "recentSessions": [],
        "rivals": [],
    }
    ps = build_player_stats(exported)
    assert ps["lifetime"]["wins"] == 50
    assert ps["lifetime"]["netProfit"] == 120000


def test_build_player_stats_empty_exported_returns_empty_sections():
    ps = build_player_stats({})
    assert ps["lifetime"] == {}
    assert ps["modeBreakdown"] == {}
    assert ps["recentSessions"] == []
    assert ps["rivals"] == []


# ---------------------------------------------------------------------------
# StatsSummaryState
# ---------------------------------------------------------------------------


def test_stats_summary_state_initial_count_is_zero():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        assert state.sessions_since_summary == 0


def test_stats_summary_state_add_sessions_increments():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        state.add_sessions(3)
        assert state.sessions_since_summary == 3
        state.add_sessions(2)
        assert state.sessions_since_summary == 5


def test_stats_summary_state_reset_clears_count():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        state.add_sessions(10)
        state.reset()
        assert state.sessions_since_summary == 0


def test_stats_summary_state_persists_across_loads():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.json")
        state = StatsSummaryState(path)
        state.add_sessions(7)

        state2 = StatsSummaryState(path)
        assert state2.sessions_since_summary == 7


def test_stats_summary_state_reset_persists_across_loads():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.json")
        state = StatsSummaryState(path)
        state.add_sessions(10)
        state.reset()

        state2 = StatsSummaryState(path)
        assert state2.sessions_since_summary == 0


def test_stats_summary_state_should_post_below_threshold():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        state.add_sessions(4)
        assert state.should_post_summary(threshold=5) is False


def test_stats_summary_state_should_post_at_threshold():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        state.add_sessions(5)
        assert state.should_post_summary(threshold=5) is True


def test_stats_summary_state_should_post_above_threshold():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        state.add_sessions(8)
        assert state.should_post_summary(threshold=5) is True


def test_stats_summary_state_custom_threshold():
    with tempfile.TemporaryDirectory() as d:
        state = StatsSummaryState(os.path.join(d, "state.json"))
        state.add_sessions(3)
        assert state.should_post_summary(threshold=3) is True
        assert state.should_post_summary(threshold=4) is False


def test_stats_summary_state_missing_file_starts_at_zero():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nonexistent", "state.json")
        state = StatsSummaryState(path)
        assert state.sessions_since_summary == 0


def test_stats_summary_state_corrupt_file_falls_back_to_zero():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.json")
        with open(path, "w") as f:
            f.write("not valid json {{{{")
        state = StatsSummaryState(path)
        assert state.sessions_since_summary == 0


# ---------------------------------------------------------------------------
# Helpers for Phase 4 tournament embed tests
# ---------------------------------------------------------------------------


def _make_tournament_data(
    tournament_id="T1709234567",
    name="Friday Night Poker",
    mode="POKER",
    fmt="SINGLE_ELIM",
    buy_in=500,
    max_players=8,
    prize_pool=4000,
    players=None,
    prizes=None,
    bracket=None,
    status="COMPLETE",
    start_time=1709234567,
    end_time=1709238167,
):
    if players is None:
        players = [
            "PlayerOne", "PlayerTwo", "PlayerThree", "PlayerFour",
            "PlayerFive", "PlayerSix", "PlayerSeven", "PlayerEight",
        ]
    if prizes is None:
        prizes = [
            {"player": "PlayerOne", "amount": 2400, "place": 1},
            {"player": "PlayerFive", "amount": 1000, "place": 2},
            {"player": "PlayerThree", "amount": 300, "place": 3},
            {"player": "PlayerSeven", "amount": 300, "place": 4},
        ]
    if bracket is None:
        bracket = {
            "round1": [
                {"winner": "PlayerOne", "loser": "PlayerTwo"},
                {"winner": "PlayerThree", "loser": "PlayerFour"},
                {"winner": "PlayerFive", "loser": "PlayerSix"},
                {"winner": "PlayerSeven", "loser": "PlayerEight"},
            ],
            "round2": [
                {"winner": "PlayerOne", "loser": "PlayerThree"},
                {"winner": "PlayerFive", "loser": "PlayerSeven"},
            ],
            "finals": [
                {"winner": "PlayerOne", "loser": "PlayerFive"},
            ],
        }
    return {
        "id": tournament_id,
        "name": name,
        "mode": mode,
        "format": fmt,
        "buyIn": buy_in,
        "maxPlayers": max_players,
        "prizePool": prize_pool,
        "players": players,
        "prizes": prizes,
        "bracket": bracket,
        "status": status,
        "startTime": start_time,
        "endTime": end_time,
    }


# ---------------------------------------------------------------------------
# format_tournament_embed — title, color, description
# ---------------------------------------------------------------------------


def test_tournament_embed_title_contains_tournament_complete():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    assert "Tournament Complete" in embed["title"]


def test_tournament_embed_title_contains_name():
    t = _make_tournament_data(name="Friday Night Poker")
    embed = format_tournament_embed(t)
    assert "Friday Night Poker" in embed["title"]


def test_tournament_embed_color_is_gold():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    assert embed["color"] == 0xFFD700


def test_tournament_embed_description_contains_mode():
    t = _make_tournament_data(mode="POKER")
    embed = format_tournament_embed(t)
    assert "Poker" in embed["description"]


def test_tournament_embed_description_contains_format():
    t = _make_tournament_data(fmt="SINGLE_ELIM")
    embed = format_tournament_embed(t)
    assert "Single Elimination" in embed["description"]


def test_tournament_embed_description_contains_player_count():
    t = _make_tournament_data(players=["A", "B", "C", "D", "E", "F", "G", "H"])
    embed = format_tournament_embed(t)
    assert "8 players" in embed["description"]


def test_tournament_embed_description_shows_bracket_rounds_for_single_elim():
    t = _make_tournament_data(fmt="SINGLE_ELIM")
    embed = format_tournament_embed(t)
    assert "Bracket" in embed["description"]
    assert "3 round" in embed["description"]


def test_tournament_embed_description_no_bracket_summary_for_round_robin():
    t = _make_tournament_data(fmt="ROUND_ROBIN", bracket={})
    embed = format_tournament_embed(t)
    assert "Bracket" not in embed["description"]


# ---------------------------------------------------------------------------
# format_tournament_embed — placement fields
# ---------------------------------------------------------------------------


def test_tournament_embed_has_first_place_field():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    first_fields = [f for f in embed["fields"] if "1st Place" in f["name"]]
    assert len(first_fields) == 1


def test_tournament_embed_first_place_shows_player_and_prize():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    first = next(f for f in embed["fields"] if "1st Place" in f["name"])
    assert "PlayerOne" in first["value"]
    assert "2,400" in first["value"]


def test_tournament_embed_has_second_place_field():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    second_fields = [f for f in embed["fields"] if "2nd Place" in f["name"]]
    assert len(second_fields) == 1


def test_tournament_embed_second_place_shows_player_and_prize():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    second = next(f for f in embed["fields"] if "2nd Place" in f["name"])
    assert "PlayerFive" in second["value"]
    assert "1,000" in second["value"]


def test_tournament_embed_has_third_place_field():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    third_fields = [f for f in embed["fields"] if "3rd Place" in f["name"]]
    assert len(third_fields) == 1


def test_tournament_embed_third_place_shows_player_and_prize():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    third = next(f for f in embed["fields"] if "3rd Place" in f["name"])
    assert "PlayerThree" in third["value"]
    assert "300" in third["value"]


def test_tournament_embed_has_first_place_gold_medal_emoji():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    first = next(f for f in embed["fields"] if "1st Place" in f["name"])
    assert "\U0001f947" in first["name"]


def test_tournament_embed_has_second_place_silver_medal_emoji():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    second = next(f for f in embed["fields"] if "2nd Place" in f["name"])
    assert "\U0001f948" in second["name"]


def test_tournament_embed_has_third_place_bronze_medal_emoji():
    t = _make_tournament_data()
    embed = format_tournament_embed(t)
    third = next(f for f in embed["fields"] if "3rd Place" in f["name"])
    assert "\U0001f949" in third["name"]


def test_tournament_embed_has_buy_in_prize_pool_field():
    t = _make_tournament_data(buy_in=500, prize_pool=4000)
    embed = format_tournament_embed(t)
    summary_fields = [f for f in embed["fields"] if "Prize Pool" in f["name"] or "Buy-in" in f["name"]]
    assert len(summary_fields) == 1
    summary = summary_fields[0]
    assert "500" in summary["value"]
    assert "4,000" in summary["value"]


def test_tournament_embed_no_prizes_produces_no_placement_fields():
    t = _make_tournament_data(prizes=[])
    embed = format_tournament_embed(t)
    place_fields = [f for f in embed["fields"] if "Place" in f["name"]]
    assert len(place_fields) == 0


def test_tournament_embed_mode_deathroll_shows_correct_mode_name():
    t = _make_tournament_data(mode="DEATHROLL", fmt="ROUND_ROBIN", bracket={})
    embed = format_tournament_embed(t)
    assert "Deathroll" in embed["description"]


# ---------------------------------------------------------------------------
# format_webhook_embed — tournament dispatch routing
# ---------------------------------------------------------------------------


def test_format_webhook_embed_dispatches_tournament():
    t = _make_tournament_data()
    t["type"] = "tournament"
    embed = format_webhook_embed(t)
    assert "Tournament Complete" in embed["title"]
    assert embed["color"] == 0xFFD700


def test_format_webhook_embed_tournament_dispatch_has_placement_fields():
    t = _make_tournament_data()
    t["type"] = "tournament"
    embed = format_webhook_embed(t)
    first_fields = [f for f in embed["fields"] if "1st Place" in f["name"]]
    assert len(first_fields) == 1


# ---------------------------------------------------------------------------
# Helpers for Phase 4 achievement embed tests
# ---------------------------------------------------------------------------


def _make_achievement_data(
    achievement_key="FIRST_BLOOD",
    achievement_name="First Blood",
    player_name="Bp",
    unlocked_at=1709234000,
    icon_url="",
    points=0,
):
    return {
        "achievementKey": achievement_key,
        "achievementName": achievement_name,
        "playerName": player_name,
        "unlockedAt": unlocked_at,
        "iconUrl": icon_url,
        "points": points,
    }


# ---------------------------------------------------------------------------
# format_achievement_embed — title, description, color
# ---------------------------------------------------------------------------


def test_achievement_embed_title_contains_achievement_unlocked():
    ach = _make_achievement_data()
    embed = format_achievement_embed(ach)
    assert "Achievement Unlocked" in embed["title"]


def test_achievement_embed_description_contains_player_name():
    ach = _make_achievement_data(player_name="Skatten")
    embed = format_achievement_embed(ach)
    assert "Skatten" in embed["description"]


def test_achievement_embed_description_contains_achievement_name():
    ach = _make_achievement_data(achievement_name="First Blood")
    embed = format_achievement_embed(ach)
    assert "First Blood" in embed["description"]


def test_achievement_embed_color_purple_for_regular():
    # FIRST_BLOOD has 10 points in registry — purple
    ach = _make_achievement_data(achievement_key="FIRST_BLOOD")
    embed = format_achievement_embed(ach)
    assert embed["color"] == 0x9B59B6


def test_achievement_embed_color_gold_for_rare():
    # HIGH_ROLLER has 50 points in registry — gold
    ach = _make_achievement_data(achievement_key="HIGH_ROLLER")
    embed = format_achievement_embed(ach)
    assert embed["color"] == 0xFFD700


def test_achievement_embed_color_gold_for_30_plus_points():
    ach = _make_achievement_data(achievement_key="UNKNOWN_ACH", points=30)
    embed = format_achievement_embed(ach)
    assert embed["color"] == 0xFFD700


def test_achievement_embed_color_purple_for_below_30_points():
    ach = _make_achievement_data(achievement_key="UNKNOWN_ACH", points=29)
    embed = format_achievement_embed(ach)
    assert embed["color"] == 0x9B59B6


def test_achievement_embed_has_points_field():
    ach = _make_achievement_data(achievement_key="FIRST_BLOOD")
    embed = format_achievement_embed(ach)
    points_fields = [f for f in embed["fields"] if f["name"] == "Points"]
    assert len(points_fields) == 1


def test_achievement_embed_points_value_from_registry():
    ach = _make_achievement_data(achievement_key="FIRST_BLOOD")
    embed = format_achievement_embed(ach)
    points_field = next(f for f in embed["fields"] if f["name"] == "Points")
    assert points_field["value"] == "10"


def test_achievement_embed_points_value_from_data_when_provided():
    ach = _make_achievement_data(achievement_key="UNKNOWN_ACH", points=99)
    embed = format_achievement_embed(ach)
    points_field = next(f for f in embed["fields"] if f["name"] == "Points")
    assert points_field["value"] == "99"


def test_achievement_embed_has_description_field_for_known_achievement():
    ach = _make_achievement_data(achievement_key="FIRST_BLOOD")
    embed = format_achievement_embed(ach)
    desc_fields = [f for f in embed["fields"] if f["name"] == "Description"]
    assert len(desc_fields) == 1
    assert "first" in desc_fields[0]["value"].lower()


def test_achievement_embed_no_description_field_for_unknown_achievement():
    ach = _make_achievement_data(achievement_key="MYSTERY_ACH")
    embed = format_achievement_embed(ach)
    desc_fields = [f for f in embed["fields"] if f["name"] == "Description"]
    assert len(desc_fields) == 0


def test_achievement_embed_thumbnail_when_icon_url_provided():
    ach = _make_achievement_data(icon_url="https://example.com/icon.png")
    embed = format_achievement_embed(ach)
    assert "thumbnail" in embed
    assert embed["thumbnail"]["url"] == "https://example.com/icon.png"


def test_achievement_embed_no_thumbnail_when_no_icon_url():
    ach = _make_achievement_data(icon_url="")
    embed = format_achievement_embed(ach)
    assert "thumbnail" not in embed


def test_achievement_embed_century_club_is_gold():
    # CENTURY_CLUB has 25 points — purple
    ach = _make_achievement_data(achievement_key="CENTURY_CLUB")
    embed = format_achievement_embed(ach)
    assert embed["color"] == 0x9B59B6


def test_achievement_embed_lucky_streak_is_gold():
    # LUCKY_STREAK has 30 points — gold
    ach = _make_achievement_data(achievement_key="LUCKY_STREAK")
    embed = format_achievement_embed(ach)
    assert embed["color"] == 0xFFD700


# ---------------------------------------------------------------------------
# format_webhook_embed — achievement dispatch routing
# ---------------------------------------------------------------------------


def test_format_webhook_embed_dispatches_achievement():
    ach = _make_achievement_data()
    ach["type"] = "achievement"
    embed = format_webhook_embed(ach)
    assert "Achievement Unlocked" in embed["title"]


def test_format_webhook_embed_achievement_dispatch_has_points_field():
    ach = _make_achievement_data(achievement_key="FIRST_BLOOD")
    ach["type"] = "achievement"
    embed = format_webhook_embed(ach)
    points_fields = [f for f in embed["fields"] if f["name"] == "Points"]
    assert len(points_fields) == 1


def test_format_webhook_embed_no_type_still_dispatches_session_mode():
    session = {
        "mode": "DIFFERENCE",
        "wager": 1000,
        "rounds": [{"results": {"winner": "Bp", "summary": "Bp wins"}}],
    }
    embed = format_webhook_embed(session)
    assert "Difference" in embed["title"]


# ---------------------------------------------------------------------------
# Helpers for Phase 5 league embed tests
# ---------------------------------------------------------------------------


def _make_league_data(
    league_key="GuildLeague1",
    name="Friday Night League",
    guild="Voidstorm",
    season=3,
    standings=None,
    history=None,
    started_at=1709234567,
):
    if standings is None:
        standings = [
            {"name": "Player1", "points": 15, "wins": 5, "losses": 2, "draws": 0, "netGold": 12500},
            {"name": "Player2", "points": 12, "wins": 4, "losses": 3, "draws": 0, "netGold": 8200},
            {"name": "Player3", "points": 9, "wins": 3, "losses": 4, "draws": 0, "netGold": -3000},
        ]
    if history is None:
        history = [{"season": 1, "winner": "Player3", "standings": []}]
    return {
        "leagueKey": league_key,
        "name": name,
        "guild": guild,
        "season": season,
        "standings": standings,
        "history": history,
        "startedAt": started_at,
    }


# ---------------------------------------------------------------------------
# format_league_embed — title, color, fields
# ---------------------------------------------------------------------------


def test_league_embed_title_contains_league_season_complete():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    assert "League Season Complete" in embed["title"]


def test_league_embed_title_contains_league_name():
    lg = _make_league_data(name="Friday Night League")
    embed = format_league_embed(lg)
    assert "Friday Night League" in embed["title"]


def test_league_embed_color_is_gold():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    assert embed["color"] == 0xFFD700


def test_league_embed_has_final_standings_field():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_fields = [f for f in embed["fields"] if "Standings" in f["name"]]
    assert len(standings_fields) == 1


def test_league_embed_standings_shows_all_players():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "Player1" in standings_field["value"]
    assert "Player2" in standings_field["value"]
    assert "Player3" in standings_field["value"]


def test_league_embed_standings_shows_points():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "15" in standings_field["value"]
    assert "12" in standings_field["value"]
    assert "9" in standings_field["value"]


def test_league_embed_standings_shows_wld():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "5W" in standings_field["value"]
    assert "2L" in standings_field["value"]


def test_league_embed_standings_shows_net_gold():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "12,500" in standings_field["value"]


def test_league_embed_standings_shows_gold_medal_for_first():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    # Gold medal emoji for rank 1
    assert "\U0001f947" in standings_field["value"]


def test_league_embed_standings_shows_silver_medal_for_second():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "\U0001f948" in standings_field["value"]


def test_league_embed_standings_shows_bronze_medal_for_third():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "\U0001f949" in standings_field["value"]


def test_league_embed_has_mvp_field():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    mvp_fields = [f for f in embed["fields"] if "MVP" in f["name"]]
    assert len(mvp_fields) == 1


def test_league_embed_mvp_is_most_points_player():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    mvp_field = next(f for f in embed["fields"] if "MVP" in f["name"])
    assert "Player1" in mvp_field["value"]


def test_league_embed_footer_contains_season_number():
    lg = _make_league_data(season=3)
    embed = format_league_embed(lg)
    assert "footer" in embed
    assert "Season 3" in embed["footer"]["text"]


def test_league_embed_footer_contains_guild():
    lg = _make_league_data(guild="Voidstorm")
    embed = format_league_embed(lg)
    assert "Voidstorm" in embed["footer"]["text"]


def test_league_embed_empty_standings_no_crash():
    lg = _make_league_data(standings=[])
    embed = format_league_embed(lg)
    assert embed["color"] == 0xFFD700
    assert "title" in embed


def test_league_embed_negative_net_gold_shown():
    lg = _make_league_data()
    embed = format_league_embed(lg)
    standings_field = next(f for f in embed["fields"] if "Standings" in f["name"])
    assert "-3,000" in standings_field["value"]


# ---------------------------------------------------------------------------
# format_league_milestone_embed
# ---------------------------------------------------------------------------


def test_league_milestone_embed_title_contains_player_name():
    embed = format_league_milestone_embed("Player1", "Friday Night League")
    assert "Player1" in embed["title"]


def test_league_milestone_embed_title_contains_league_name():
    embed = format_league_milestone_embed("Player1", "Friday Night League")
    assert "Friday Night League" in embed["title"]


def test_league_milestone_embed_title_has_takes_the_lead():
    embed = format_league_milestone_embed("Player1", "Friday Night League")
    assert "takes the lead" in embed["title"]


def test_league_milestone_embed_color_is_gold():
    embed = format_league_milestone_embed("Player1", "Friday Night League")
    assert embed["color"] == 0xFFD700


# ---------------------------------------------------------------------------
# format_webhook_embed — league dispatch routing
# ---------------------------------------------------------------------------


def test_format_webhook_embed_dispatches_league():
    lg = _make_league_data()
    lg["type"] = "league"
    embed = format_webhook_embed(lg)
    assert "League Season Complete" in embed["title"]
    assert embed["color"] == 0xFFD700


def test_format_webhook_embed_league_dispatch_has_standings_field():
    lg = _make_league_data()
    lg["type"] = "league"
    embed = format_webhook_embed(lg)
    standings_fields = [f for f in embed["fields"] if "Standings" in f["name"]]
    assert len(standings_fields) == 1


# ---------------------------------------------------------------------------
# _apply_verbosity — minimal / normal / verbose
# ---------------------------------------------------------------------------


def _make_embed_with_fields():
    return {
        "title": "Test Embed",
        "description": "Test description",
        "color": 0x89b4fa,
        "fields": [
            {"name": "Field1", "value": "Value1", "inline": True},
            {"name": "Field2", "value": "Value2", "inline": False},
        ],
        "thumbnail": {"url": "https://example.com/img.png"},
        "footer": {"text": "Voidstorm Gambling"},
    }


def test_apply_verbosity_minimal_strips_fields():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "minimal")
    assert "fields" not in result


def test_apply_verbosity_minimal_strips_thumbnail():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "minimal")
    assert "thumbnail" not in result


def test_apply_verbosity_minimal_keeps_title():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "minimal")
    assert result["title"] == "Test Embed"


def test_apply_verbosity_minimal_keeps_description():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "minimal")
    assert result["description"] == "Test description"


def test_apply_verbosity_minimal_keeps_color():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "minimal")
    assert result["color"] == 0x89b4fa


def test_apply_verbosity_minimal_keeps_footer():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "minimal")
    assert "footer" in result


def test_apply_verbosity_normal_returns_embed_unchanged():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "normal")
    assert len(result["fields"]) == 2
    assert "thumbnail" in result


def test_apply_verbosity_verbose_returns_embed_unchanged():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "verbose")
    assert len(result["fields"]) == 2
    assert "thumbnail" in result


def test_apply_verbosity_does_not_mutate_original():
    embed = _make_embed_with_fields()
    _ = _apply_verbosity(embed, "minimal")
    # Original embed should still have its fields
    assert "fields" in embed
    assert len(embed["fields"]) == 2


def test_apply_verbosity_unknown_verbosity_treats_as_normal():
    embed = _make_embed_with_fields()
    result = _apply_verbosity(embed, "unknown_level")
    assert len(result["fields"]) == 2


def test_apply_verbosity_minimal_on_embed_without_fields():
    embed = {"title": "No Fields", "color": 0x000000}
    result = _apply_verbosity(embed, "minimal")
    assert result["title"] == "No Fields"
    assert "fields" not in result


# ---------------------------------------------------------------------------
# Consistent footer format (_standard_footer)
# ---------------------------------------------------------------------------


def test_standard_footer_without_timestamp():
    from voidstorm_companion.main import _standard_footer
    footer = _standard_footer()
    assert "Voidstorm Gambling" in footer["text"]


def test_standard_footer_with_timestamp():
    from voidstorm_companion.main import _standard_footer
    footer = _standard_footer(timestamp=1709234567)
    assert "Voidstorm Gambling" in footer["text"]
    # Should include a formatted date/time
    assert "2024" in footer["text"] or "UTC" in footer["text"]


def test_standard_footer_text_key_present():
    from voidstorm_companion.main import _standard_footer
    footer = _standard_footer()
    assert "text" in footer
