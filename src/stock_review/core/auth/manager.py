"""登录管理器：统一入口，先试旧 cookie，失效才重登，存回本地。

日常只需一条命令刷新：stock-review login --platform ths
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import time

from stock_review.core.auth.cookie_store import CookieStore, DEFAULT_SECRETS_DIR
from stock_review.core.auth.providers import get_provider, list_platforms as _list_platforms


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
        self, platform: str, *, interactive: bool = True, ttl: int = 0,
        timeout: int = 600,
    ) -> dict[str, Any] | None:
        """确保有可用 cookie：先试旧的，失效/缺失才触发登录并存回。"""
        store = CookieStore(platform, self.secrets_dir)
        if store.is_fresh(ttl):
            cookies = store.load()
            if cookies:
                return cookies
        provider = get_provider(platform)
        result = provider.login(interactive=interactive, timeout=timeout)
        cookies = result.cookies
        # 韭研等 SPA 登录态在 localStorage：即便 cookie 为空，只要有 storage_state 也应落盘
        if cookies or result.storage_state:
            # 优先用会话票自带 expires 判新鲜度；传入 ttl 仅会话级兜底
            store.save(
                cookies,
                ttl=ttl,
                expires_map=result.expires_map,
                success_cookies=provider.success_cookies,
                storage_state=result.storage_state,
            )
        return cookies

    def cookie_header(self, platform: str, *, ttl: int = 0) -> str:
        """便捷：返回可直接塞进 HTTP 头的 cookie 字符串（无则空串）。

        从权威源（storage_state.cookies）重建，避免读到易为空的顶层字段。
        """
        store = CookieStore(platform, self.secrets_dir)
        header = store.canonical_cookie()
        if header:
            return header
        # 无本地登录态则触发/读取一次，再从权威源重建
        self.ensure(platform, interactive=False, ttl=ttl)
        return store.canonical_cookie()

    def storage_state(self, platform: str) -> dict[str, Any] | None:
        """返回完整 storage_state（含 localStorage），供 playwright 恢复上下文。"""
        return CookieStore(platform, self.secrets_dir).load_storage_state()

    def local_storage(self, platform: str, origin_substr: str = "") -> dict[str, str]:
        """返回该平台 localStorage 键值（SPA token 在此，如韭研）。"""
        return CookieStore(platform, self.secrets_dir).local_storage(origin_substr)

    def token(self, platform: str, *keys: str) -> str | None:
        """取该平台 localStorage 里的登录 token（按候选 key 顺序；缺省宽松匹配含 token 的 key）。"""
        return CookieStore(platform, self.secrets_dir).token(*keys)

    def auth_headers(self, platform: str, *, token_keys: tuple[str, ...] = ()) -> dict[str, str]:
        """组装带完整鉴权的请求头：Cookie（权威源）+ token（localStorage）+ 正规 UA/Referer。

        这是"调用能通过"的关键：韭研等平台裸发（不带 cookie/token）会被按 IP 封。
        """
        from stock_review.core.auth.providers import get_provider  # noqa: PLC0415

        store = CookieStore(platform, self.secrets_dir)
        headers: dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        }
        cookie = store.canonical_cookie()
        if cookie:
            headers["Cookie"] = cookie
        try:
            headers["Referer"] = get_provider(platform).login_url
        except Exception:  # noqa: BLE001
            pass
        tok = store.token(*token_keys)
        if tok:
            headers["token"] = tok
        return headers

    def verify(self, platform: str) -> dict[str, Any]:
        """验证某平台登录态是否真的能带上（解决/自检「调用不通过」。

        用已保存的 storage_state 恢复浏览器上下文访问平台，返回诊断字典。
        兼容旧登录格式：若无 storage_state 但有 cookie，用 cookie 重建最小
        storage_state（cookies 数组），使旧登录态也能 probe。
        """
        from stock_review.core.auth.providers import get_provider  # noqa: PLC0415

        store = CookieStore(platform, self.secrets_dir)
        state = store.load_storage_state()
        if not state:
            cookies = store.load() or {}
            if cookies:
                # 旧格式兼容：用平台登录页 origin 作为 cookie 的 url，
                # 让 playwright 能接受（cookie 需 url 或 domain/path）
                from urllib.parse import urlparse  # noqa: PLC0415

                origin = ""
                try:
                    origin = urlparse(get_provider(platform).login_url).netloc
                except Exception:  # noqa: BLE001
                    origin = ""
                state = {
                    "cookies": [
                        {"name": k, "value": v, "domain": origin, "path": "/",
                         "expires": -1, "httpOnly": False, "secure": False}
                        for k, v in cookies.items()
                    ],
                    "origins": [],
                }
        if not state:
            return {"ok": False, "reason": "本地无登录态（cookie/storage_state 皆空），请先登录",
                    "http_status": None, "logged_in": False,
                    "cookie_count": 0, "ls_keys": []}
        return get_provider(platform).verify(state)

    def forget(self, platform: str) -> None:
        CookieStore(platform, self.secrets_dir).clear()

    def list_platforms(self) -> list[dict[str, Any]]:
        """返回已注册平台元数据（名称/展示名/登录页/是否需 token）。"""
        return _list_platforms()

    def status(self) -> list[dict[str, Any]]:
        """汇总每个平台的持久化状态：是否新鲜、剩余天数、cookie 数、保存时间。"""
        out: list[dict[str, Any]] = []
        now = time.time()
        for meta in _list_platforms():
            name = meta["name"]
            store = CookieStore(name, self.secrets_dir)
            row = dict(meta)
            if not store.path.exists():
                row.update(saved=False, fresh=False, days_left=None,
                           cookie_count=0, saved_at=None)
                out.append(row)
                continue
            data = {}
            try:
                data = json.loads(store.path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = {}
            cookies = data.get("cookies") or {}
            ss = data.get("storage_state") or {}
            ls_count = sum(len(o.get("localStorage", [])) for o in ss.get("origins", []))
            ttl = data.get("ttl", 0) or 0
            saved_at = data.get("saved_at")
            fresh = store.is_fresh()
            days_left = None
            if saved_at and ttl:
                days_left = max(0, int((saved_at + ttl - now) // 86400))
            row.update(
                saved=True,
                fresh=fresh,
                days_left=days_left,
                ttl=ttl,
                cookie_count=len(cookies),
                ls_count=ls_count,
                saved_at=saved_at,
            )
            out.append(row)
        return out
