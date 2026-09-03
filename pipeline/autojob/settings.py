"""Configuration: secrets from .env, everything else from config/search.yaml.

Nothing personal lives in code. The candidate profile and LaTeX templates live in
``profile/`` (git-ignored); search behaviour lives in ``config/search.yaml`` (tracked).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _path(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name)
    return Path(raw).expanduser().resolve() if raw else default


DATA_DIR = _path("AUTOJOB_DATA_DIR", ROOT / "data")
OUTPUT_DIR = _path("AUTOJOB_OUTPUT_DIR", ROOT / "output")
PROFILE_DIR = _path("AUTOJOB_PROFILE_DIR", ROOT / "profile")
CONFIG_PATH = _path("AUTOJOB_CONFIG", ROOT / "config" / "search.yaml")
PROMPTS_DIR = ROOT / "prompts"

DB_PATH = DATA_DIR / "autojob.db"
LOG_PATH = DATA_DIR / "autojob.log"
LOCK_PATH = DATA_DIR / "autojob.lock"


@dataclass
class Secrets:
    llm_api_key: str = ""
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    serper_api_key: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @classmethod
    def from_env(cls) -> Secrets:
        return cls(
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_base_url=os.environ.get("LLM_BASE_URL", cls.llm_base_url),
            serper_api_key=os.environ.get("SERPER_API_KEY", ""),
            adzuna_app_id=os.environ.get("ADZUNA_APP_ID", ""),
            adzuna_app_key=os.environ.get("ADZUNA_APP_KEY", ""),
            jooble_api_key=os.environ.get("JOOBLE_API_KEY", ""),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        )


@dataclass
class Settings:
    raw: dict[str, Any]
    secrets: Secrets = field(default_factory=Secrets.from_env)

    # --- generic accessors -------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def source(self, name: str) -> dict[str, Any]:
        cfg = self.get(f"sources.{name}", {}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def source_enabled(self, name: str) -> bool:
        return bool(self.source(name).get("enabled", False))

    @property
    def queries(self) -> list[str]:
        return list(self.get("queries", []) or [])

    def source_queries(self, name: str) -> list[str]:
        """Per-source query override, else the global list."""
        override = self.source(name).get("queries")
        return list(override) if override else self.queries

    # --- profile files -------------------------------------------------------
    @property
    def candidate_profile_path(self) -> Path:
        return PROFILE_DIR / "candidate.md"

    @property
    def resume_template_path(self) -> Path:
        return PROFILE_DIR / "resume.tex"

    @property
    def cover_letter_template_path(self) -> Path:
        return PROFILE_DIR / "cover_letter.tex"

    def candidate_profile(self) -> str:
        return self.candidate_profile_path.read_text(encoding="utf-8")

    def prompt(self, name: str) -> str:
        return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_settings(path: Path | None = None) -> Settings:
    cfg_path = path or CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Settings(raw=raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
