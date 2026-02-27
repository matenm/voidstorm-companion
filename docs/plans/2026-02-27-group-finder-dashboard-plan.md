# Group Finder Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a real-time group finder dashboard to the Voidstorm Companion app so users can browse, sign up for, manage, and create groups without needing to /reload in WoW.

**Architecture:** Tkinter window (dark Catppuccin theme) reads live state from GroupSync's 3s polling via callbacks. Direct API calls for actions (signup, withdraw, create, accept/decline, start, cancel). After each action, immediate GroupSync refresh triggers UI update.

**Tech Stack:** Python 3.12, Tkinter, requests, pystray. Server: Next.js 16, Drizzle ORM, Zod.

**User preferences:** No comments in code. No AI attribution. No emojis. Ask before committing.

---

### Task 1: Add companion token auth to /api/user/characters

The existing characters endpoint only supports session auth. We need to add companion Bearer token support so the companion app can fetch the user's WoW characters.

**Files:**
- Modify: `C:\Users\magnu\Documents\git\voidstorm\app\api\user\characters\route.ts`

**Step 1: Add companion token auth**

The current handler starts at line 16 with `export async function GET()`. It only checks `session?.user?.id`. We need to add the same companion token pattern used in `app/api/groups/my-state/route.ts`.

Replace the GET function (lines 16-114) with this version that supports both auth methods:

```typescript
import { NextRequest } from 'next/server';
import { auth } from '@/app/lib/auth';
import { validateCompanionToken } from '@/app/lib/companion-auth';

const BLIZZARD_REGION = process.env.BLIZZARD_REGION || 'eu';

function getApiUrl(region: string) {
  const urls: Record<string, string> = {
    us: 'https://us.api.blizzard.com',
    eu: 'https://eu.api.blizzard.com',
    kr: 'https://kr.api.blizzard.com',
    tw: 'https://tw.api.blizzard.com',
  };
  return urls[region] || urls.eu;
}

export async function GET(req: NextRequest) {
  let userId: string;

  const authHeader = req.headers.get('authorization');
  if (authHeader?.startsWith('Bearer ')) {
    const token = authHeader.slice(7);
    const companion = await validateCompanionToken(token);
    if (!companion) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    userId = companion.userId;
  } else {
    const session = await auth();
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }
    userId = session.user.id;
  }

  // ... rest of handler stays the same, but use userId instead of session.user.id
  // when querying the accounts table:
  //   .where(eq(accounts.userId, userId))
```

Key changes:
- Function signature changes from `GET()` to `GET(req: NextRequest)` to access headers
- Add `import { validateCompanionToken } from '@/app/lib/companion-auth'` and `import { NextRequest } from 'next/server'`
- Auth block checks Bearer token first, falls back to session
- Replace `session.user.id` with `userId` in the accounts query

**Step 2: Test manually**

Test with curl using a companion token:
```bash
curl -H "Authorization: Bearer <token>" https://voidstorm.cc/api/user/characters
```

Expected: JSON response with `{ success: true, data: { characters: [...], total: N } }`

**Step 3: Deploy to VPS**

```bash
ssh voidstorm@185.248.146.191
cd /home/voidstorm/voidstorm
git pull origin main
npm ci && npm run build
cp -r public .next/standalone/public
cp -r .next/static .next/standalone/.next/static
cp .env .next/standalone/.env
pm2 restart voidstorm
```

---

### Task 2: Add group action methods to ApiClient

Extend the companion's ApiClient with methods for all group operations.

**Files:**
- Modify: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\api_client.py`

**Step 1: Add group action methods**

After the existing `upload()` method (line 73), add these methods:

```python
def _headers(self):
    return {
        "Authorization": f"Bearer {self.token}",
        "Content-Type": "application/json",
    }

