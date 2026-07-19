"""平台连接器基类：登录态保证 + 不重复试错。

核心设计（回应「鉴权接口不要重复试错、保证登录态」）：
- 任何鉴权调用前必过 ensure_logged_in() 闸门：
  * 本地无新鲜登录态 → 直接抛 NeedLoginError，绝不裸发空 cookie（避免被按 IP 封）。
  * 默认用 CookieStore.is_fresh()（廉价、基于真实会话票 expires）判定，不发请求即可保证"带着有效凭据"。
- request() 只发一次请求；遇到 401/403 视为登录态失效，返回明确失败，**绝不循环重试**。
- 完整的「调用能否通过」自检走 LoginManager.verify()（恢复浏览器上下文 probe），
  那是显式动作（CLI: probe / connect --verify），不放在每次请求里（避免每次拉起浏览器）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stock_review.core.auth.cookie_store import DEFAULT_SECRETS_DIR, CookieStore
from stock_review.core.auth.manager import LoginManager


class NeedLoginError(RuntimeError):
    """本地无有效登录态。连接器抛出它来阻止裸发/重试（避免被封 IP）。"""

    def __init__(self, platform: str, reason: str = ""):
        self.platform = platform
        self.reason = reason
        super().__init__(
            f"[{platform}] 未登录或登录态已失效，需先重登：{reason}\n"
            f"  → 执行：stock-review login {platform}"
        )


@dataclass
class AuthCallResult:
    """一次鉴权调用的结构化结果。失败也照常返回（不抛、不重试）。"""

    ok: bool
    status_code: int | None = None
    data: Any = None
    problems: list[str] = field(default_factory=list)


class BasePlatformConnector:
    """带登录态保证的平台连接器。子类只需填 platform / base_url / token_keys / 平台特有头。"""

    platform: str = "base"
    display: str = "基础平台"
    base_url: str = ""
    token_keys: tuple[str, ...] = ()

    def __init__(self, secrets_dir: Any = DEFAULT_SECRETS_DIR):
        self._store = CookieStore(self.platform, secrets_dir)
        self._mgr = LoginManager(secrets_dir)

    # ── 登录态保证闸门 ──
    def is_logged_in(self, *, verify: bool = False) -> bool:
        """廉价判断：本地有未过期的登录态。verify=True 时额外跑浏览器 probe。"""
        if not self._store.path.exists() or not self._store.is_fresh():
            return False
        if not verify:
            return True
        return bool(self._mgr.verify(self.platform).get("ok"))

    def ensure_logged_in(self, *, verify: bool = False) -> None:
        """鉴权调用前的强制闸门。**不重试、不裸发**：无有效登录态直接抛 NeedLoginError。"""
        if not self.is_logged_in(verify=verify):
            raise NeedLoginError(self.platform, "本地无新鲜登录态")

    def verify_login(self) -> dict[str, Any]:
        """显式浏览器 probe：验证登录态能否真的带上（解决/自检「调用不通过」）。"""
        return self._mgr.verify(self.platform)

    # ── 鉴权头 ──
    def _platform_extra_headers(self) -> dict[str, str]:
        """平台特有必带头（如雪球需 x 头）。默认空，子类按需覆盖。"""
        return {}

    def auth_headers(self, *, token_keys: tuple[str, ...] = ()) -> dict[str, str]:
        """带完整鉴权的请求头（Cookie 权威源 + localStorage token + UA/Referer + 平台特有头）。"""
        keys = token_keys or self.token_keys
        h = self._mgr.auth_headers(self.platform, token_keys=keys)
        h.update(self._platform_extra_headers())
        return h

    # ── 受控请求 ──
    def request(
        self,
        method: str,
        url: str,
        *,
        verify_login: bool = True,
        token_keys: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> AuthCallResult:
        """带登录态保证的请求。**任何鉴权接口必经此门**：
        - verify_login=True 时先 ensure_logged_in()（无登录态直接抛错，绝不裸发/重试）。
        - 注入 auth_headers（Cookie 权威源 + localStorage token + UA/Referer + 平台特有头）。
        - 只发一次；401/403 视为登录态失效，返回明确失败（不重试，避免被封 IP）。
        """
        if verify_login:
            self.ensure_logged_in(verify=False)
        headers = dict(kwargs.pop("headers", {}))
        headers.update(self.auth_headers(token_keys=token_keys))
        try:
            import httpx  # noqa: PLC0415

            resp = httpx.request(method, url, headers=headers, timeout=30, **kwargs)
        except Exception as e:  # noqa: BLE001
            return AuthCallResult(ok=False, status_code=None, data=None, problems=[f"请求异常: {e}"])
        if resp.status_code in (401, 403):
            return AuthCallResult(
                ok=False,
                status_code=resp.status_code,
                data=None,
                problems=[
                    f"HTTP {resp.status_code}：登录态失效，请 `stock-review login "
                    f"{self.platform}` 后重试（不要循环重试，会被封 IP）"
                ],
            )
        return AuthCallResult(
            ok=resp.status_code < 400,
            status_code=resp.status_code,
            data=resp.text,
            problems=[] if resp.status_code < 400 else [f"HTTP {resp.status_code}"],
        )

    def get(self, url: str, **kw: Any) -> AuthCallResult:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> AuthCallResult:
        return self.request("POST", url, **kw)

    # ── 子类可覆盖：一次有代表性的鉴权调用（连通性自检）──
    def smoke_url(self) -> str:
        return self.base_url

    def smoke(self) -> AuthCallResult:
        """默认冒烟：一次受控 GET，验证「带着登录态能调通」。"""
        return self.get(self.smoke_url(), verify_login=True)
