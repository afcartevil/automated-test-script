import signal
import threading
import atexit
from typing import Callable, Dict, List, Optional, Any


class InterruptSignalManager:
    """
    A generic signal manager that invokes registered callbacks when an interrupt signal
    or program exit (atexit) occurs.

    Usage:
        manager = InterruptSignalManager(
            signals=[signal.SIGINT, signal.SIGTERM],
            support_atexit=True
        )
        manager.register(my_cleanup_function)
        manager.activate()
        # Continue with main program

    Methods:
        register(callback): Register a function to be called on signal or exit.
        unregister(callback): Remove a previously registered callback.
        activate(): Install handlers for configured signals and atexit.
        deactivate(): Restore original signal handlers.
    """

    ATEXIT_SIGNAL = -1  # Virtual signal number for atexit callbacks

    def __init__(
            self,
            signals: Optional[List[int]] = None,
            support_atexit: bool = False
    ):
        self._signals = signals or [signal.SIGINT, signal.SIGTERM]
        self._support_atexit = support_atexit
        self._callbacks: List[Callable[[int, Optional[Any]], None]] = []
        self._orig_handlers: Dict[int, Callable] = {}
        self._lock = threading.Lock()
        self._is_activated = False

    def register(self, callback: Callable[[int, Optional[Any]], None], active_if_needed=True) -> None:
        """Register a callback to be invoked on signal or exit."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)
                if active_if_needed:
                    self.activate()

    def unregister(self, callback: Callable[[int, Optional[Any]], None]) -> None:
        """Unregister a previously registered callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def activate(self) -> None:
        """Install handlers and atexit support."""
        if self._is_activated:
            return

        if threading.current_thread() != threading.main_thread():
            return

        self._is_activated = True
        # Setup signal handlers
        for sig in self._signals:
            self._orig_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, self._handle_signal)

        # Setup atexit if required
        if self._support_atexit:
            atexit.register(self._handle_atexit)
        print('POWERTRDE InterruptSignalManager is actived!')

    def deactivate(self) -> None:
        """Restore original signal handlers."""
        if not self._is_activated:
            return
        self._is_activated = False
        for sig, handler in self._orig_handlers.items():
            signal.signal(sig, handler)
        self._orig_handlers.clear()

    def _handle_signal(self, signum: int, frame: Optional[Any]) -> None:
        self._invoke_callbacks(signum, frame)
        # Delegate to original handler
        original = self._orig_handlers.get(signum)
        if callable(original):
            original(signum, frame)

    def _handle_atexit(self) -> None:
        # Simulate a signal for atexit
        self._invoke_callbacks(self.ATEXIT_SIGNAL, None)

    def _invoke_callbacks(self, signum: int, frame: Optional[Any]) -> None:
        with self._lock:
            for callback in list(self._callbacks):
                try:
                    callback(signum, frame)
                except Exception:
                    # Suppress exceptions in cleanup
                    pass


# Example usage
if __name__ == "__main__":
    import subprocess


    def cleanup(signum, frame):
        if signum == InterruptSignalManager.ATEXIT_SIGNAL:
            print("Program exiting, performing atexit cleanup...")
        else:
            print(f"Received signal {signum}, performing signal cleanup...")
        subprocess.run(['adb', 'shell', 'pkill', '-9', 'perfetto'], check=False)


    # Enable both signals and atexit
    manager = InterruptSignalManager(support_atexit=True)
    manager.register(cleanup)
    manager.activate()

    print("Running. Press Ctrl+C or exit to trigger cleanup.")
    try:
        # Simulate work
        while True:
            pass
    except KeyboardInterrupt:
        pass

    manager.deactivate()
