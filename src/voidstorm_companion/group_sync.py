import hashlib
import hmac
import json
import logging
import os
import threading
import time

import requests

log = logging.getLogger("voidstorm-companion")

POLL_INTERVAL = 3.0
COMMAND_POLL_INTERVAL = 0.5
STATE_FILENAME = "VoidstormGroupSync.lua"
AUTH_KEY_FILENAME = "VoidstormAuthKey.lua"
COMMANDS_FILENAME = "VoidstormMatchmaking.lua"
MAX_COMMAND_RETRIES = 5


def _fire_windows_toast(title: str, message: str) -> None:
    """Send a Windows balloon/toast notification via ctypes shell API.

    Non-critical — any failure is silently swallowed so the caller is never
    disrupted by notification infrastructure issues.
    """
    try:
        # NIIF_NOSOUND = 0x00000010, NIIF_INFO = 0x00000001
        # Shell_NotifyIconW is the Win32 entry point for tray notifications.
        # We use a simple MessageBeep + a hidden approach: leverage
        # win10toast-style Shell_NotifyIcon via ctypes if available,
        # otherwise fall back to a non-blocking approach.
        #
        # Simplest reliable approach without a third-party library: use the
        # Windows Script Host COM object (wscript.shell popup) — but that
        # blocks. Instead use ctypes to call Shell_NotifyIconW directly.
        #
        # The lightest dependency-free path on Win32 is to call
        # ToastNotificationManager via WinRT COM, but that requires
        # comtypes. Use PowerShell as an out-of-process launcher instead,
        # which is always available on Windows 10+.
        import subprocess
        safe_title = title.replace("'", "''")
        safe_message = message.replace("'", "''")
        ps_script = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; "
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
            "ContentType=WindowsRuntime] | Out-Null; "
            "$xml = [Windows.UI.Notifications.ToastNotificationManager]"
            "::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$nodes = $xml.GetElementsByTagName('text'); "
            f"$nodes.Item(0).AppendChild($xml.CreateTextNode('{safe_title}')); "
            f"$nodes.Item(1).AppendChild($xml.CreateTextNode('{safe_message}')); "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            "$notifier = [Windows.UI.Notifications.ToastNotificationManager]"
            "::CreateToastNotifier('Voidstorm Companion'); "
            "$notifier.Show($toast)"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except Exception:
        log.debug("GroupSync toast notification failed (non-critical)", exc_info=True)


