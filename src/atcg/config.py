"""
ATCG Configuration — Environment loading and settings management.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class NeonConfig:
    """Neon database configuration."""
    database_url: str
    branch_url: str | None = None

    @property
    def is_branch_available(self) -> bool:
        return bool(self.branch_url)


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration (Google Gemini)."""
    api_key: str
    model: str = "gemini-2.5-flash"
    embedding_model: str = "models/text-embedding-004"
    temperature: float = 0.2
    max_output_tokens: int = 8192


@dataclass(frozen=True)
class ATCGSettings:
    """ATCG pipeline settings."""
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
class ATCGConfig:
    """Root configuration container — aggregates all sub-configs."""
    neon: NeonConfig
    llm: LLMConfig
    settings: ATCGSettings
    project_root: Path = field(default_factory=lambda: Path.cwd())

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> ATCGConfig:
        """
        Load configuration from environment variables.
        Optionally load from a .env file.
        """
        if env_path:
            load_dotenv(env_path)
        else:
            # Auto-discover .env in current directory or parent
            load_dotenv()

        neon_url = os.environ.get("NEON_DATABASE_URL", "")
        if not neon_url:
            raise ValueError(
                "NEON_DATABASE_URL is required. "
                "Copy .env.example to .env and configure your Neon connection string."
            )

        google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is required. "
                "Get one from https://aistudio.google.com/apikey"
            )

        return cls(
            neon=NeonConfig(
                database_url=neon_url,
                branch_url=os.environ.get("NEON_BRANCH_URL") or None,
            ),
            llm=LLMConfig(
                api_key=google_api_key,
                model=os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
                embedding_model=os.environ.get("EMBEDDING_MODEL", "models/text-embedding-004"),
            ),
            settings=ATCGSettings(
                max_retries=int(os.environ.get("ATCG_MAX_RETRIES", "3")),
                hitl_enabled=os.environ.get("ATCG_HITL_ENABLED", "true").lower() == "true",
                log_level=os.environ.get("ATCG_LOG_LEVEL", "INFO"),
            ),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings."""
        warnings = []
        if not self.neon.is_branch_available:
            warnings.append(
                "NEON_BRANCH_URL not set — integration tests will use pg-mem mock fallback"
            )
        return warnings