def get_characters(self) -> list[dict]:
    resp = requests.get(
        f"{self.api_url}/api/user/characters",
        headers=self._headers(),
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Failed to fetch characters (HTTP {resp.status_code})")
    data = resp.json()
    if data.get("success"):
        return data["data"].get("characters", [])
    return []

def create_group(self, payload: dict) -> dict:
    resp = requests.post(
        f"{self.api_url}/api/groups",
        headers=self._headers(),
        json=payload,
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code not in (200, 201):
        raise UploadError(f"Create group failed (HTTP {resp.status_code}): {resp.text}")
    return resp.json().get("data", {})

def signup_group(self, group_id: str, payload: dict) -> dict:
    resp = requests.post(
        f"{self.api_url}/api/groups/{group_id}/signup",
        headers=self._headers(),
        json=payload,
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code not in (200, 201):
        raise UploadError(f"Signup failed (HTTP {resp.status_code}): {resp.text}")
    return resp.json().get("data", {})

def withdraw_group(self, group_id: str) -> dict:
    resp = requests.delete(
        f"{self.api_url}/api/groups/{group_id}/signup",
        headers=self._headers(),
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Withdraw failed (HTTP {resp.status_code})")
    return resp.json().get("data", {})

def accept_signup(self, group_id: str, signup_id: str) -> dict:
    resp = requests.patch(
        f"{self.api_url}/api/groups/{group_id}/signup/{signup_id}",
        headers=self._headers(),
        json={"status": "ACCEPTED"},
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Accept failed (HTTP {resp.status_code})")
    return resp.json().get("data", {})

def decline_signup(self, group_id: str, signup_id: str) -> dict:
    resp = requests.patch(
        f"{self.api_url}/api/groups/{group_id}/signup/{signup_id}",
        headers=self._headers(),
        json={"status": "DECLINED"},
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Decline failed (HTTP {resp.status_code})")
    return resp.json().get("data", {})

def start_group(self, group_id: str) -> dict:
    resp = requests.patch(
        f"{self.api_url}/api/groups/{group_id}/start",
        headers=self._headers(),
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Start failed (HTTP {resp.status_code})")
    return resp.json().get("data", {})

def cancel_group(self, group_id: str) -> dict:
    resp = requests.patch(
        f"{self.api_url}/api/groups/{group_id}/cancel",
        headers=self._headers(),
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Cancel failed (HTTP {resp.status_code})")
    return resp.json().get("data", {})

def lock_group(self, group_id: str) -> dict:
    resp = requests.patch(
        f"{self.api_url}/api/groups/{group_id}/lock",
        headers=self._headers(),
        timeout=10,
    )
    if resp.status_code == 401:
        raise AuthError("Unauthorized")
    if resp.status_code != 200:
        raise UploadError(f"Lock failed (HTTP {resp.status_code})")
    return resp.json().get("data", {})
```

---

### Task 3: Add callback mechanism and state access to GroupSync

GroupSync needs to expose its state to the window and fire callbacks when state changes.

**Files:**
- Modify: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\group_sync.py`

**Step 1: Add state storage and callbacks**

In `__init__` (line 21), add after `self._online = None` (line 32):

```python
self._state_callbacks: list = []
self._groups: list = []
self._my_signups: dict = {}
self._my_group_signups: dict = {}
self._invite_pending: list = []
self._force_refresh = False
```

**Step 2: Add public methods**

After the `stop()` method (line 47), add:

```python
def add_state_callback(self, cb):
    if cb not in self._state_callbacks:
        self._state_callbacks.append(cb)

def remove_state_callback(self, cb):
    if cb in self._state_callbacks:
        self._state_callbacks.remove(cb)

def force_refresh(self):
    self._force_refresh = True

def get_state(self):
    return {
        "groups": self._groups,
        "mySignups": self._my_signups,
        "myGroupSignups": self._my_group_signups,
        "invitePending": self._invite_pending,
        "online": self._online is True,
    }
```

**Step 3: Fire callbacks after state fetch**

In `_fetch_and_write_state()`, after the line `log.info("GroupSync state fetched: %d group(s)", len(groups))` (line 108), add:

```python
self._groups = groups
self._my_signups = my_signups
self._my_group_signups = my_group_signups
self._invite_pending = invite_pending
self._fire_callbacks()
```

Add the `_fire_callbacks` method:

```python
def _fire_callbacks(self):
    for cb in self._state_callbacks:
        try:
            cb(self.get_state())
        except Exception:
            log.exception("GroupSync callback error")
```

**Step 4: Support force_refresh in poll loop**

In `_poll_loop()` (line 49), modify the condition on line 54:

Change:
```python
if processed or state_countdown <= 0:
```
To:
```python
if processed or state_countdown <= 0 or self._force_refresh:
    self._force_refresh = False
```

---

### Task 4: Create the Group Finder window

The main window with scrollable group cards, action buttons, and status bar.

**Files:**
- Create: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\group_finder_window.py`

**Step 1: Create the window module**

This is the largest file. It follows the same pattern as `dashboard_window.py` — a module-level `open_group_finder()` function that creates a `tk.Toplevel`.

The window structure:
1. Header with "Create Group" and "Refresh" buttons
2. Scrollable frame containing group cards
3. Status bar at the bottom

Each group card is a `tk.Frame` with:
- Title + status badge (colored label)
- Content type / dungeon / leader info
- Role slots (T/H/D with color coding)
- Action buttons: Sign Up (with role dropdown), Withdraw, Cancel, Start
- For leader's groups: expandable signup list with Accept/Decline buttons

Key implementation details:

```python
import logging
import threading
import tkinter as tk

from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, GREEN, RED, app_icon_path
from voidstorm_companion.api_client import ApiClient

log = logging.getLogger("voidstorm-companion")

ROLE_COLORS = {
    "TANK": "#33aaff",
    "HEALER": "#33ee55",
    "DPS": "#ff5555",
}

STATUS_COLORS = {
    "OPEN": GREEN,
    "LOCKED": "#7f849c",
    "STARTED": "#00c2ff",
    "FULL": "#ffaa11",
}
```

The `open_group_finder` function signature:

```python
def open_group_finder(group_sync, api_client: ApiClient, parent: tk.Tk):
```

It registers a callback on `group_sync` that calls `parent.after(0, _refresh)` to marshal UI updates to the Tkinter thread. On window close, it unregisters the callback.

**Card layout per group:**

```python
def _create_card(container, group, my_signups, my_group_signups, leader_name, api_client, group_sync, parent):
    card = tk.Frame(container, bg=SURFACE, padx=10, pady=8)
    card.pack(fill="x", padx=4, pady=2)

    is_signed_up = group["id"] in my_signups
    is_leader = group.get("leaderCharName") == leader_name

    # Row 1: Title + Status badge
    # Row 2: Content type, dungeon, leader
    # Row 3: Role slots (T x/y  H x/y  D x/y)
    # Row 4: Action buttons
    # Row 5 (leader only): Signup list with accept/decline
```

**Role picker** — When "Sign Up" is clicked, show a small frame with Tank/Healer/DPS buttons below the Sign Up button:

```python
def _show_role_picker(card, group_id, api_client, group_sync, parent, char_name, char_realm, char_class):
    picker = tk.Frame(card, bg=BG)
    picker.pack(fill="x", pady=(4, 0))
    for role, label in [("TANK", "Tank"), ("HEALER", "Healer"), ("DPS", "DPS")]:
        color = ROLE_COLORS[role]
        btn = tk.Button(picker, text=label, ...)
        btn.pack(side="left", padx=2)
        btn.configure(command=lambda r=role: _do_signup(group_id, r, ...))
```

**Actions run in threads** to avoid blocking the UI:

```python
def _do_signup(group_id, role, api_client, group_sync, btn, char_name, char_realm, char_class):
    btn.configure(state="disabled")
    def work():
        try:
            api_client.signup_group(group_id, {
                "characterName": char_name,
                "realm": char_realm,
                "characterClass": char_class,
                "role": role,
                "source": "WEBSITE",
            })
            group_sync.force_refresh()
        except Exception as e:
            log.error("Signup failed: %s", e)
    threading.Thread(target=work, daemon=True).start()
```

The window needs to know the user's character name/realm for signups. Two options:
- Fetch from `/api/user/characters` on window open (preferred — reuse for create form)
- Store the character list on the window instance and share with create dialog

On window open, fetch characters in a background thread:

```python
self._characters = []
def _fetch_chars():
    try:
        self._characters = api_client.get_characters()
    except Exception:
        pass
threading.Thread(target=_fetch_chars, daemon=True).start()
```

Default character is the first one (highest level). For signup, use the default character's name/realm/class.

**Status bar:**

```python
status_frame = tk.Frame(win, bg=BG, pady=4)
status_frame.pack(fill="x", side="bottom", padx=16)

dot = tk.Label(status_frame, text="●", font=("Segoe UI", 8), bg=BG, fg=GREEN)
dot.pack(side="left")

status_label = tk.Label(status_frame, text="Connected · 0 groups", font=("Segoe UI", 9), bg=BG, fg=FG)
status_label.pack(side="left", padx=(4, 0))
```

**Full refresh cycle:**

```python
def _refresh(state):
    # Called from GroupSync callback via parent.after(0, ...)
    groups = state["groups"]
    my_signups = state["mySignups"]
    my_group_signups = state["myGroupSignups"]
    online = state["online"]

    # Clear all existing cards
    for widget in inner.winfo_children():
        widget.destroy()

    # Rebuild cards
    for group in groups:
        _create_card(inner, group, my_signups, my_group_signups, ...)

    # Update status bar
    dot.configure(fg=GREEN if online else RED)
    status_label.configure(
        text=f"Connected · {len(groups)} group(s)" if online else "Disconnected"
    )
```

---

### Task 5: Create the Create Group dialog

A separate Toplevel dialog for creating new groups.

**Files:**
- Create: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\create_group_dialog.py`

**Step 1: Create the dialog module**

```python
import logging
import threading
import tkinter as tk

from voidstorm_companion.theme import BG, FG, ACCENT, BTN_BG, BTN_HOVER, SURFACE, app_icon_path
from voidstorm_companion.api_client import ApiClient

log = logging.getLogger("voidstorm-companion")

PRESETS = {
    "Mythic+ (5-man)": {"maxSize": 5, "requiredTanks": 1, "requiredHealers": 1, "requiredDps": 3},
    "Raid Normal (10)": {"maxSize": 10, "requiredTanks": 2, "requiredHealers": 2, "requiredDps": 6},
    "Raid Heroic (20)": {"maxSize": 20, "requiredTanks": 2, "requiredHealers": 4, "requiredDps": 14},
    "Raid Mythic (20)": {"maxSize": 20, "requiredTanks": 2, "requiredHealers": 4, "requiredDps": 14},
    "Custom": None,
}

PRESET_API_KEYS = {
    "Mythic+ (5-man)": "MYTHIC_PLUS_5",
    "Raid Normal (10)": "RAID_NORMAL_10",
    "Raid Heroic (20)": "RAID_HEROIC_20",
    "Raid Mythic (20)": "RAID_MYTHIC_20",
    "Custom": "CUSTOM",
}
```

Function signature:

```python
def open_create_group(api_client: ApiClient, group_sync, characters: list[dict], parent: tk.Tk):
```

**Dialog layout (~400x520):**

```
Title:          [___________________]
Content Type:   [Mythic+ ▾]
Dungeon/Raid:   [___________________]
Key Level:      [__] (shown when M+)
Difficulty:     [Normal ▾] (shown when Raid)
Preset:         [Mythic+ (5-man) ▾]
  Tanks: [1]  Healers: [1]  DPS: [3]
Character:      [CharName-Realm ▾]
           [Create]  [Cancel]
```

**Content type switching** — Use `tk.StringVar` with trace to show/hide fields:

```python
content_type_var = tk.StringVar(value="MYTHIC_PLUS")

def _on_content_type_change(*_):
    if content_type_var.get() == "MYTHIC_PLUS":
        key_frame.pack(...)
        diff_frame.pack_forget()
        preset_var.set("Mythic+ (5-man)")
    else:
        key_frame.pack_forget()
        diff_frame.pack(...)
        preset_var.set("Raid Heroic (20)")

content_type_var.trace_add("write", _on_content_type_change)
```

**Preset auto-fill:**

```python
preset_var = tk.StringVar(value="Mythic+ (5-man)")

def _on_preset_change(*_):
    preset = PRESETS.get(preset_var.get())
    if preset:
        tanks_var.set(str(preset["requiredTanks"]))
        healers_var.set(str(preset["requiredHealers"]))
        dps_var.set(str(preset["requiredDps"]))

preset_var.trace_add("write", _on_preset_change)
```

**Character dropdown** — Populated from the `characters` list passed in:

```python
char_options = [f"{c['name']}-{c['realm']}" for c in characters] if characters else ["No characters"]
char_var = tk.StringVar(value=char_options[0] if char_options else "")
char_menu = tk.OptionMenu(form, char_var, *char_options)
```

**Create button handler:**

```python
def _on_create():
    create_btn.configure(state="disabled")
    char_str = char_var.get()
    parts = char_str.rsplit("-", 1)
    char_name = parts[0]
    char_realm = parts[1] if len(parts) > 1 else ""

    char_data = next((c for c in characters if c["name"] == char_name and c["realm"] == char_realm), None)

    payload = {
        "title": title_var.get().strip(),
        "contentType": content_type_var.get(),
        "dungeonOrRaid": dungeon_var.get().strip(),
        "leaderCharName": char_name,
        "leaderRealm": char_realm,
        "preset": PRESET_API_KEYS.get(preset_var.get()),
        "requiredTanks": int(tanks_var.get()),
        "requiredHealers": int(healers_var.get()),
        "requiredDps": int(dps_var.get()),
        "maxSize": int(tanks_var.get()) + int(healers_var.get()) + int(dps_var.get()),
    }

    if content_type_var.get() == "MYTHIC_PLUS":
        try:
            payload["keystoneLevel"] = int(key_level_var.get())
        except ValueError:
            pass
    else:
        payload["difficulty"] = difficulty_var.get()

    def work():
        try:
            api_client.create_group(payload)
            group_sync.force_refresh()
            parent.after(0, dialog.destroy)
        except Exception as e:
            log.error("Create group failed: %s", e)
            parent.after(0, lambda: error_label.configure(text=str(e)))
            parent.after(0, lambda: create_btn.configure(state="normal"))

    threading.Thread(target=work, daemon=True).start()
```

---

### Task 6: Wire up WindowManager, TrayApp, and main.py

Connect the group finder window to the tray menu and application lifecycle.

**Files:**
- Modify: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\window_manager.py`
- Modify: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\tray.py`
- Modify: `C:\Users\magnu\Documents\git\voidstorm-companion\src\voidstorm_companion\main.py`

**Step 1: Add open_group_finder to WindowManager**

In `window_manager.py`, after the `open_dashboard` method (line 47), add:

```python
def open_group_finder(self, group_sync, api_client):
    from voidstorm_companion.group_finder_window import open_group_finder
    if self._root:
        self._root.after(0, lambda: open_group_finder(group_sync, api_client, self._root))
```

**Step 2: Add "Group Finder" to TrayApp**

In `tray.py`, add `on_group_finder=None` parameter to `TrayApp.__init__` (line 37):

```python
def __init__(self, on_upload_now, on_login, on_logout, on_quit,
             on_settings=None, on_history=None, on_dashboard=None,
             on_group_finder=None, on_update=None):
    # ...existing...
    self.on_group_finder = on_group_finder
```

In `_build_menu` (line 56), add a "Group Finder" item. Insert it between the "Upload Now" item and the "Dashboard" item. After the "Upload Now" MenuItem (line 79), add:

```python
pystray.MenuItem(
    "Group Finder",
    lambda: self.on_group_finder() if self.on_group_finder else None,
    enabled=lambda item: self.logged_in,
),
```

**Step 3: Wire up in main.py**

In `main.py`, add a `_do_group_finder` method to the `App` class (after `_do_dashboard` on line 211):

```python
def _do_group_finder(self):
    with self._client_lock:
        client = self.client
    if not client or not self._group_sync:
        return
    self.window_manager.open_group_finder(self._group_sync, client)
```

In the `TrayApp` constructor call (line 303), add:

```python
on_group_finder=self._do_group_finder,
```

---

### Task 7: Build and test end-to-end

**Step 1: Run the companion in dev mode**

```bash
cd C:\Users\magnu\Documents\git\voidstorm-companion
py -m voidstorm_companion.main
```

**Step 2: Test the flow**

1. Right-click tray icon → Group Finder
2. Verify window opens with dark theme
3. Verify groups load (should see any active groups)
4. Verify status bar shows "Connected"
5. Click "Create Group" → verify dialog opens with character dropdown
6. Create a M+ group → verify it appears in the list
7. From another account (or the website), sign up → verify signup appears in real-time
8. Accept/decline signups from the companion
9. Test Sign Up with role picker → verify it works
10. Test Withdraw → verify button changes back to Sign Up
11. Test Cancel Group → verify group disappears
12. Test Start Group → verify status changes

**Step 3: Build the executable**

```bash
cd C:\Users\magnu\Documents\git\voidstorm-companion
rm -rf build dist
py -m PyInstaller voidstorm-companion.spec --noconfirm
```

Verify `dist/VoidstormCompanion/VoidstormCompanion.exe` runs correctly.
