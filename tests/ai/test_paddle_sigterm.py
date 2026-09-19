"""Loading Paddle must not take over SIGTERM.

paddle installs glog's failure handler for SIGTERM; a stopped API or worker then
hung in it and segfaulted instead of shutting down. The guard puts the previous
handler back. Tested with a stand-in that replaces the handler, so no model loads.
"""

import ctypes
import signal
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from ocr import provider  # noqa: E402

LIBC = ctypes.CDLL(None)


def _c_handler() -> bytes:
    """The installed SIGTERM handler as the kernel sees it (sa_handler)."""
    action = ctypes.create_string_buffer(256)
    LIBC.sigaction(signal.SIGTERM, None, action)
    return action.raw[:ctypes.sizeof(ctypes.c_void_p)]


def test_sigterm_handler_survives_engine_load(monkeypatch):
    previous = signal.signal(signal.SIGTERM, lambda *_: None)
    try:
        before = _c_handler()

        def hijacking_load(self):
            LIBC.signal(signal.SIGTERM, ctypes.c_void_p(1))  # SIG_IGN, in C, as glog does
            self._engine = object()

        monkeypatch.setattr(provider.PaddleOcrProvider, "_load_engine", hijacking_load)
        provider.PaddleOcrProvider()._get_engine()

        assert _c_handler() == before
    finally:
        signal.signal(signal.SIGTERM, previous)
