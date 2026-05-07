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
    model_api_url: str = "http://localhost:8092/v1/chat/completions"
    model_name: str = "gemma-4-e2b"

    # External chat interface (example AI)
    chat_api_url: str = "http://localhost:8090/v1/chat/completions"
    chat_model_name: str = "gemma-4-e4b"

    # Web UI server
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    # Memory vault (Obsidian-compatible)
    memory_vault_path: str = "~/.audioshuttle/memory"

    model_config = {"env_prefix": "AUDIOSHUTTLE_"}
