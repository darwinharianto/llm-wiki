from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VAULT_DIR = Path(os.environ.get("LLM_WIKI_VAULT_DIR", BASE_DIR / "vault"))


class RuntimeSettings(BaseModel):
    """Runtime configuration for LLM providers, similarity merge threshold, and auto-maintenance."""

    provider: Literal["local_smart", "gemini", "openai", "ollama"] = Field(
        default="local_smart"
    )
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.5-flash-lite")
    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_model: str = Field(default="gpt-4o-mini")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434")
    ollama_model: str = Field(default="llama3.2")
    similarity_threshold: float = Field(default=0.35, ge=0.1, le=0.95)
    near_duplicate_threshold: float = Field(default=0.55, ge=0.2, le=0.95)
    auto_maintain_after_ingest: bool = Field(default=True)
    periodic_maintain_seconds: int = Field(default=300, ge=0)

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        explicit_provider = os.environ.get("LLM_WIKI_PROVIDER", "")

        if explicit_provider in {"local_smart", "gemini", "openai", "ollama"}:
            provider: Literal["local_smart", "gemini", "openai", "ollama"] = explicit_provider  # type: ignore[assignment]
        elif gemini_key:
            provider = "gemini"
        elif openai_key:
            provider = "openai"
        else:
            provider = "local_smart"

        return cls(
            provider=provider,
            gemini_api_key=gemini_key,
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            openai_api_key=openai_key,
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            similarity_threshold=float(os.environ.get("LLM_WIKI_SIMILARITY_THRESHOLD", "0.35")),
        )

