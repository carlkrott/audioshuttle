"""Embedded model server lifecycle management."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from urllib.parse import urlparse
from typing import Any

import httpx

from audioshuttle.config import Settings

logger = logging.getLogger(__name__)


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

    @property
    def is_running(self) -> bool:
        """Check if the model server process is alive."""
        return self._process is not None and self._process.poll() is None

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

        # Kill any orphaned process on the model port before starting.
        # This prevents "address already in use" errors from previous runs.
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
            "--jinja",
            "--timeout", str(s.model_timeout),
            "--mlock",
            "--no-mmap",
        ]

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
        max_tokens: int = 512,
    ) -> str | None:
        """Send a chat completion request to the model server.

        Args:
            messages: OpenAI-format messages list.
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
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("Model chat request failed: %s", e)
            return None

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
