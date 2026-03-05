import os
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileModifiedEvent,
    FileMovedEvent,
    FileCreatedEvent,
)

try:
    import psutil
except ImportError:
    psutil = None

log = logging.getLogger("voidstorm-companion")

WOW_PROCESS_NAMES = {"wow.exe", "wowclassic.exe", "wow-64.exe", "wowt.exe", "wowb.exe"}
_POLL_INTERVAL = 5.0


class WowProcessWatcher:
    def __init__(self, on_exit, poll_interval: float = _POLL_INTERVAL):
        self.on_exit = on_exit
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._was_running = False

    @staticmethod
    def _is_wow_running() -> bool:
        if psutil is None:
            return False
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() in WOW_PROCESS_NAMES:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def _poll_loop(self):
        while not self._stop_event.is_set():
            is_running = self._is_wow_running()
            if self._was_running and not is_running:
                log.info("WoW process exited — triggering upload")
                try:
                    self.on_exit()
                except Exception:
                    log.exception("WoW exit callback failed")
            self._was_running = is_running
            self._stop_event.wait(self.poll_interval)

    def start(self):
        if psutil is None:
            log.warning("psutil not installed — WoW process watching disabled")
            return
        self._stop_event.clear()
        self._was_running = self._is_wow_running()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)


class SavedVariablesWatcher:
    def __init__(self, filepath: str, on_change, debounce_sec: float = 2.0):
        self.filepath = os.path.abspath(filepath)
        self.directory = os.path.dirname(self.filepath)
        self.filename = os.path.basename(self.filepath)
        self.on_change = on_change
        self.debounce_sec = debounce_sec
        self._observer: Observer | None = None
        self._debounce_timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()

    def _handle_event(self):
        self.on_change(self.filepath)

    def _schedule_debounce(self):
        with self._timer_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(self.debounce_sec, self._handle_event)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _on_any_event(self, event):
        if isinstance(event, FileMovedEvent):
            if os.path.basename(event.dest_path) == self.filename:
                log.debug(f"File renamed to {self.filename}")
                self._schedule_debounce()
        elif isinstance(event, (FileModifiedEvent, FileCreatedEvent)):
            if os.path.basename(event.src_path) == self.filename:
                log.debug(f"File modified/created: {self.filename}")
                self._schedule_debounce()

    def start(self):
        handler = FileSystemEventHandler()
        handler.on_any_event = self._on_any_event
        self._observer = Observer()
        self._observer.schedule(handler, self.directory, recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def stop(self):
        with self._timer_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
