"""Thinking stream broadcaster — central nervous system for live thinking.

Thread-safe singleton that receives events from all pipeline stages
(model, translator, executor, vision, audio) and broadcasts to subscribers
(overlay, log file, SSE endpoint).

Events are also written to /tmp/audioshuttle_thinking.jsonl for MCP queries.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

THINKING_LOG_PATH = "/tmp/audioshuttle_thinking.jsonl"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB


@dataclass
class ThinkingEvent:
    """An event in the thinking stream."""

    type: str  # thinking_start, thinking_token, content_token, tool_call, tool_result, error, done
    source: str  # e2b, stt, translator, executor, audio, vision
    text: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "ts": self.timestamp,
            "type": self.type,
            "source": self.source,
            "text": self.text,
        }

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class ThinkingStream:
    """Thread-safe event broadcaster for the thinking stream.

    Singleton pattern: use ThinkingStream.instance() to get the global instance.
    """

    _instance: ThinkingStream | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._subscribers: list[Callable[[ThinkingEvent], None]] = []
        self._recent: list[ThinkingEvent] = []
        self._max_recent = 500
        self._sub_lock = threading.Lock()
        self._log_file = None
        self._log_lock = threading.Lock()
        self._interrupt_flag = threading.Event()

    @classmethod
    def instance(cls) -> ThinkingStream:
        """Get or create the global ThinkingStream singleton."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None

    def emit(self, event: ThinkingEvent) -> None:
        """Broadcast an event to all subscribers and the log file."""
        # Store in recent buffer
        with self._sub_lock:
            self._recent.append(event)
            if len(self._recent) > self._max_recent:
                self._recent = self._recent[-self._max_recent:]

        # Write to JSONL log
        self._write_log(event)

        # Notify subscribers
        with self._sub_lock:
            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.debug("Subscriber error: %s", e)

    def subscribe(self, callback: Callable[[ThinkingEvent], None]) -> None:
        """Register a subscriber callback."""
        with self._sub_lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[ThinkingEvent], None]) -> None:
        """Remove a subscriber callback."""
        with self._sub_lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    def get_recent(self, n: int = 50) -> list[ThinkingEvent]:
        """Return the last N events."""
        with self._sub_lock:
            return list(self._recent[-n:])

    def get_recent_dicts(self, n: int = 50) -> list[dict]:
        """Return the last N events as dicts."""
        return [e.to_dict() for e in self.get_recent(n)]

    # ── Interrupt Support ──────────────────────────────────────

    def interrupt(self, reason: str = "user requested") -> None:
        """Signal an interrupt to the current processing pipeline."""
        self._interrupt_flag.set()
        self.emit(ThinkingEvent(
            type="done",
            source="interrupt",
            text=f"Interrupted: {reason}",
        ))
        logger.info("Thinking stream interrupted: %s", reason)

    def is_interrupted(self) -> bool:
        """Check if an interrupt has been requested."""
        return self._interrupt_flag.is_set()

    def clear_interrupt(self) -> None:
        """Clear the interrupt flag (call at the start of a new command)."""
        self._interrupt_flag.clear()

    # ── Convenience Emitters ───────────────────────────────────

    def emit_thinking(self, text: str, source: str = "e2b") -> None:
        """Emit a thinking/reasoning token."""
        self.emit(ThinkingEvent(type="thinking_token", source=source, text=text))

    def emit_content(self, text: str, source: str = "e2b") -> None:
        """Emit a content/response token."""
        self.emit(ThinkingEvent(type="content_token", source=source, text=text))

    def emit_tool_call(self, tool: str, args: dict, source: str = "translator") -> None:
        """Emit a tool call event."""
        args_str = json.dumps(args, ensure_ascii=False)
        if len(args_str) > 100:
            args_str = args_str[:100] + "..."
        self.emit(ThinkingEvent(
            type="tool_call", source=source,
            text=f"{tool}({args_str})",
        ))

    def emit_tool_result(self, tool: str, success: bool, detail: str = "", source: str = "executor") -> None:
        """Emit a tool result event."""
        status = "OK" if success else "FAIL"
        text = f"{tool} -> {status}"
        if detail:
            text += f": {detail[:80]}"
        self.emit(ThinkingEvent(type="tool_result", source=source, text=text))

    def emit_stt(self, text: str) -> None:
        """Emit a speech-to-text result."""
        self.emit(ThinkingEvent(type="content_token", source="stt", text=f"Heard: {text}"))

    def emit_vision(self, text: str) -> None:
        """Emit a vision analysis event."""
        self.emit(ThinkingEvent(type="thinking_token", source="vision", text=text))

    def emit_audio(self, text: str) -> None:
        """Emit an audio analysis event."""
        self.emit(ThinkingEvent(type="thinking_token", source="audio", text=text))

    def emit_error(self, text: str, source: str = "executor") -> None:
        """Emit an error event."""
        self.emit(ThinkingEvent(type="error", source=source, text=text))

    def emit_done(self, source: str = "e2b") -> None:
        """Emit a done/completion event."""
        self.emit(ThinkingEvent(type="done", source=source))

    # ── Log File ───────────────────────────────────────────────

    def _write_log(self, event: ThinkingEvent) -> None:
        """Append event to JSONL log file with rotation."""
        with self._log_lock:
            try:
                # Rotate if too large
                if os.path.exists(THINKING_LOG_PATH):
                    if os.path.getsize(THINKING_LOG_PATH) > MAX_LOG_SIZE:
                        self._rotate_log()

                with open(THINKING_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(event.to_jsonl() + "\n")
            except Exception as e:
                logger.debug("Thinking log write error: %s", e)

    def _rotate_log(self) -> None:
        """Trim the log file to half the max size."""
        try:
            with open(THINKING_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Keep last half
            keep = lines[len(lines) // 2:]
            with open(THINKING_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(keep)
        except Exception:
            pass

    def close(self) -> None:
        """Clean up resources."""
        with self._sub_lock:
            self._subscribers.clear()
            self._recent.clear()
