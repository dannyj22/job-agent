"""Configuration loading from YAML plus environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_CONFIG: dict[str, Any] = {
    "database": {"path": "data/jobs.db"},
    "logging": {"level": "INFO", "file": "logs/jobagent.log"},
    "filters": {
        "min_score": 4,
        "exclude_keywords": [],
        "include_keywords": {"core": [], "adjacent": [], "general": []},
        "weights": {"core": 4, "adjacent": 2, "general": 1},
        "title_bonus": 3,
        "locations": [],
    },
    "notify": {"discord": {"max_jobs_per_run": 20, "embeds_per_message": 10}},
    "sources": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class Config:
    base_dir: Path
    data: dict[str, Any] = field(default_factory=dict)
    discord_webhook: str = ""
    discord_mention: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    indeed_proxy: str = ""

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        base_dir = Path(__file__).resolve().parent.parent
        load_dotenv(base_dir / ".env")

        if config_path is None:
            config_path = base_dir / "config.yaml"
        config_path = Path(config_path)

        raw: dict[str, Any] = {}
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
        data = _deep_merge(DEFAULT_CONFIG, raw)

        return cls(
            base_dir=base_dir,
            data=data,
            discord_webhook=os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
            discord_mention=os.getenv(
                "DISCORD_MENTION_USER_ID",
                str(data.get("notify", {}).get("discord", {}).get("mention", "")),
            ).strip(),
            adzuna_app_id=os.getenv("ADZUNA_APP_ID", "").strip(),
            adzuna_app_key=os.getenv("ADZUNA_APP_KEY", "").strip(),
            indeed_proxy=os.getenv("INDEED_PROXY", "").strip(),
        )

    # ---- convenience accessors -------------------------------------------
    @property
    def filters(self) -> dict[str, Any]:
        return self.data.get("filters", {})

    @property
    def sources(self) -> dict[str, Any]:
        return self.data.get("sources", {})

    @property
    def discord(self) -> dict[str, Any]:
        return self.data.get("notify", {}).get("discord", {})

    def source_config(self, name: str) -> dict[str, Any]:
        return self.sources.get(name, {}) or {}

    def source_enabled(self, name: str) -> bool:
        return bool(self.source_config(name).get("enabled", False))

    def path(self, relative: str) -> Path:
        path = Path(relative)
        if not path.is_absolute():
            path = self.base_dir / path
        return path

    @property
    def db_path(self) -> Path:
        return self.path(self.data.get("database", {}).get("path", "data/jobs.db"))

    @property
    def log_path(self) -> Path:
        return self.path(self.data.get("logging", {}).get("file", "logs/jobagent.log"))

    @property
    def log_level(self) -> str:
        return str(self.data.get("logging", {}).get("level", "INFO")).upper()
