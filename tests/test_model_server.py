"""Tests for model server lifecycle management."""

import json
from unittest.mock import MagicMock, patch

import pytest

from audioshuttle.config import Settings
from audioshuttle.model_server import ModelServer


class TestModelServerConfig:
    """Test Settings has model server config."""

    def test_default_settings(self):
        s = Settings()
        assert s.model_enabled is True
        assert s.model_gpu_device == 0
        assert s.model_name == "gemma-4-e2b"
        assert s.model_timeout == 60
        assert s.model_gpu_layers == 99
        assert s.model_context_size == 8192

    def test_custom_model_url(self):
        s = Settings(model_api_url="http://myhost:9999/v1/chat/completions")
        ms = ModelServer(s)
        assert ms._extract_host() == "myhost"
        assert ms._extract_port() == 9999
        assert ms.base_url == "http://myhost:9999"

    def test_extract_host_localhost(self):
        ms = ModelServer()
        assert ms._extract_host() == "localhost"

    def test_extract_port_default(self):
        ms = ModelServer()
        assert ms._extract_port() == 8092

    def test_base_url_strips_chat_path(self):
        ms = ModelServer()
        assert ms.base_url == "http://localhost:8092"


class TestModelServerLifecycle:
    """Test process lifecycle without actually starting anything."""

    def test_initial_state_not_running(self):
        ms = ModelServer()
        assert ms.is_running is False

    def test_stop_when_not_running_no_error(self):
        ms = ModelServer()
        ms.stop()  # Should not raise

    def test_repr_shows_stopped(self):
        ms = ModelServer()
        assert "stopped" in repr(ms)

    def test_repr_shows_url(self):
        ms = ModelServer()
        assert "localhost:8092" in repr(ms)


class TestModelServerHealthCheck:
    """Test health check logic."""

    def test_health_check_fails_when_not_running(self):
        ms = ModelServer()
        assert ms.health_check() is False

    @patch("audioshuttle.model_server.httpx.get")
    def test_health_check_returns_true_on_200(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        ms = ModelServer()
        assert ms.health_check() is True
        mock_get.assert_called_once()

    @patch("audioshuttle.model_server.httpx.get")
    def test_health_check_fails_on_500(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        ms = ModelServer()
        assert ms.health_check() is False

    @patch("audioshuttle.model_server.httpx.get")
    def test_health_check_fails_on_connection_error(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        ms = ModelServer()
        assert ms.health_check() is False


class TestModelServerChat:
    """Test chat completion requests."""

    def test_chat_returns_none_when_not_running(self):
        ms = ModelServer()
        result = ms.chat([{"role": "user", "content": "hello"}])
        assert result is None

    @patch("audioshuttle.model_server.httpx.post")
    def test_chat_parses_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": '{"tool": "play", "args": {}}'}}
            ]
        }
        mock_post.return_value = mock_response

        ms = ModelServer()
        result = ms.chat([{"role": "user", "content": "play"}])
        assert result == '{"tool": "play", "args": {}}'

    @patch("audioshuttle.model_server.httpx.post")
    def test_chat_returns_none_on_error(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")
        ms = ModelServer()
        result = ms.chat([{"role": "user", "content": "hello"}])
        assert result is None

    @patch("audioshuttle.model_server.httpx.post")
    def test_chat_sends_correct_payload(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_post.return_value = mock_response

        ms = ModelServer()
        ms.chat(
            [{"role": "system", "content": "You are helpful"}],
            temperature=0.1,
            max_tokens=256,
        )

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["temperature"] == 0.1
        assert payload["max_tokens"] == 256
        assert len(payload["messages"]) == 1
