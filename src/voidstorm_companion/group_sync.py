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
STATE_FILENAME = "VoidstormGroupSync.lua"
COMMANDS_FILENAME = "VoidstormGroupCommands.lua"
MAX_COMMAND_RETRIES = 5


class GroupSync:
    def __init__(self, api_url: str, token: str, addon_path: str):
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.addon_path = addon_path
        self._running = False
        self._thread: threading.Thread | None = None
        self._hmac_key = hashlib.sha256(
            (token + ":voidstorm-group-sync").encode()
        ).digest()
        self._last_state_written = False
        self._online = None

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

    def _poll_loop(self):
        while self._running:
            try:
                self._process_commands()
                self._fetch_and_write_state()
            except Exception:
                log.exception("GroupSync poll error")
            time.sleep(POLL_INTERVAL)

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
            except requests.RequestException:
                pass

            log.info("GroupSync state fetched: %d group(s)", len(groups))
            ts = int(time.time())
            payload = json.dumps({"timestamp": ts, "groups": groups}, separators=(",", ":"))
            sig = hmac.new(self._hmac_key, payload.encode(), hashlib.sha256).hexdigest()

            lua = self._to_lua_state(ts, sig, groups, my_signups, invite_pending)
            state_path = os.path.join(self.addon_path, STATE_FILENAME)
            tmp_path = state_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(lua)
            os.replace(tmp_path, state_path)
            self._last_state_written = True
        except requests.RequestException:
            log.warning("GroupSync network error — preserving last known state")
            self._set_online(False)
        except Exception:
            log.exception("GroupSync write error")

    def _process_commands(self):
        cmd_path = os.path.join(self.addon_path, COMMANDS_FILENAME)
        if not os.path.exists(cmd_path):
            return

        try:
            with open(cmd_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content or "commands" not in content:
                return

            from .lua_parser import parse_lua_table
            data = parse_lua_table(content, "VoidstormGroupCommands")
            commands = data.get("commands", [])
            if not commands:
                return

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

            if not failed:
                with open(cmd_path, "w", encoding="utf-8") as f:
                    f.write('VoidstormGroupCommands = { commands = {} }\n')
            else:
                remaining_lua = self._to_lua_commands(failed)
                with open(cmd_path, "w", encoding="utf-8") as f:
                    f.write(remaining_lua)
                log.warning(
                    "GroupSync retained %d failed command(s) for retry", len(failed)
                )

        except Exception:
            log.exception("GroupSync command processing error")

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
                    resp = requests.post(
                        f"{self.api_url}/api/groups/{group_id}/signup",
                        headers=headers,
                        json={
                            "characterName": cmd.get("characterName"),
                            "realm": cmd.get("realm"),
                            "characterClass": cmd.get("characterClass"),
                            "spec": cmd.get("spec"),
                            "role": cmd.get("role"),
                            "availableRoles": cmd.get("availableRoles"),
                            "ilvl": cmd.get("ilvl"),
                            "mythicPlusScore": cmd.get("mythicPlusScore"),
                            "source": "ADDON",
                        },
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

    def _to_lua_commands(self, commands: list) -> str:
        lines = ['VoidstormGroupCommands = { commands = {']
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
            lines.append('  { ' + ', '.join(parts) + ' },')
        lines.append('} }')
        return '\n'.join(lines) + '\n'

    def _to_lua_state(self, ts: int, sig: str, groups: list,
                       my_signups: dict | None = None,
                       invite_pending: list | None = None) -> str:
        lines = ['VoidstormGroupSync = {']
        lines.append(f'  timestamp = {ts},')
        lines.append(f'  hmac = "{sig}",')
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
        lines.append('}')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _esc(s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
