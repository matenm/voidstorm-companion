import json
import os
import tempfile

from voidstorm_companion.stats_store import StatsStore


def test_new_store_has_empty_stats():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        assert store.total_sessions == 0
        assert store.total_gold_wagered == 0
        assert store.modes == {}
        assert store.players == {}


def test_update_accumulates_stats():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        sessions = [
            {
                "id": "sess-1",
                "mode": "DIFFERENCE",
                "wager": 50000,
                "rounds": [
                    {
                        "players": [
                            {"name": "Bp"},
                            {"name": "Skatten"},
                        ],
                        "results": {"winner": "Bp", "loser": "Skatten"},
                    }
                ],
            }
        ]
        store.update(sessions)
        assert store.total_sessions == 1
        assert store.total_gold_wagered == 50000
        assert store.modes == {"DIFFERENCE": 1}
        assert store.players["Bp"] == 1
        assert store.players["Skatten"] == 1


def test_update_skips_already_seen():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        sessions = [{"id": "sess-1", "mode": "DIFFERENCE", "wager": 10000, "rounds": [{"players": [{"name": "Bp"}], "results": {}}]}]
        store.update(sessions)
        store.update(sessions)
        assert store.total_sessions == 1


def test_persistence_across_loads():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "stats.json")
        store = StatsStore(path)
        sessions = [{"id": "sess-1", "mode": "DEATHROLL", "wager": 25000, "rounds": [{"players": [{"name": "Koiebar"}, {"name": "Bp"}], "results": {}}]}]
        store.update(sessions)

        store2 = StatsStore(path)
        assert store2.total_sessions == 1
        assert store2.total_gold_wagered == 25000
        assert store2.modes == {"DEATHROLL": 1}
        assert store2.players["Koiebar"] == 1


def test_seen_ids_capped():
    with tempfile.TemporaryDirectory() as d:
        store = StatsStore(os.path.join(d, "stats.json"))
        all_sessions = [{"id": f"sess-{i}", "mode": "DIFFERENCE", "wager": 100, "rounds": [{"players": [], "results": {}}]} for i in range(2100)]
        store.update(all_sessions)
        assert len(store._seen_ids) <= 2000
        assert store.total_sessions == 2100
        assert "sess-2099" in store._seen_ids
        assert "sess-0" not in store._seen_ids
