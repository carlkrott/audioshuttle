"""Integration tests for AudioShuttle web routes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from audioshuttle.config import Settings
from audioshuttle.error_log import ErrorLog
from audioshuttle.web import create_web_app


@pytest.fixture
def client():
    """Create a test client with default settings."""
    settings = Settings(model_enabled=False)
    app = create_web_app(settings)
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client_with_bridge():
    """Create a test client with a mock bridge."""
    settings = Settings(model_enabled=False)
    bridge = MagicMock()
    bridge.is_connected = True
    app = create_web_app(settings, bridge=bridge)
    return TestClient(app, follow_redirects=False)


# ── Home route tests ──────────────────────────────────────────


def test_home_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_home_contains_audiohuttle(client):
    resp = client.get("/")
    assert "AudioShuttle" in resp.text


def test_home_shows_error_log(client):
    """Error log is now on /log tab, not home page."""
    from audioshuttle.error_log import error_log

    error_log.clear()
    error_log.add("Test error message for display")
    # Error log moved to dedicated /log tab
    resp = client.get("/log")
    assert "Test error message for display" in resp.text
    error_log.clear()


def test_home_status_badges(client):
    resp = client.get("/")
    assert "Reaper" in resp.text
    assert "GPU" in resp.text


def test_home_no_errors_message(client):
    """Home page shows activity section instead of error log."""
    from audioshuttle.error_log import error_log

    error_log.clear()
    resp = client.get("/")
    assert "Activity" in resp.text


# ── Input tab tests ───────────────────────────────────────────


def test_input_tab_get(client):
    resp = client.get("/input")
    assert resp.status_code == 200
    assert "textarea" in resp.text


def test_input_save_system_prompt(client):
    resp = client.post(
        "/input/system-prompt", data={"system_prompt": "Test prompt 123"}
    )
    assert resp.status_code == 303
    assert "/input" in resp.headers["location"]


def test_input_save_confirmation(client):
    resp = client.get("/input?saved=1")
    assert resp.status_code == 200
    assert "Saved" in resp.text


def test_input_persists_prompt(client):
    # Save a prompt
    client.post("/input/system-prompt", data={"system_prompt": "You are a DAW assistant that controls Reaper."})
    # Load input page — should show saved prompt
    resp = client.get("/input")
    assert resp.status_code == 200
    assert "DAW assistant that controls Reaper" in resp.text


# ── Output tab tests ──────────────────────────────────────────


def test_output_tab_get(client):
    resp = client.get("/output")
    assert resp.status_code == 200
    assert "Reaper" in resp.text
    assert "Ardour" in resp.text


def test_output_rescan(client):
    resp = client.post("/output/rescan")
    assert resp.status_code == 303


def test_output_daw_preset_change(client):
    resp = client.post("/output/daw-preset", data={"daw_type": "ardour"})
    assert resp.status_code == 303


# ── Navigation tests ──────────────────────────────────────────


def test_nav_tabs_visible(client):
    for path in ["/", "/input", "/output"]:
        resp = client.get(path)
        assert resp.status_code == 200
        assert "Home" in resp.text or 'href="/"' in resp.text
        assert "Input" in resp.text or 'href="/input"' in resp.text
        assert "Output" in resp.text or 'href="/output"' in resp.text


def test_web_app_no_bridge():
    """Web app works without a bridge."""
    settings = Settings(model_enabled=False)
    app = create_web_app(settings)
    c = TestClient(app)
    resp = c.get("/")
    assert resp.status_code == 200


def test_web_app_with_bridge():
    """Web app shows connected status with bridge."""
    settings = Settings(model_enabled=False)
    bridge = MagicMock()
    bridge.is_connected = True
    app = create_web_app(settings, bridge=bridge)
    c = TestClient(app)
    resp = c.get("/")
    assert resp.status_code == 200
    assert "Connected" in resp.text
