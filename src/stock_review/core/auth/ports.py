"""登录提供者端口（Protocol 契约）。新增平台只需实现本协议并注册。"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from stock_review.core.auth.providers import LoginResult


@runtime_checkable
class LoginProvider(Protocol):
    """一个平台的登录提供者。

    负责拿到该平台的认证 cookie（name->value 字典）；具体怎么登录
    （playwright 实浏览器捕获 / 手动粘贴 / OAuth）由实现决定，上层不关心。
    """

    name: str
    login_url: str

    def login(self, *, interactive: bool = True, timeout: int = 600) -> LoginResult:
        """执行登录并返回 LoginResult（cookies + storage_state）。
        interactive=True 时引导用户完成登录；
        timeout 控制自动等待/人工确认的总时限（秒）。"""
        ...

    def verify(self, storage_state: dict[str, Any], *, timeout: int = 20) -> dict[str, Any]:
        """用已保存的 storage_state 验证登录态是否有效。
        返回 {ok, http_status, logged_in, reason, cookie_count, ls_keys}。"""
        ...
