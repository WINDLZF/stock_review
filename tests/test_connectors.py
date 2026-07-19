"""连接器测试：核心保证「鉴权调用绝不裸发、不重复试错」。

这些测试不需要真实登录态/网络：
- 未登录时 ensure_logged_in() / request() 必须抛 NeedLoginError，证明不会发出空 cookie 请求。
- 连接器注册表必须包含 5 个可接入平台（韭研 IP 被封暂时搁置，连接器代码保留但不列入）。
"""
from __future__ import annotations

import pytest

from stock_review.adapters.platforms import list_connectors
from stock_review.adapters.platforms.base import NeedLoginError
from stock_review.core.auth.providers import is_accessible_platform
from stock_review.core.registry import connector_registry

PLATFORMS = ("ths", "kpl", "dxr", "taoguba", "xueqiu")


def _make_connector(name: str, secrets_dir):
    """用指定 secrets 目录实例化连接器（隔离真实 .secrets，保证测试确定性）。"""
    return connector_registry.get(name)(secrets_dir=secrets_dir)


def test_registry_has_five_accessible_platforms() -> None:
    names = set(list_connectors())
    assert {"ths", "kpl", "dxr", "taoguba", "xueqiu"} <= names
    # 韭研公社 IP 被封暂时搁置，is_accessible_platform 应返回 False
    assert is_accessible_platform("jiuyan") is False


def test_unlogged_connector_refuses_bare_request(tmp_path) -> None:
    """未登录时，受控请求必须抛 NeedLoginError，绝不裸发空 cookie。

    用空 tmp_path 作为 secrets 目录，避免受工作区已有真实登录态影响。
    """
    for name in PLATFORMS:
        c = _make_connector(name, tmp_path)
        with pytest.raises(NeedLoginError):
            c.ensure_logged_in()
        with pytest.raises(NeedLoginError):
            c.request("GET", "https://example.com/api", verify_login=True)


def test_auth_call_result_is_dataclass() -> None:
    from stock_review.adapters.platforms.base import AuthCallResult

    r = AuthCallResult(ok=False, status_code=401, problems=["expired"])
    assert r.ok is False
    assert r.status_code == 401
