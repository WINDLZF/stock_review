"""雪球连接器：登录态保证 + 受控请求。

鉴权方式：cookie（xq_a_token 等）+ **强制 x 头**。雪球 API 要求请求带一个特殊头
`x`，其值取自登录 cookie `xq_r_token`；缺失该头会被 403。_platform_extra_headers()
自动从已保存登录态里取该值，无需手动填。
已知稳定接口（参考雪球公开 API 形态 stock.xueqiu.com）：
- 行情快照 /v5/stock/quote.json?code=CODE
- K线       /stock/forchart/price.json?symbol=CODE&period=1DAY
- 用户自选  需登录态；个股详情 /v5/stock/finance.json?symbol=CODE
"""
from __future__ import annotations

from stock_review.adapters.platforms.base import AuthCallResult, BasePlatformConnector
from stock_review.core.registry import connector_registry


@connector_registry.register("xueqiu")
class XueqiuConnector(BasePlatformConnector):
    platform = "xueqiu"
    display = "雪球"
    base_url = "https://stock.xueqiu.com"
    token_keys = ()

    def _platform_extra_headers(self) -> dict[str, str]:
        # 雪球强制 x 头 = 登录 cookie xq_r_token 的值；缺失即 403
        ck = self._store.canonical_cookie()
        for part in ck.split("; "):
            if part.startswith("xq_r_token="):
                return {"x": part.split("=", 1)[1]}
        return {}

    def quote(self, code: str) -> AuthCallResult:
        """个股行情快照（已知稳定接口，需登录态）。code 形如 SH600000 / BABA。"""
        self.ensure_logged_in(verify=True)
        return self.get(f"{self.base_url}/v5/stock/quote.json?code={code}")

    def kline(self, code: str, period: str = "1DAY") -> AuthCallResult:
        """K 线（需登录态）。period: 1DAY/1MONTH/... 参考雪球 forchart 接口。"""
        self.ensure_logged_in(verify=True)
        return self.get(
            f"{self.base_url}/stock/forchart/price.json?symbol={code}&period={period}"
        )

    def smoke(self) -> AuthCallResult:
        return self.quote("SH600000")
