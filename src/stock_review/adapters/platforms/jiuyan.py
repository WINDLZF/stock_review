"""韭研公社连接器：必须登录（硬鉴权，绝不降级公开）。

鉴权方式：韭研公社是 SPA，登录态(token)在 localStorage 而非 cookie。
不登录**完全无法访问**（裸查会被按 IP 封），故本连接器是「硬鉴权」：
- 任何数据方法都先 ensure_logged_in()；
- 韭研是 SPA，localStorage token 新鲜度无法靠 cookie TTL 判断，故 is_logged_in()
  始终走浏览器 probe(verify=True)做权威判定，避免用过期 token 裸发被封；
- 无登录态直接抛 NeedLoginError，绝不降级到「公开」、绝不裸发。
登录态获取：stock-review login jiuyan（manual_only：弹窗登录后回车抓取完整 storage_state）。
真实数据接口：用 stock-review sniff jiuyan 抓包确认后，调 api_get(path)（仍受登录态闸门保护）。
合规边界：不循环重试；401/403 视为失效并提示重登，避免被封 IP。
"""
from __future__ import annotations

from stock_review.adapters.platforms.base import AuthCallResult, BasePlatformConnector
from stock_review.core.registry import connector_registry


@connector_registry.register("jiuyan")
class JiuyanConnector(BasePlatformConnector):
    platform = "jiuyan"
    display = "韭研公社"
    base_url = "https://www.jiuyangongshe.com"
    # localStorage 里的登录 token 候选 key（用于组装 Authorization 类头）
    token_keys = ("token", "Authorization", "authorization", "access_token")

    def is_logged_in(self, *, verify: bool = False) -> bool:
        # 韭研是 SPA：localStorage token 新鲜度无法靠 cookie TTL 判断，
        # 始终走浏览器 probe(verify=True)做权威判定，避免用过期 token 裸发被封。
        if not self._store.path.exists():
            return False
        return bool(self._mgr.verify(self.platform).get("ok"))

    def smoke(self) -> AuthCallResult:
        # 硬鉴权：无登录态直接抛 NeedLoginError（SPA 走浏览器 probe 验证 localStorage token）
        self.ensure_logged_in(verify=False)
        return self.get(f"{self.base_url}/", verify_login=False)

    def api_get(self, path: str) -> AuthCallResult:
        """调韭研任意需鉴权的 GET 接口（path 形如 '/api/xxx'，由 sniff 确认）。

        硬鉴权：必须已登录，未登录抛 NeedLoginError；401/403 视为失效、不重试。
        """
        self.ensure_logged_in(verify=False)
        if not path.startswith("/"):
            path = "/" + path
        return self.get(f"{self.base_url}{path}", verify_login=False)
