import os
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent


class SavedVariablesWatcher:
    def __init__(self, filepath: str, on_change, debounce_sec: float = 2.0):
        self.filepath = os.path.abspath(filepath)
        self.directory = os.path.dirname(self.filepath)
        self.filename = os.path.basename(self.filepath)
        self.on_change = on_change
        self.debounce_sec = debounce_sec
        self._observer: Observer | None = None
        self._debounce_timer: threading.Timer | None = None

    def _handle_event(self):
        self.on_change(self.filepath)

    def _on_modified(self, event):
        if not isinstance(event, FileModifiedEvent):
            return
        if os.path.basename(event.src_path) != self.filename:
            return
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(self.debounce_sec, self._handle_event)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def start(self):
        handler = FileSystemEventHandler()
        handler.on_modified = self._on_modified
        self._observer = Observer()
        self._observer.schedule(handler, self.directory, recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def stop(self):
        if self._debounce_timer:
            self._debounce_timer.cancel()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
