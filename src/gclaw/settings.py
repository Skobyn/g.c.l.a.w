"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str = field(
        default_factory=lambda: os.environ["GCP_PROJECT_ID"]
    )
    gcp_location: str = field(
        default_factory=lambda: os.environ.get("GCP_LOCATION", "us-central1")
    )
    gemini_pro_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_PRO_MODEL", "gemini-2.5-flash"
        )
    )
    gemini_flash_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_FLASH_MODEL", "gemini-2.5-flash"
        )
    )
    gemini_live_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_LIVE_MODEL", "gemini-2.5-flash-preview-native-audio"
        )
    )
    firestore_database: str = field(
        default_factory=lambda: os.environ.get("FIRESTORE_DATABASE", "(default)")
    )
    config_dir: str = field(
        default_factory=lambda: os.environ.get(
            "GCLAW_CONFIG_DIR",
            os.path.join(os.path.dirname(__file__), "..", ".."),
        )
    )
    # Heartbeat settings
    heartbeat_session_id: str = field(
        default_factory=lambda: os.environ.get(
            "HEARTBEAT_SESSION_ID", "heartbeat"
        )
    )
    # Memory Bank settings
    memory_bank_reasoning_engine_id: str = field(
        default_factory=lambda: os.environ.get(
            "MEMORY_BANK_REASONING_ENGINE_ID", ""
        )
    )
    memory_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "MEMORY_ENABLED", "false"
        ).lower() == "true"
    )
    # Which MemoryService backend to use:
    #   "custom" — hand-rolled MemoryBankClient (default, preserves
    #              structured memory shape and full feature set).
    #   "native" — ADK's VertexAiMemoryBankService via NativeMemoryService
    #              (lean, delegates to blessed ADK wrapper; loses the
    #              summary/entities/importance structured shape because
    #              ADK's MemoryEntry doesn't expose those fields).
    memory_backend: str = field(
        default_factory=lambda: os.environ.get(
            "MEMORY_BACKEND", "custom"
        ).lower()
    )
    # Session settings
    session_compaction_threshold: int = field(
        default_factory=lambda: int(os.environ.get(
            "SESSION_COMPACTION_THRESHOLD", "50"
        ))
    )
    stale_session_threshold_seconds: int = field(
        default_factory=lambda: int(os.environ.get(
            "STALE_SESSION_THRESHOLD_SECONDS", "3600"
        ))
    )
    # Firebase Auth settings
    firebase_auth_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "FIREBASE_AUTH_ENABLED", "false"
        ).lower() == "true"
    )
    # Skills settings
    skills_dir: str = field(
        default_factory=lambda: os.environ.get(
            "GCLAW_SKILLS_DIR",
            os.path.join(
                os.environ.get(
                    "GCLAW_CONFIG_DIR",
                    os.path.join(os.path.dirname(__file__), "..", ".."),
                ),
                "skills",
            ),
        )
    )
    # Model routing settings
    model_routing_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "MODEL_ROUTING_ENABLED", "false"
        ).lower() == "true"
    )
    gemma_endpoint_id: str = field(
        default_factory=lambda: os.environ.get("GEMMA_ENDPOINT_ID", "")
    )
    nemotron_endpoint_id: str = field(
        default_factory=lambda: os.environ.get("NEMOTRON_ENDPOINT_ID", "")
    )
    nemotron_provider: str = field(
        default_factory=lambda: os.environ.get("NEMOTRON_PROVIDER", "vertex")
    )
    openrouter_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", "")
    )
    google_workspace_credentials_file: str = field(
        default_factory=lambda: os.environ.get(
            "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE", ""
        )
    )


def get_settings() -> Settings:
    return Settings()
