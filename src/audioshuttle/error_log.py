"""Thread-safe error log for AudioShuttle."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


class ErrorLog:
    """Thread-safe error log with max entry limit."""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: list[dict[str, Any]] = []
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def add(self, message: str, level: str = "error") -> None:
        """Add an entry with ISO timestamp, trimming to max_entries."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

    def get_recent(self, n: int = 50) -> list[dict[str, Any]]:
        """Return last N entries (most recent last)."""
        with self._lock:
            return list(self._entries[-n:])

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()


# Module-level singleton
error_log = ErrorLog()
