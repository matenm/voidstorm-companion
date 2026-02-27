# Dashboard Feature Design

**Goal:** Add a combined Dashboard window showing lifetime stats and recent session activity, powered by local data.

**Architecture:** Stats are persisted in a lightweight `stats.json` file that accumulates counters as sessions are parsed. Recent session details come from live SavedVariables on disk. This means lifetime stats survive addon history clears, while the session feed reflects current on-disk state.

## Data Layer: StatsStore

New file: `src/voidstorm_companion/stats_store.py`

Stored at `~/.voidstorm-companion/stats.json`. Updated each time sessions are parsed (during the upload flow in `_do_upload`).

Schema:
```json
{
  "total_sessions": 42,
  "total_gold_wagered": 1250000,
  "modes": {"DIFFERENCE": 30, "DEATHROLL": 12},
  "players": {"Bp": 35, "Skatten": 20, "Koiebar": 15},
  "session_ids_seen": ["1740934800-5432", "1740935000-1111"]
}
```

- `session_ids_seen` prevents double-counting when the same session is parsed multiple times
- Cap `session_ids_seen` at 2000 entries (FIFO) to prevent unbounded growth
- Uses same atomic write pattern as other stores (tempfile + os.replace)
- Thread-safe with a lock

### Integration with upload flow

In `main.py _do_upload`, after parsing sessions and before uploading, call `self.stats.update(sessions)` to accumulate stats from any new (unseen) sessions.

## Dashboard Window

New file: `src/voidstorm_companion/dashboard_window.py`

Single tkinter Toplevel window opened from tray menu via WindowManager.

### Top Section: Lifetime Stats (from stats.json)
Compact grid with Catppuccin Mocha theme:
- Total Sessions count
- Total Gold Wagered (formatted with commas)
- Mode breakdown (e.g. "30 Difference, 12 Deathroll")
- Top 3 most active players

### Bottom Section: Recent Sessions (from SavedVariables)
Scrollable list, most recent first, showing:
- Relative timestamp
- Mode + wager (e.g. "DIFFERENCE - 50,000g")
- Result summary from results.summary field
- Channel

Shows "No sessions on disk" when SavedVariables is empty/cleared.

Uses alternating row colors (same pattern as history window).

### Data Loading
- Stats loaded from StatsStore (always available)
- Recent sessions loaded by calling `parse_savedvariables()` on configured paths
- Data loaded once when window opens (no live refresh needed)

## Tray Menu Integration

Add "Dashboard" entry to tray menu between "Upload Now" and "Upload History". The existing Upload History stays — it shows upload sync status while Dashboard shows game data.

## Files Modified/Created

- `src/voidstorm_companion/stats_store.py` (new) - StatsStore class
- `src/voidstorm_companion/dashboard_window.py` (new) - Dashboard window
- `src/voidstorm_companion/window_manager.py` (modify) - add open_dashboard method
- `src/voidstorm_companion/main.py` (modify) - create StatsStore, wire to upload flow, add tray callback
- `src/voidstorm_companion/tray.py` (modify) - add Dashboard menu entry
- `src/voidstorm_companion/config.py` (modify) - add STATS_PATH constant
