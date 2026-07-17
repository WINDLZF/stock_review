"""配置中心：环境变量(.env) + 插件开关(config.yaml)，彻底去除硬编码。

设计要点（贴合 Java 同学习惯的分层配置）：
- 标量/敏感项走 pydantic-settings（SR_ 前缀 + .env），密码/cookie 永不入库。
- 插件启用清单走 config.yaml，新增扩展只改 yaml，不动代码。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PluginConfig(BaseModel):
    """config.yaml 中的 plugins 段：声明启用哪些扩展。"""

    data_sources: list[str] = Field(default_factory=lambda: ["akshare"])
    dimensions: list[str] = Field(default_factory=lambda: ["technical", "breadth"])
    repository_mode: Literal["realtime_preferred", "offline_only"] = "offline_only"


class ThsConfig(BaseModel):
    """同花顺回写配置：基址/cookie 可被 .env 覆盖（敏感）。"""

    sync_mode: Literal["http", "file"] = "http"
    api_base: str = ""
    cookie: str = ""
    export_dir: str = "./.ths/exports"


def _load_yaml(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_plugins(path: Path) -> PluginConfig:
    cfg = _load_yaml(path)
    plugins = cfg.get("plugins", {}) or {}
    return PluginConfig(
        data_sources=plugins.get("data_sources", ["akshare"]),
        dimensions=plugins.get("dimensions", ["technical", "breadth"]),
        repository_mode=plugins.get("repository_mode", "offline_only"),
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "stock-review"
    log_level: str = "INFO"
    db_url: str = "sqlite:///./data/stock_review.db"
    config_path: Path = Path("config.yaml")

    # 同花顺回写（敏感项，优先读 .env 覆盖）
    ths_sync_mode: Literal["http", "file"] = "http"
    ths_api_base: str | None = None
    ths_cookie: str | None = None

    # 通达信离线行情目录（vipdoc），如 C:/new_tdx/vipdoc；可用 SR_TDX_VIPDOC_PATH 覆盖
    tdx_vipdoc_path: str = "C:/new_tdx/vipdoc"

    def __init__(self, **data):
        super().__init__(**data)
        self._plugins = load_plugins(self.config_path)

    @property
    def plugins(self) -> PluginConfig:
        return self._plugins

    @property
    def ths(self) -> ThsConfig:
        cfg = _load_yaml(self.config_path)
        ths = cfg.get("ths", {}) or {}
        return ThsConfig(
            sync_mode=self.ths_sync_mode,
            api_base=self.ths_api_base or ths.get("api_base", ""),
            cookie=self.ths_cookie or ths.get("cookie", ""),
            export_dir=ths.get("export_dir", "./.ths/exports"),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
