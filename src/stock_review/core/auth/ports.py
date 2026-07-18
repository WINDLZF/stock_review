"""登录提供者端口（Protocol 契约）。新增平台只需实现本协议并注册。"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LoginProvider(Protocol):
    """一个平台的登录提供者。

    负责拿到该平台的认证 cookie（name->value 字典）；具体怎么登录
    （playwright 实浏览器捕获 / 手动粘贴 / OAuth）由实现决定，上层不关心。
    """

    name: str
    login_url: str

    def login(self, *, interactive: bool = True) -> dict[str, Any]:
        """执行登录并返回 cookies（name->value）。interactive=True 时引导用户完成登录。"""
        ...
