"""平台连接器包：统一入口，导入即注册（同 datasource 的 ensure_sources 思路）。

使用：
    from stock_review.adapters.platforms import get_connector, list_connectors
    c = get_connector("xueqiu")
    c.verify_login()          # 显式浏览器 probe：登录态能否带上
    res = c.smoke()           # 一次受控鉴权调用（不重试）
    res = c.get("https://...")  # 任意受控 GET（自动带登录态）
"""
from __future__ import annotations

from stock_review.adapters.platforms.base import (
    AuthCallResult,
    BasePlatformConnector,
    NeedLoginError,
)
from stock_review.core.registry import connector_registry

# 触发各平台模块 @register（修掉"从不导入实现"导致 KeyError 的问题）
from stock_review.adapters.platforms import dxr, jiuyan, kpl, taoguba, ths, xueqiu  # noqa: E402,F401


def get_connector(name: str) -> BasePlatformConnector:
    """按名称取一个连接器实例（未注册抛 KeyError，错误信息含可用清单）。"""
    return connector_registry.create(name)


def list_connectors() -> list[str]:
    """已注册的连接器名称清单。"""
    return connector_registry.names()


__all__ = [
    "BasePlatformConnector",
    "AuthCallResult",
    "NeedLoginError",
    "get_connector",
    "list_connectors",
]