class GroupSync:
    def __init__(self, api_url: str, token: str, addon_path: str, sv_dirs: list[str]):
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.addon_path = addon_path
        self.sv_dirs = sv_dirs
        self._running = False
        self._thread: threading.Thread | None = None
        self._hmac_key = hashlib.sha256(
            (token + ":voidstorm-group-sync").encode()
        ).digest()
        self._last_state_written = False
        self._online = None
        self._state_callbacks: list = []
        self._groups: list = []
        self._my_signups: dict = {}
        self._my_group_signups: dict = {}
        self._invite_pending: list = []
        self._force_refresh = False
        # Task 7b: change-detection and sync versioning
        self._sync_version: int = int(time.time())
        self._prev_groups: list | None = None
        self._auth_key_written: bool = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("GroupSync started (poll every %.1fs)", POLL_INTERVAL)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log.info("GroupSync stopped")

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

    def _fire_callbacks(self):
        for cb in self._state_callbacks:
            try:
                cb(self.get_state())
            except Exception:
                log.exception("GroupSync callback error")

    def _poll_loop(self):
        state_countdown = 0.0
        while self._running:
            try:
                processed = self._process_commands()
                if processed or state_countdown <= 0 or self._force_refresh:
                    self._force_refresh = False
                    self._fetch_and_write_state()
                    state_countdown = POLL_INTERVAL
            except Exception:
                log.exception("GroupSync poll error")
            time.sleep(COMMAND_POLL_INTERVAL)
            state_countdown -= COMMAND_POLL_INTERVAL

    def _set_online(self, online: bool):
        if self._online is not online:
            self._online = online
            if online:
                log.info("GroupSync connection state: online")
            else:
                log.warning("GroupSync connection state: offline")

    def _fetch_and_write_state(self):
        try:
            resp = requests.get(
                f"{self.api_url}/api/groups",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10,
            )
            if resp.status_code != 200:
                log.warning("GroupSync fetch failed: HTTP %d", resp.status_code)
                self._set_online(False)
                return

            data = resp.json()
            if not data.get("success"):
                self._set_online(False)
                return

            self._set_online(True)
            groups = data.get("data", [])

            my_signups = {}
            invite_pending = []
            my_group_signups = {}
            try:
                state_resp = requests.get(
                    f"{self.api_url}/api/groups/my-state",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=10,
                )
                if state_resp.status_code == 200:
                    state_data = state_resp.json()
                    if state_data.get("success"):
                        my_signups = state_data["data"].get("mySignups", {})
                        invite_pending = state_data["data"].get("invitePending", [])
                        my_group_signups = state_data["data"].get("myGroupSignups", {})
            except requests.RequestException:
                pass

            log.info("GroupSync state fetched: %d group(s)", len(groups))

            # Task 7b: compute change summary before updating internal state.
            # Skip on the first poll (_prev_groups is None) to avoid a spurious
            # toast notification that compares against an empty baseline.
            if self._prev_groups is not None:
                change_summary = self._compute_change_summary(self._prev_groups, groups)
                has_meaningful_change = bool(change_summary)
            else:
                change_summary = ""
                has_meaningful_change = False

            self._groups = groups
            self._my_signups = my_signups
            self._my_group_signups = my_group_signups
            self._invite_pending = invite_pending
            self._fire_callbacks()

            ts = int(time.time())
            payload = json.dumps({"timestamp": ts, "groups": groups}, separators=(",", ":"))
            sig = hmac.new(self._hmac_key, payload.encode(), hashlib.sha256).hexdigest()

            # Task 7b: increment sync version counter
            self._sync_version += 1

            summary_str = change_summary if change_summary else "No changes"
            lua = self._to_lua_state(
                ts, sig, groups, my_signups, invite_pending, my_group_signups,
                payload=payload,
                sync_version=self._sync_version,
                last_sync_time=ts,
                change_summary=summary_str,
            )

            # Task 3: write VoidstormGroupSync.lua atomically
            state_path = os.path.join(self.addon_path, STATE_FILENAME)
            tmp_path = state_path + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(lua)
                os.replace(tmp_path, state_path)
            except BaseException:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            # Task 3: write VoidstormAuthKey.lua atomically alongside sync file,
            # but only once per session — the key never changes within a run.
            if not self._auth_key_written:
                self._write_auth_key()
                self._auth_key_written = True

            self._last_state_written = True

            # Task 7b: save current groups as previous state for next diff
            self._prev_groups = groups

            # Task 7b: fire Windows toast notification on meaningful group changes
            if has_meaningful_change:
                log.info("GroupSync meaningful change detected: %s", change_summary)
                _fire_windows_toast(
                    "Voidstorm — Groups Updated",
                    f"{change_summary}. Reload in-game to see changes.",
                )
        except requests.RequestException:
            log.warning("GroupSync network error — preserving last known state")
            self._set_online(False)
        except Exception:
            log.exception("GroupSync write error")

    def _process_commands(self) -> bool:
        processed = False
        for sv_dir in self.sv_dirs:
            if self._process_commands_in(sv_dir):
                processed = True
        return processed

    def _process_commands_in(self, sv_dir: str) -> bool:
        cmd_path = os.path.join(sv_dir, COMMANDS_FILENAME)
        if not os.path.exists(cmd_path):
            return False

        try:
            with open(cmd_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content or "commands" not in content:
                return False

            from .lua_parser import parse_lua_table
            data = parse_lua_table(content, "VoidstormGroupCommands")
            commands = data.get("commands", [])
            if not commands:
                return False

            reopen_ui = data.get("reopenUI")

            failed = []
            for cmd in commands:
                retry_count = int(cmd.get("retryCount", 0))
                if retry_count >= MAX_COMMAND_RETRIES:
                    log.warning(
                        "GroupSync discarding command after %d retries: action=%s groupId=%s",
                        retry_count,
                        cmd.get("action"),
                        cmd.get("groupId"),
                    )
                    continue
                success = self._execute_command(cmd)
                if not success:
                    cmd["retryCount"] = retry_count + 1
                    failed.append(cmd)

            reopen_lua = ""
            if reopen_ui:
                reopen_lua = "  reopenUI = true,\n"

            if not failed:
                with open(cmd_path, "w", encoding="utf-8") as f:
                    f.write(f'VoidstormGroupCommands = {{\n{reopen_lua}  commands = {{}},\n}}\n')
            else:
                remaining_lua = self._to_lua_commands(failed, reopen_ui=reopen_ui)
                with open(cmd_path, "w", encoding="utf-8") as f:
                    f.write(remaining_lua)
                log.warning(
                    "GroupSync retained %d failed command(s) for retry", len(failed)
                )

            log.info("GroupSync processed %d command(s)", len(commands))
            return True

        except Exception:
            log.exception("GroupSync command processing error")
            return False

    def _execute_command(self, cmd: dict) -> bool:
        action = cmd.get("action")
        group_id = cmd.get("groupId")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            try:
                resp = None
                if action == "SIGNUP":
                    payload = {
                        "characterName": cmd.get("characterName"),
                        "realm": cmd.get("realm"),
                        "characterClass": cmd.get("characterClass"),
                        "spec": cmd.get("spec"),
                        "role": cmd.get("role"),
                        "availableRoles": cmd.get("availableRoles"),
                        "ilvl": cmd.get("ilvl"),
                        "mythicPlusScore": cmd.get("mythicPlusScore"),
                        "source": "ADDON",
                    }
                    payload = {k: v for k, v in payload.items() if v is not None}
                    resp = requests.post(
                        f"{self.api_url}/api/groups/{group_id}/signup",
                        headers=headers,
                        json=payload,
                        timeout=10,
                    )
                elif action == "WITHDRAW":
                    resp = requests.delete(
                        f"{self.api_url}/api/groups/{group_id}/signup",
                        headers=headers,
                        timeout=10,
                    )
                elif action == "START_GROUP":
                    resp = requests.patch(
                        f"{self.api_url}/api/groups/{group_id}/start",
                        headers=headers,
                        timeout=10,
                    )
                elif action == "LOCK":
                    resp = requests.patch(
                        f"{self.api_url}/api/groups/{group_id}/lock",
                        headers=headers,
                        timeout=10,
                    )
                elif action == "CANCEL":
                    resp = requests.patch(
                        f"{self.api_url}/api/groups/{group_id}/cancel",
                        headers=headers,
                        timeout=10,
                    )
                elif action in ("ACCEPT_SIGNUP", "DECLINE_SIGNUP"):
                    signup_id = cmd.get("signupId")
                    new_status = "ACCEPTED" if action == "ACCEPT_SIGNUP" else "DECLINED"
                    resp = requests.patch(
                        f"{self.api_url}/api/groups/{group_id}/signup/{signup_id}",
                        headers=headers,
                        json={"status": new_status},
                        timeout=10,
                    )
                else:
                    log.warning("Unknown group command: %s", action)
                    return True

                if resp is not None and resp.status_code < 500:
                    log.info(
                        "GroupSync command succeeded: action=%s groupId=%s status=%d",
                        action,
                        group_id,
                        resp.status_code,
                    )
                    return True

                if attempt < 2:
                    time.sleep(2)

            except requests.RequestException:
                if attempt < 2:
                    time.sleep(2)
                else:
                    log.warning(
                        "GroupSync command failed after 3 attempts: action=%s groupId=%s",
                        action,
                        group_id,
                    )
                    return False

        log.warning(
            "GroupSync command failed: action=%s groupId=%s",
            action,
            group_id,
        )
        return False

    def _write_auth_key(self) -> None:
        """Task 3: Atomically write VoidstormAuthKey.lua to the addon directory.

        Format: VoidstormAuthKey = "<hex-encoded-hmac-key>"
        """
        auth_key_path = os.path.join(self.addon_path, AUTH_KEY_FILENAME)
        tmp_path = auth_key_path + ".tmp"
        hex_key = self._hmac_key.hex()
        content = f'VoidstormAuthKey = "{hex_key}"\n'
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, auth_key_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        log.debug("GroupSync wrote auth key to %s", auth_key_path)

    @staticmethod
    def _compute_change_summary(prev_groups: list, curr_groups: list) -> str:
        """Task 7b: Diff previous and current groups lists.

        Returns a human-readable summary string when there are meaningful
        differences (new groups, closed groups, signup count changes).
        Returns an empty string when nothing changed.
        """
        prev_by_id: dict = {g.get("id"): g for g in prev_groups}
        curr_by_id: dict = {g.get("id"): g for g in curr_groups}

        prev_ids = set(prev_by_id)
        curr_ids = set(curr_by_id)

        new_ids = curr_ids - prev_ids
        removed_ids = prev_ids - curr_ids

        # Count groups that became closed/cancelled/started
        newly_closed: list[str] = []
        signup_increases: int = 0
        signup_decreases: int = 0

        for gid in curr_ids & prev_ids:
            prev_g = prev_by_id[gid]
            curr_g = curr_by_id[gid]

            prev_status = prev_g.get("status", "")
            curr_status = curr_g.get("status", "")
            if prev_status not in ("CLOSED", "CANCELLED", "STARTED") and curr_status in (
                "CLOSED", "CANCELLED", "STARTED"
            ):
                newly_closed.append(curr_status.lower())

            prev_signups = int(prev_g.get("totalSignups", 0))
            curr_signups = int(curr_g.get("totalSignups", 0))
            delta = curr_signups - prev_signups
            if delta > 0:
                signup_increases += delta
            elif delta < 0:
                signup_decreases += abs(delta)

        parts: list[str] = []
        if new_ids:
            n = len(new_ids)
            parts.append(f"{n} new group{'s' if n != 1 else ''}")
        if removed_ids:
            n = len(removed_ids)
            parts.append(f"{n} group{'s' if n != 1 else ''} removed")
        if newly_closed:
            # Summarise by status word, e.g. "1 group closed, 1 group started"
            from collections import Counter
            for status, count in Counter(newly_closed).items():
                parts.append(f"{count} group{'s' if count != 1 else ''} {status}")
        if signup_increases:
            parts.append(
                f"{signup_increases} new signup{'s' if signup_increases != 1 else ''}"
            )
        if signup_decreases:
            parts.append(
                f"{signup_decreases} signup{'s' if signup_decreases != 1 else ''} withdrawn"
            )

        return ", ".join(parts)

    def _to_lua_commands(self, commands: list, reopen_ui: bool = False) -> str:
        lines = ['VoidstormGroupCommands = {']
        if reopen_ui:
            lines.append('  reopenUI = true,')
        lines.append('  commands = {')
        for cmd in commands:
            parts = []
            for k, v in cmd.items():
                if v is None:
                    continue
                if isinstance(v, bool):
                    parts.append(f'{k} = {"true" if v else "false"}')
                elif isinstance(v, (int, float)):
                    parts.append(f'{k} = {v}')
                elif isinstance(v, list):
                    inner = ", ".join(f'"{self._esc(str(i))}"' for i in v)
                    parts.append(f'{k} = {{{inner}}}')
                else:
                    parts.append(f'{k} = "{self._esc(str(v))}"')
            lines.append('    { ' + ', '.join(parts) + ' },')
        lines.append('  },')
        lines.append('}')
        return '\n'.join(lines) + '\n'

    def _to_lua_state(self, ts: int, sig: str, groups: list,
                       my_signups: dict | None = None,
                       invite_pending: list | None = None,
                       my_group_signups: dict | None = None,
                       payload: str | None = None,
                       sync_version: int = 0,
                       last_sync_time: int | None = None,
                       change_summary: str = "") -> str:
        lines = ['VoidstormGroupSync = {']
        lines.append(f'  timestamp = {ts},')
        lines.append(f'  hmac = "{sig}",')
        # Task 7b: sync version counter — monotonically increasing per write
        lines.append(f'  syncVersion = {sync_version},')
        # Task 7b: Unix timestamp of this sync write
        lines.append(f'  lastSyncTime = {last_sync_time if last_sync_time is not None else ts},')
        # Task 7b: human-readable change description
        lines.append(f'  changeSummary = "{self._esc(change_summary)}",')
        # Task 3: exact JSON string that was HMAC'd so the addon can verify
        if payload is not None:
            lines.append(f'  jsonPayload = "{self._esc(payload)}",')
        lines.append('  groups = {')
        for g in groups:
            lines.append('    {')
            lines.append(f'      id = "{self._esc(g.get("id", ""))}",')
            lines.append(f'      title = "{self._esc(g.get("title", ""))}",')
            lines.append(f'      contentType = "{self._esc(g.get("contentType", ""))}",')
            lines.append(f'      difficulty = "{self._esc(g.get("difficulty", "") or "")}",')
            lines.append(f'      keystoneLevel = {g.get("keystoneLevel") or 0},')
            lines.append(f'      dungeonOrRaid = "{self._esc(g.get("dungeonOrRaid", ""))}",')
            lines.append(f'      status = "{self._esc(g.get("status", ""))}",')
            lines.append(f'      maxSize = {g.get("maxSize", 5)},')
            lines.append(f'      requiredTanks = {g.get("requiredTanks", 1)},')
            lines.append(f'      requiredHealers = {g.get("requiredHealers", 1)},')
            lines.append(f'      requiredDps = {g.get("requiredDps", 3)},')
            lines.append(f'      leaderCharName = "{self._esc(g.get("leaderCharName", ""))}",')
            lines.append(f'      leaderRealm = "{self._esc(g.get("leaderRealm", ""))}",')
            lines.append(f'      acceptedTanks = {g.get("acceptedTanks", 0)},')
            lines.append(f'      acceptedHealers = {g.get("acceptedHealers", 0)},')
            lines.append(f'      acceptedDps = {g.get("acceptedDps", 0)},')
            lines.append(f'      totalSignups = {g.get("totalSignups", 0)},')
            lines.append('    },')
        lines.append('  },')
        lines.append('  mySignups = {')
        for gid, info in (my_signups or {}).items():
            lines.append(f'    ["{self._esc(gid)}"] = {{')
            lines.append(f'      status = "{self._esc(info.get("status", ""))}",')
            lines.append(f'      role = "{self._esc(info.get("role", ""))}",')
            lines.append('    },')
        lines.append('  },')
        lines.append('  invitePending = {')
        for name_realm in (invite_pending or []):
            lines.append(f'    "{self._esc(name_realm)}",')
        lines.append('  },')
        lines.append('  myGroupSignups = {')
        for gid, signups in (my_group_signups or {}).items():
            lines.append(f'    ["{self._esc(gid)}"] = {{')
            for s in signups:
                lines.append('      {')
                lines.append(f'        id = "{self._esc(s.get("id", ""))}",')
                lines.append(f'        characterName = "{self._esc(s.get("characterName", ""))}",')
                lines.append(f'        realm = "{self._esc(s.get("realm", ""))}",')
                lines.append(f'        characterClass = "{self._esc(s.get("characterClass", ""))}",')
                lines.append(f'        spec = "{self._esc(s.get("spec", "") or "")}",')
                lines.append(f'        role = "{self._esc(s.get("role", ""))}",')
                lines.append(f'        ilvl = {s.get("ilvl") or 0},')
                lines.append(f'        status = "{self._esc(s.get("status", ""))}",')
                lines.append('      },')
            lines.append('    },')
        lines.append('  },')
        lines.append('}')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _esc(s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
