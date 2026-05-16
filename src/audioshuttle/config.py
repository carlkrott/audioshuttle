"""AudioShuttle configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """AudioShuttle server configuration.

    All paths default to empty strings — configure via AUDIOSHUTTLE_MODEL_PATH,
    AUDIOSHUTTLE_MODEL_BINARY, AUDIOSHUTTLE_MODEL_MMPROJ env vars or CLI args.
    Model file must be provided before the model server can start.
    """

    # Reaper OSC connection
    reaper_host: str = "127.0.0.1"
    reaper_port: int = 8000  # Reaper listens here for commands
    reaper_feedback_port: int = 9000  # Reaper sends feedback here

    # Embedded model (domain expert — E4B + mmproj vision on dGPU)
    model_api_url: str = "http://localhost:8093/v1/chat/completions"
    model_name: str = "gemma-4-e4b"
    model_enabled: bool = True
    model_binary: str = ""
    model_path: str = ""
    model_mmproj: str = ""
    model_gpu_device: int = 0  # GPU device index for ROCm/CUDA
    model_context_size: int = 131072  # 128k context
    model_threads: int = 8
    model_threads_batch: int = 8
    model_parallel: int = 2
    model_timeout: int = 120  # seconds for API requests
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
