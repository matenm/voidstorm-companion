import threading
import time
from voidstorm_companion.window_manager import WindowManager


def test_window_manager_starts_and_stops():
    wm = WindowManager()
    wm.start()
    assert wm._root is not None
    assert wm._thread.is_alive()
    wm.stop()
    time.sleep(0.2)
    assert not wm._thread.is_alive()


def test_window_manager_schedules_on_tk_thread():
    wm = WindowManager()
    wm.start()
    called = threading.Event()

    def callback():
        called.set()

    wm._root.after(0, callback)
    assert called.wait(timeout=2)
    wm.stop()
