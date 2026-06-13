"""
ATLAS Configuration — Environment loading and settings management.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration (Google Gemini)."""

    api_key: str
    model: str = "gemini-2.5-flash"
    embedding_model: str = "models/text-embedding-004"
    temperature: float = 0.2
    max_output_tokens: int = 8192


@dataclass(frozen=True)
class ATLASSettings:
    """ATLAS pipeline settings."""

    max_retries: int = 3
    hitl_enabled: bool = True
    log_level: str = "INFO"

    # Coverage targets per layer
    unit_coverage_target: float = 85.0
    integration_coverage_target: float = 80.0
    functional_coverage_target: float = 75.0

    # Performance defaults
    perf_default_iterations: int = 1000
    perf_default_concurrency: int = 50

    # Performance budgets (p95 in ms)
    perf_budget_simple_ms: float = 5.0
    perf_budget_db_read_ms: float = 20.0
    perf_budget_db_write_ms: float = 30.0
    perf_budget_http_call_ms: float = 50.0
    perf_budget_data_transform_ms: float = 100.0


@dataclass
class ATLASConfig:
    """Root configuration container — aggregates all sub-configs."""

    llm: LLMConfig
    settings: ATLASSettings
    project_root: Path = field(default_factory=lambda: Path.cwd())

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> ATLASConfig:
        """
        Load configuration from environment variables.
        Optionally load from a .env file.
        """
        if env_path:
            load_dotenv(env_path)
        else:
            # Auto-discover .env in current directory or parent
            load_dotenv()

        google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is required. Get one from https://aistudio.google.com/apikey"
            )

        return cls(
            llm=LLMConfig(
                api_key=google_api_key,
                model=os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
                embedding_model=os.environ.get("EMBEDDING_MODEL", "models/text-embedding-004"),
            ),
            settings=ATLASSettings(
                max_retries=int(os.environ.get("ATLAS_MAX_RETRIES", "3")),
                hitl_enabled=os.environ.get("ATLAS_HITL_ENABLED", "true").lower() == "true",
                log_level=os.environ.get("ATLAS_LOG_LEVEL", "INFO"),
            ),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings."""
        warnings: list[str] = []
        return warnings
