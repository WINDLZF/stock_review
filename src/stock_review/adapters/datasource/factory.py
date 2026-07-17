"""数据源工厂：按 config.yaml 启用清单构建实现。"""
from __future__ import annotations

from stock_review.core.config import get_settings
from stock_review.core.registry import source_registry
from stock_review.domain.ports import MarketDataSource


def build_source(name: str) -> MarketDataSource:
    return source_registry.create(name)


def build_enabled_sources() -> list[MarketDataSource]:
    s = get_settings()
    return [build_source(n) for n in s.plugins.data_sources]


def first_source() -> MarketDataSource:
    return build_enabled_sources()[0]
