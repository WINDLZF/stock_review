"""同花顺连接器：必须登录（硬鉴权，绝不降级公开）。

鉴权方式：网页 cookie（user/userid/ticket 会话票；同花顺为网页端，cookie 鉴权有效）。
参考：
- 现有 `adapters/ths/__init__.py` 的 ThsHttpSync（自定义板块回写 /custom-block，已调通）
- github.com/panghu11033/thsdk、github.com/limitget/THS（同花顺数据/交易协议）
- 官方量化接口 quantapi.10jqka.com.cn

硬鉴权：所有数据接口都走 verify_login=True（ensure_logged_in 闸门），无登录态直接抛
NeedLoginError，绝不裸发/降级——同花顺裸查会被按 IP 封。
数据调用：
- 回写类（写）：自定义板块 /custom-block（需 SR_THS_API_BASE）
- 行情类（读）：网页端 dq.10jqka.com.cn（行情快照，cookie 鉴权；真实 path 待 sniff 确认）
"""
from __future__ import annotations

from stock_review.adapters.platforms.base import AuthCallResult, BasePlatformConnector
from stock_review.core.config import get_settings
from stock_review.core.registry import connector_registry


@connector_registry.register("ths")
class ThsConnector(BasePlatformConnector):
    platform = "ths"
    display = "同花顺"
    base_url = "https://dq.10jqka.com.cn"
    token_keys = ()

    def smoke(self) -> AuthCallResult:
        # 硬鉴权：先浏览器 probe 验证 cookie 能否带上（无登录态直接抛 NeedLoginError）
        self.ensure_logged_in(verify=True)
        s = get_settings().ths
        if not s.api_base:
            return AuthCallResult(
                ok=False,
                status_code=None,
                data=None,
                problems=[
                    "登录态已验证通过，但未配置 SR_THS_API_BASE（同花顺回写 API 基址），"
                    "无法发起数据/回写调用；请在 .env 配置后重试"
                ],
            )
        # 已知接口：自定义板块列表（需带登录 cookie）
        return self.get(f"{s.api_base.rstrip('/')}/custom-block", verify_login=True)

    def custom_blocks(self) -> AuthCallResult:
        """读取远程自定义板块列表（回写闭环的读侧，配合 ThsHttpSync；已验证接口）。"""
        self.ensure_logged_in(verify=False)
        s = get_settings().ths
        if not s.api_base:
            return AuthCallResult(ok=False, status_code=None, data=None,
                                  problems=["未配置 SR_THS_API_BASE"])
        return self.get(f"{s.api_base.rstrip('/')}/custom-block", verify_login=True)

    def quote(self, code: str) -> AuthCallResult:
        """行情快照（网页端 cookie 鉴权）。硬鉴权：必须已登录。

        ⚠️ 接口待抓包确认：同花顺网页行情真实 XHR 路径需在登录后浏览器 Network 中确认。
        code 形如 600519。
        """
        self.ensure_logged_in(verify=False)
        raise NotImplementedError(
            "同花顺网页行情接口 path 待抓包确认，暂不可用。"
            "请在登录后浏览器 Network 中确认真实请求路径后更新 quote() 实现。"
        )
