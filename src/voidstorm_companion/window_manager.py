import threading
import tkinter as tk


class WindowManager:
    def __init__(self):
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._ready.set()
        self._root.mainloop()

    def open_history(self, history):
        from voidstorm_companion.history_window import open_history
        if self._root:
            self._root.after(0, lambda: open_history(history, self._root))

    def open_settings(self, config):
        from voidstorm_companion.settings_window import open_settings
        if self._root:
            self._root.after(0, lambda: open_settings(config, self._root))

    def stop(self):
        if self._root:
            self._root.after(0, self._root.quit)
