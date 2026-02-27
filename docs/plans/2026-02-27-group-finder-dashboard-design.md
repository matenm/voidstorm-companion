# Group Finder Dashboard — Design

## Goal

Add a real-time group finder dashboard to the Voidstorm Companion app so users can browse, sign up for, manage, and create groups without needing to /reload in WoW.

## Architecture

Tkinter window (dark Catppuccin theme, consistent with existing Dashboard/Settings/History windows). GroupSync's existing 3s polling provides live state. The window makes direct API calls for actions (signup, withdraw, create, accept/decline, start, cancel). After each action, an immediate GroupSync refresh is triggered so the UI updates within ~1 second.

## Window Layout

620x700 Tkinter Toplevel window, opened from tray menu ("Group Finder").

Three zones:

1. **Header bar** — "Create Group" button (left), "Refresh" button (right)
2. **Scrollable group list** — Cards for each group, auto-refreshes via GroupSync callbacks
3. **Status bar** — Connection dot + label + group count

### Group Cards

Each card shows:
- Title (e.g., "+12 Ara-Kara") + status badge (OPEN/LOCKED/STARTED)
- Content type, dungeon/raid name, leader name
- Role slots: T 0/1  H 0/1  D 2/3 (color-coded)
- Action buttons based on context:
  - Not signed up → [Sign Up ▾] (opens role picker: Tank / Healer / DPS)
  - Signed up → [Withdraw]
  - Your group → [Cancel] [Start] + expandable signup list

### Leader Signup List

When you're the group leader, the card expands to show all pending/accepted signups:
- Character name, realm, role, status
- [✓] Accept / [✗] Decline buttons for PENDING signups

### Create Group Dialog

Separate Toplevel dialog (~400x500), fields:
- Content Type dropdown (Mythic+ / Raid)
- Dungeon/Raid text field
- Key Level spinbox (M+ only, 2-40)
- Difficulty dropdown (Raids only: Normal / Heroic / Mythic)
- Preset dropdown (Mythic+ 5-man, Raid Normal 10, Raid Heroic 20, Raid Mythic 20, Custom)
- Role composition: Tanks / Healers / DPS spinboxes (auto-filled from preset)
- Character dropdown (populated from GET /api/user/characters via Blizzard API)
- [Create] [Cancel] buttons

Content Type toggles visibility of Key Level vs Difficulty fields. Preset selection auto-fills role composition.

## Data Flow

```
GroupSync (existing, 3s poll)
  ├── GET /api/groups → group list
  ├── GET /api/groups/my-state → mySignups, myGroupSignups, invitePending
  ├── Writes addon state file (existing)
  └── NEW: Fires state_callbacks → window refreshes

Group Finder Window (new)
  ├── Reads from GroupSync: groups, mySignups, myGroupSignups
  ├── Direct API calls for actions:
  │     POST   /api/groups                         → Create
  │     POST   /api/groups/{id}/signup              → Sign up
  │     DELETE  /api/groups/{id}/signup              → Withdraw
  │     PATCH  /api/groups/{id}/signup/{signupId}   → Accept/Decline
  │     PATCH  /api/groups/{id}/start               → Start
  │     PATCH  /api/groups/{id}/cancel              → Cancel
  │     GET    /api/user/characters                 → Character list
  └── After action → GroupSync.force_refresh()
```

## File Changes

### New files (companion)
- `src/voidstorm_companion/group_finder_window.py` — Main window with scrollable group list, cards, actions
- `src/voidstorm_companion/create_group_dialog.py` — Create group form dialog

### Modified files (companion)
- `group_sync.py` — Add callback list for state changes, expose `get_state()`, add `force_refresh()`, store parsed state as accessible attributes
- `window_manager.py` — Add `open_group_finder(group_sync, api_client)` method
- `main.py` — Wire tray menu → group finder, pass GroupSync + ApiClient references
- `tray.py` — Add "Group Finder" menu item (between "Upload Now" and "Dashboard")
- `api_client.py` — Add methods: `signup()`, `withdraw()`, `create_group()`, `accept_signup()`, `decline_signup()`, `start_group()`, `cancel_group()`, `get_characters()`

### Modified files (server)
- `app/api/user/characters/route.ts` — Add companion Bearer token auth (same pattern as my-state route)

## GroupSync Callback Mechanism

GroupSync gains:
- `_state_callbacks: list[Callable]` — registered listeners
- `add_state_callback(cb)` / `remove_state_callback(cb)` — register/unregister
- After each state fetch, call all callbacks with `(groups, my_signups, my_group_signups, invite_pending)`
- `force_refresh()` — sets a flag that triggers immediate state fetch on next poll tick
- `get_state()` — returns current cached state tuple

The window registers its refresh function as a callback on open, unregisters on close.

## Error Handling

- API errors show a brief status message in the status bar (e.g., "Signup failed: 400")
- Network errors don't crash the window — status bar shows "Connection lost"
- Create group validation errors highlighted in the form
- Actions are non-blocking (threaded), with the button disabled during the API call to prevent double-clicks

## Threading

- GroupSync callbacks fire from the GroupSync thread — use `root.after(0, ...)` to marshal UI updates to the Tkinter thread
- Action API calls run in daemon threads — button re-enabled after completion
- Character list fetch runs in a thread when the create dialog opens
