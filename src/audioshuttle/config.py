"""AudioShuttle configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """AudioShuttle server configuration.

    All settings can be overridden via AUDIOSHUTTLE_ prefixed env vars.
    Example: AUDIOSHUTTLE_REAPER_PORT=9000
    """

    # Reaper OSC connection
    reaper_host: str = "127.0.0.1"
    reaper_port: int = 8000  # Reaper listens here for commands
    reaper_feedback_port: int = 9000  # Reaper sends feedback here

    # Embedded model (domain expert)
    model_api_url: str = "http://localhost:8093/v1/chat/completions"
    model_name: str = "gemma-4-e2b"
    model_enabled: bool = True
    model_binary: str = "/usr/bin/llama-server"
    model_path: str = "/home/korphaus/models/llm/gemma-4-e2b-it/gemma-4-E2B-it-UD-Q4_K_XL.gguf"
    model_gpu_device: int = 0  # ROCm device index (0 = RX 6950 XT)
    model_context_size: int = 8192
    model_threads: int = 4
    model_threads_batch: int = 4
    model_parallel: int = 2
    model_timeout: int = 60  # seconds for API requests
    model_gpu_layers: int = 99  # offload all layers to GPU

    # External chat interface (example AI)
    chat_api_url: str = "http://localhost:8090/v1/chat/completions"
    chat_model_name: str = "gemma-4-e4b"

    # Web UI server
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    # Memory vault (Obsidian-compatible)
    memory_vault_path: str = "~/.audioshuttle/memory"

    # DAW selection
    daw_type: str = "reaper"  # "reaper" or "ardour"

    # STT (speech-to-text) — optional, requires audioshuttle[stt]
    stt_model_size: str = "small"  # tiny/base/small/medium/large-v3
    stt_device: str = "cpu"  # cpu or cuda (default cpu — no GPU contention)
    stt_compute_type: str = "int8"  # int8 for CPU, float16 for GPU

    # Voice pipeline
    voice_hotkey: str = "alt+space"  # global hotkey combo
    voice_cleanup: bool = True  # E2B formatting pass on voice input
    voice_sample_rate: int = 16000  # recording sample rate (Whisper prefers 16kHz)

    # Web UI behavior
    auto_open_browser: bool = True  # auto-open browser on startup
    tray_enabled: bool = True  # show system tray icon
    toast_notifications: bool = True  # show system tray toasts for errors
    log_level: str = "warning"  # logging level for uvicorn

    model_config = {"env_prefix": "AUDIOSHUTTLE_"}
