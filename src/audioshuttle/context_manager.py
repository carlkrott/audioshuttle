"""Rolling context manager for the E2B model's translation sessions."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ContextManager:
    """Manages rolling context for the E2B model's translation sessions.

    Accumulates messages, compacts when limits are reached, and dumps
    compacted sessions to an Obsidian-compatible vault.
    """

    def __init__(
        self,
        model_server: Any | None = None,
        vault_path: str | Path = "~/.audioshuttle/memory",
        max_messages: int = 40,
        max_chars: int = 6000,
    ) -> None:
        self._messages: list[dict[str, Any]] = []
        self._model_server = model_server
        self._vault_path = Path(vault_path).expanduser()
        self._max_messages = max_messages
        self._max_chars = max_chars
        self._lock = threading.Lock()

    def add(self, role: str, content: str) -> None:
        """Append a message and compact if needed."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._messages.append(entry)
            if self._should_compact():
                self._compact()

    def get_messages(self) -> list[dict[str, Any]]:
        """Return current messages list."""
        with self._lock:
            return list(self._messages)

    def clear(self) -> None:
        """Clear all messages without dumping."""
        with self._lock:
            self._messages.clear()

    def _should_compact(self) -> bool:
        """Check if compaction is needed."""
        total_chars = sum(len(m.get("content", "")) for m in self._messages)
        return total_chars > self._max_chars or len(self._messages) > self._max_messages

    def _compact(self) -> None:
        """Compact old messages into a summary, dump old to vault."""
        keep_count = max(5, self._max_messages // 2)
        if len(self._messages) <= keep_count:
            return

        old = self._messages[:-keep_count]
        recent = self._messages[-keep_count:]

        # Dump old messages before discarding
        self._dump_session(old)

        # Generate summary
        summary = self._generate_summary(old)

        self._messages = [
            {
                "role": "system",
                "content": f"Previous session summary: {summary}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            *recent,
        ]

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """Generate a summary of old messages."""
        # Try model-based summarization
        if self._model_server is not None:
            try:
                if hasattr(self._model_server, "is_running") and self._model_server.is_running:
                    old_text = "\n".join(
                        f"{m.get('role', '?').title()}: {m.get('content', '')[:200]}"
                        for m in messages
                    )
                    prompt = (
                        "Summarize this DAW control session in 200 words or less. "
                        "Focus on: user preferences, track names referenced, "
                        "volume/pan settings changed, workflow patterns. "
                        "Be specific about track names and values.\n\n"
                        f"{old_text}"
                    )
                    summary = self._model_server.chat(
                        [{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=300,
                    )
                    if summary:
                        return summary
            except Exception:
                pass  # Fall through to truncation

        # Fallback: simple truncation
        parts = []
        for m in messages:
            content = m.get("content", "")[:100]
            role = m.get("role", "?").title()
            parts.append(f"{role}: {content}")
        return " | ".join(parts)

    def _dump_session(self, messages: list[dict[str, Any]]) -> None:
        """Write messages to Obsidian vault as a markdown session file."""
        try:
            sessions_dir = self._vault_path / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)

            # Create session file
            now = datetime.now(timezone.utc)
            ts_safe = now.isoformat().replace(":", "-").replace("+00:00", "Z")
            session_file = sessions_dir / f"{ts_safe}.md"

            lines = [f"# Session {now.isoformat()}", ""]
            for m in messages:
                role = m.get("role", "?").title()
                content = m.get("content", "")
                ts = m.get("timestamp", "")
                lines.append(f"**{role}** ({ts[:19]}): {content}")
                lines.append("")
            session_file.write_text("\n".join(lines))

            # Update README
            self._update_readme(sessions_dir)
        except Exception:
            pass  # Don't let vault write failures break compaction

    def _update_readme(self, sessions_dir: Path) -> None:
        """Update or create vault README with session index."""
        readme = self._vault_path / "README.md"
        session_files = sorted(sessions_dir.glob("*.md"), reverse=True)

        lines = ["# AudioShuttle Memory Vault", "", "## Sessions", ""]
        lines.append("| Date | Messages | First User Message |")
        lines.append("|------|----------|-------------------|")

        for sf in session_files[:50]:  # Keep last 50
            content = sf.read_text()
            msg_count = content.count("**User**") + content.count("**Assistant**")
            first_user = ""
            for line in content.split("\n"):
                if "**User**" in line:
                    first_user = line.split(":", 2)[-1].strip()[:60]
                    break
            date = sf.stem[:19].replace("T", " ")
            lines.append(f"| {date} | {msg_count} | {first_user} |")

        readme.write_text("\n".join(lines) + "\n")
