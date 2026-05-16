"""Embedded model server lifecycle management.

Supports both synchronous and streaming chat, with multimodal content
(images, audio as spectrogram images) for Gemma 4 E2B.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Any, Generator

import httpx

from audioshuttle.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """A single event from a streaming chat response."""

    type: str  # "thinking" | "content" | "done"
    text: str = ""
    source: str = "e2b"  # which model/source produced this
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "text": self.text,
            "source": self.source,
            "ts": self.timestamp,
        }


class ModelServer:
    """Manages the E2B llama-server process on GPU.

    Handles start/stop lifecycle, health checks, and API communication.
    The server runs llama-server as a subprocess with ROCm GPU offloading.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._process: subprocess.Popen | None = None
        self._base_url = self._settings.model_api_url.replace(
            "/v1/chat/completions", ""
        )
        self._external_last_check: float = 0.0
        self._external_available: bool = False
        self._external_mode: bool = False

    @property
    def is_running(self) -> bool:
        """Check if the model server is available.

        If we spawned a subprocess, check if it's alive.
        If in external mode (connect to pre-existing server), use cached health check.
        """
        if self._process is not None:
            return self._process.poll() is None
        # External mode — cached health check (probe every 10s)
        if self._external_mode:
            now = time.time()
            if now - self._external_last_check > 10.0:
                self._external_available = self.health_check()
                self._external_last_check = now
            return self._external_available
        # No subprocess, not external mode → not running
        return False

    def enable_external(self) -> None:
        """Enable external mode — probe for a pre-existing model server."""
        self._external_mode = True
        self._external_available = self.health_check()
        self._external_last_check = time.time()

    @property
    def base_url(self) -> str:
        """Base URL for the model API."""
        return self._base_url

    def start(self, wait: bool = True, timeout: float = 60.0) -> bool:
        """Start the llama-server process with ROCm GPU offloading.

        Args:
            wait: If True, block until health check passes.
            timeout: Max seconds to wait for server ready.

        Returns:
            True if server started (and is healthy if wait=True).
        """
        if self.is_running:
            logger.warning(
                "Model server already running (pid %d)", self._process.pid
            )
            return True

        # Before attempting to start/cleanup, probe for a pre-existing external
        # server on the same port — if one is already responding to /health, use it.
        if self.health_check():
            logger.info(
                "External model server already running at %s — using it",
                self.base_url,
            )
            self.enable_external()
            if wait:
                # Wait for it to be fully ready
                deadline = time.time() + timeout
                while not self.is_running and time.time() < deadline:
                    time.sleep(1.0)
            return True

        # No existing server found — proceed with normal startup/cleanup cycle
        self._cleanup_orphaned_process()

        s = self._settings
        env = os.environ.copy()
        env["HIP_VISIBLE_DEVICES"] = str(s.model_gpu_device)

        cmd = [
            s.model_binary,
            "-m", s.model_path,
            "--host", self._extract_host(),
            "--port", str(self._extract_port()),
            "-ngl", str(s.model_gpu_layers),
            "-t", str(s.model_threads),
            "-tb", str(s.model_threads_batch),
            "--parallel", str(s.model_parallel),
            "-c", str(s.model_context_size),
            "-ctk", "q4_0",
            "-ctv", "q4_0",
            "-fa", "auto",
            "--jinja",
            "--no-cont-batching",
            "--reasoning", "off",
            "--timeout", str(s.model_timeout),
            "--mlock",
        ]

        # Add mmproj for vision if configured
        mmproj = getattr(s, "model_mmproj", None)
        if mmproj:
            cmd.extend(["--mmproj", mmproj])

        logger.info("Starting model server: %s ...", " ".join(cmd[:6]))

        try:
            self._process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            logger.info("Model server started (pid %d)", self._process.pid)
        except FileNotFoundError:
            logger.error("llama-server binary not found: %s", s.model_binary)
            return False
        except Exception as e:
            logger.error("Failed to start model server: %s", e)
            return False

        if not wait:
            return True

        return self.wait_ready(timeout=timeout)

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the model server process gracefully.

        Sends SIGTERM, waits for timeout, then SIGKILL if needed.
        """
        if self._process is None:
            return

        pid = self._process.pid
        logger.info("Stopping model server (pid %d)...", pid)

        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=timeout)
                logger.info("Model server stopped gracefully (pid %d)", pid)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Model server didn't stop in %.1fs, killing", timeout
                )
                self._process.kill()
                self._process.wait(timeout=5.0)
                logger.info("Model server killed (pid %d)", pid)
        except Exception as e:
            logger.error("Error stopping model server: %s", e)
        finally:
            self._process = None

    def wait_ready(
        self, timeout: float = 60.0, interval: float = 2.0
    ) -> bool:
        """Wait until the model server responds to health checks.

        Args:
            timeout: Max seconds to wait.
            interval: Seconds between checks.

        Returns:
            True if server is ready, False if timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running:
                rc = self._process.returncode if self._process else -1
                logger.error("Model server crashed (exit code %d)", rc)
                return False

            if self.health_check():
                logger.info("Model server ready at %s", self._base_url)
                return True

            time.sleep(min(interval, deadline - time.time()))

        logger.error("Model server not ready after %.1fs", timeout)
        return False

    def health_check(self) -> bool:
        """Check if the model server API is responding."""
        try:
            resp = httpx.get(f"{self._base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str | None:
        """Send a chat completion request to the model server.

        Args:
            messages: OpenAI-format messages list.
            temperature: Sampling temperature.
            max_tokens: Max tokens in response (default 1024 — E2B thinking
                mode uses tokens for reasoning, so we need headroom).

        Returns:
            Assistant message content, or None on error.
        """
        try:
            resp = httpx.post(
                f"{self._base_url}/v1/chat/completions",
                json={
                    "model": self._settings.model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=float(self._settings.model_timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content", "")
            # E2B thinking mode: content may be empty while reasoning is present
            if not content:
                reasoning = message.get("reasoning_content", "")
                if reasoning:
                    content = reasoning
            return content or None
        except Exception as e:
            logger.error("Model chat request failed: %s", e)
            return None

    # ── Streaming Chat ──────────────────────────────────────────

    def chat_streaming(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Generator[StreamEvent, None, None]:
        """Stream a chat completion, yielding thinking/content/done events.

        Parses SSE chunks from llama-server's streaming API.
        E2B emits `delta.reasoning_content` for thinking and `delta.content`
        for the actual response.

        Yields:
            StreamEvent objects with type "thinking", "content", or "done".
        """
        try:
            payload = {
                "model": self._settings.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }

            with httpx.stream(
                "POST",
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                timeout=float(self._settings.model_timeout),
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: " prefix
                    if data_str.strip() == "[DONE]":
                        yield StreamEvent(type="done", source="e2b")
                        return

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason")

                    # Thinking tokens
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        yield StreamEvent(
                            type="thinking", text=reasoning, source="e2b"
                        )

                    # Content tokens
                    content = delta.get("content", "")
                    if content:
                        yield StreamEvent(
                            type="content", text=content, source="e2b"
                        )

                    # Finish
                    if finish_reason:
                        yield StreamEvent(
                            type="done", text=finish_reason, source="e2b"
                        )
                        return

        except httpx.HTTPStatusError as e:
            logger.error("Streaming chat HTTP error: %s", e)
            yield StreamEvent(
                type="done", text=f"error: HTTP {e.response.status_code}", source="e2b"
            )
        except Exception as e:
            logger.error("Streaming chat failed: %s", e)
            yield StreamEvent(
                type="done", text=f"error: {e}", source="e2b"
            )

    # ── Multimodal Chat ────────────────────────────────────────

    def chat_multimodal(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str | None:
        """Send a multimodal chat completion (text + image/audio content).

        Args:
            messages: OpenAI-format messages with multipart content.
                Each message content can be a string or list of content parts:
                [
                    {"type": "text", "text": "Describe this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
                ]
            temperature: Sampling temperature.
            max_tokens: Max tokens in response.

        Returns:
            Assistant message content, or None on error.
        """
        try:
            resp = httpx.post(
                f"{self._base_url}/v1/chat/completions",
                json={
                    "model": self._settings.model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=float(self._settings.model_timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content", "")
            if not content:
                reasoning = message.get("reasoning_content", "")
                if reasoning:
                    content = reasoning
            return content or None
        except Exception as e:
            logger.error("Multimodal chat request failed: %s", e)
            return None

    def chat_multimodal_streaming(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Generator[StreamEvent, None, None]:
        """Stream a multimodal chat completion, yielding events.

        Same as chat_streaming but accepts multipart message content.
        """
        yield from self.chat_streaming(messages, temperature, max_tokens)

    # ── Content Helpers ────────────────────────────────────────

    @staticmethod
    def image_from_file(path: str) -> dict:
        """Build an image_url content part from a file path.

        Reads the file, base64-encodes it, and returns an OpenAI-format
        image_url content part suitable for chat_multimodal().
        """
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        ext = os.path.splitext(path)[1].lower()
        mime = mime_map.get(ext, "image/png")

        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")

        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }

    @staticmethod
    def image_from_bytes(data: bytes, mime: str = "image/png") -> dict:
        """Build an image_url content part from raw bytes."""
        b64 = base64.b64encode(data).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }

    @staticmethod
    def text_part(text: str) -> dict:
        """Build a text content part."""
        return {"type": "text", "text": text}

    # ── Internals ──────────────────────────────────────────────

    def _extract_host(self) -> str:
        """Extract host from model_api_url."""
        parsed = urlparse(self._settings.model_api_url)
        return parsed.hostname or "127.0.0.1"

    def _extract_port(self) -> int:
        """Extract port from model_api_url."""
        parsed = urlparse(self._settings.model_api_url)
        return parsed.port or 8092

    def _cleanup_orphaned_process(self) -> None:
        """Kill any orphaned llama-server process on the model port.

        When AudioShuttle is killed without clean shutdown, the llama-server
        subprocess can survive. A new start would fail to bind the port.
        This finds and kills any existing process before starting a fresh one.
        """
        port = self._extract_port()
        try:
            import subprocess
            result = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split()
                for pid_str in pids:
                    try:
                        pid = int(pid_str.strip())
                        if pid != os.getpid():
                            logger.info(
                                "Killing orphaned process on port %d (pid %d)",
                                port, pid,
                            )
                            os.kill(pid, 9)
                            time.sleep(0.5)
                    except (ValueError, ProcessLookupError):
                        pass
        except Exception as e:
            logger.debug("Could not check for orphaned processes: %s", e)

    def __repr__(self) -> str:
        status = "running" if self.is_running else "stopped"
        pid = self._process.pid if self._process else None
        return f"ModelServer(url={self._base_url}, status={status}, pid={pid})"
