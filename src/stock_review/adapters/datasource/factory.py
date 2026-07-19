"""数据源工厂：按 config.yaml 启用清单构建实现。"""
from __future__ import annotations

from stock_review.core.config import get_settings
from stock_review.core.registry import source_registry
from stock_review.domain.ports import MarketDataSource


def ensure_sources() -> None:
    """导入各数据源模块以触发 @register（修掉原先"从不导入实现"导致 KeyError 的问题）。

    新增数据源时在此追加 import 即可；akshare 的 akshare 包是懒加载，模块导入不强制装包。
    """
    from stock_review.adapters.datasource import akshare_source, dxr_source, tdx_source  # noqa: F401


def build_source(name: str) -> MarketDataSource:
    ensure_sources()
    return source_registry.create(name)


def build_enabled_sources() -> list[MarketDataSource]:
    ensure_sources()
    s = get_settings()
    return [source_registry.create(n) for n in s.plugins.data_sources]


def first_source() -> MarketDataSource:
    return build_enabled_sources()[0]
