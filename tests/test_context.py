"""Tests for ContextManager."""

from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Thread

import pytest

from audioshuttle.context_manager import ContextManager


def test_add_messages():
    cm = ContextManager(model_server=None, vault_path="/tmp/test-cm", max_messages=100, max_chars=10000)
    cm.add("user", "mute the drums")
    cm.add("assistant", "→ set_track_mute({track: 1, mute: True})")
    messages = cm.get_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_compaction_triggers_at_max_messages():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextManager(model_server=None, vault_path=tmpdir, max_messages=5, max_chars=100000)
        for i in range(10):
            cm.add("user", f"Command {i}")
        messages = cm.get_messages()
        # Should have compacted: summary + last 5 (or close)
        assert len(messages) <= 7  # summary + last 5 + small slack


def test_compaction_triggers_at_max_chars():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextManager(model_server=None, vault_path=tmpdir, max_messages=10, max_chars=100)
        for i in range(20):
            cm.add("user", f"This is a longer message number {i} with extra text to fill up space")
        messages = cm.get_messages()
        # After compaction, should have fewer than original 20
        assert len(messages) < 20


def test_compaction_without_model_server():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextManager(model_server=None, vault_path=tmpdir, max_messages=5, max_chars=500)
        for i in range(10):
            cm.add("user", f"Command {i}")
        messages = cm.get_messages()
        # Truncation fallback should produce a summary message
        assert any(m["role"] == "system" for m in messages)


def test_dump_session_creates_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextManager(model_server=None, vault_path=tmpdir, max_messages=5, max_chars=500)
        for i in range(10):
            cm.add("user", f"Command {i}")
        sessions_dir = Path(tmpdir) / "sessions"
        assert sessions_dir.exists()
        session_files = list(sessions_dir.glob("*.md"))
        assert len(session_files) >= 1


def test_dump_session_creates_readme():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextManager(model_server=None, vault_path=tmpdir, max_messages=5, max_chars=500)
        for i in range(10):
            cm.add("user", f"Command {i}")
        readme = Path(tmpdir) / "README.md"
        assert readme.exists()
        content = readme.read_text()
        assert "AudioShuttle Memory Vault" in content


def test_clear_empties_context():
    cm = ContextManager(model_server=None, vault_path="/tmp/test-cm-clear")
    cm.add("user", "test")
    assert len(cm.get_messages()) == 1
    cm.clear()
    assert len(cm.get_messages()) == 0


def test_vault_path_expansion():
    cm = ContextManager(model_server=None, vault_path="~/test-expand")
    assert str(cm._vault_path).startswith("/")
    assert "~" not in str(cm._vault_path)


def test_thread_safety():
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextManager(model_server=None, vault_path=tmpdir, max_messages=100, max_chars=100000)

        errors = []

        def add_messages(start):
            try:
                for i in range(100):
                    cm.add("user", f"Thread {start} message {i}")
            except Exception as e:
                errors.append(e)

        threads = [Thread(target=add_messages, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All messages should be accounted for (some compacted)
        total = len(cm.get_messages())
        assert total > 0
