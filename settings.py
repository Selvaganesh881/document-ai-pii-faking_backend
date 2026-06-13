from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # from .env file
    DB_PATH: Path = Field(default=Path("data/pii_masker.db"))
    UPLOAD_DIR: Path = Field(default=Path("uploads"))
    OUTPUT_DIR: Path = Field(default=Path("outputs"))
    LOG_DIR: Path = Field(default=Path("logs"))
    
    # from config.yaml
    model_name: str = Field(default="roberta-base")
    model_path: Path = Field(default=Path("store_api/roberta-pii"))
    model_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    pdf_ocr_fallback_threshold: int = Field(default=50)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
        )
    
def load_config_yaml(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

@lru_cache(maxsize=1)
def get_settings(config_path: str = "config.yaml") -> Settings:
    data = load_config_yaml(config_path=Path(config_path))
    return Settings(**data)
    