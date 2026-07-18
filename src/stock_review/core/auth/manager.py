"""登录管理器：统一入口，先试旧 cookie，失效才重登，存回本地。

日常只需一条命令刷新：stock-review login --platform ths
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from stock_review.core.auth.cookie_store import CookieStore, DEFAULT_SECRETS_DIR
from stock_review.core.auth.providers import get_provider


def to_cookie_header(cookies: dict[str, Any]) -> str:
    """把 cookie 字典拼成 HTTP 'Cookie' 头字符串。"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


class LoginManager:
    def __init__(self, secrets_dir: Path | str = DEFAULT_SECRETS_DIR):
        self.secrets_dir = Path(secrets_dir)

    def load(self, platform: str) -> dict[str, Any] | None:
        """仅读取已持久化的 cookie（不触发登录）。"""
        return CookieStore(platform, self.secrets_dir).load()

    def ensure(
        self, platform: str, *, interactive: bool = True, ttl: int = 0
    ) -> dict[str, Any] | None:
        """确保有可用 cookie：先试旧的，失效/缺失才触发登录并存回。"""
        store = CookieStore(platform, self.secrets_dir)
        if store.is_fresh(ttl):
            cookies = store.load()
            if cookies:
                return cookies
        provider = get_provider(platform)
        cookies = provider.login(interactive=interactive)
        if cookies:
            store.save(cookies, ttl=ttl)
        return cookies

    def cookie_header(self, platform: str, *, ttl: int = 0) -> str:
        """便捷：返回可直接塞进 HTTP 头的 cookie 字符串（无则空串）。"""
        cookies = self.ensure(platform, interactive=False, ttl=ttl)
        return to_cookie_header(cookies) if cookies else ""

    def forget(self, platform: str) -> None:
        CookieStore(platform, self.secrets_dir).clear()
