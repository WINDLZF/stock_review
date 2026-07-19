"""开盘啦连接器：登录态保证 + 受控请求。

⚠️ 重要鉴权校准（避免闭门造车 / 不重复试错）：
开盘啦的**行情/情绪/涨停数据在 App 端**，接口域为 `apphwshhq.longhuvip.com`（板块）
与 `apphis.longhuvip.com`（历史/个股成分），鉴权 **不是网页 cookie**，而是
URL 内联的 `UserID` + `Token` 参数，且必须带 `Dalvik/...` 移动端 UA（非 Dalvik UA 返回空）。
参考：github.com/Rainynitesky/kaipanla-data-parser、github.com/jinhao2003/kaipanla-crawler。

→ 因此：光靠「网页登录 cookie」**调不通**开盘啦数据接口。本连接器有两种模式：
  1) App 令牌模式（推荐）：通过 `KPL_USER_ID` / `KPL_TOKEN` 注入 App 端 UserID+Token，
     直接走 App 接口（如板块强度 `C=ZHISHURANKING&PlateID=...`）。
  2) 网页模式（仅验证）：用网页登录 cookie 验证「网页登录态能否带上」，但**不声称能调数据接口**。

若未注入 App 令牌，smoke() 明确报错提示，绝不裸发/假装调通。
"""
from __future__ import annotations

import os
from typing import Any

from stock_review.adapters.platforms.base import AuthCallResult, BasePlatformConnector
from stock_review.core.auth.cookie_store import DEFAULT_SECRETS_DIR
from stock_review.core.registry import connector_registry

# App 端数据接口域（参考 kaipanla-data-parser）
_KPL_APP_HOST = "https://apphwshhq.longhuvip.com"
_KPL_APP_HIS_HOST = "https://apphis.longhuvip.com"
# App 通用参数（需真实 UserID/Token，从抓包获得）
_KPL_APIV = "w44"
_KPL_VER = "5.23.0.4"


@connector_registry.register("kpl")
class KplConnector(BasePlatformConnector):
    platform = "kpl"
    display = "开盘啦"
    base_url = "https://www.kaipanla.com"
    token_keys = ()

    def __init__(self, secrets_dir: Any = DEFAULT_SECRETS_DIR):
        super().__init__(secrets_dir)
        self.user_id = os.getenv("KPL_USER_ID", "")
        self.token = os.getenv("KPL_TOKEN", "")

    # ── App 端鉴权参数（不靠网页 cookie）──
    def _app_common_params(self) -> str:
        """App 端通用鉴权参数串（UserID+Token 在 URL 内，非 cookie）。"""
        return (
            f"PhoneOSNew=1&DeviceID=kpl&VerSion={_KPL_VER}&apiv={_KPL_APIV}"
            f"&UserID={self.user_id}&Token={self.token}"
        )

    def _app_headers(self) -> dict[str, str]:
        # 必须 Dalvik UA，否则返回空 List（kaipanla-data-parser 已踩坑）
        return {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; ALN-AL00 Build/W528JS)",
            "Connection": "Keep-Alive",
        }

    def has_app_token(self) -> bool:
        return bool(self.user_id and self.token)

    # ── 真实 App 接口：板块强度（借鉴 kaipanla-data-parser GETPLATE_INFO_QJ）──
    def sector_strength(self, plate_id: str, date: str = "") -> AuthCallResult:
        """板块强度/涨停数。`plate_id` 如 801159（概念板块）。需 App 令牌。"""
        if not self.has_app_token():
            return AuthCallResult(
                ok=False, status_code=None, data=None,
                problems=[
                    "开盘啦数据在 App 端，网页登录 cookie 调不通；需注入 App 令牌："
                    "设置环境变量 KPL_USER_ID / KPL_TOKEN（从开盘啦 App 抓包获得 UserID+Token）"
                ],
            )
        qs = f"C=ZHISHURANKING&PlateID={plate_id}"
        if date:
            qs += f"&Date={date}"
        qs += "&" + self._app_common_params()
        return self.request(
            "GET", f"{_KPL_APP_HOST}/getdata?{qs}",
            verify_login=False,  # App 令牌模式不走网页 cookie 闸门
            headers=self._app_headers(),
        )

    def smoke(self) -> AuthCallResult:
        # App 令牌可用 → 真调一个板块强度接口验证通路
        if self.has_app_token():
            return self.sector_strength("801159")
        # 否则只验证网页登录态能否带上（诚实标注：不等同于能调数据接口）
        try:
            self.ensure_logged_in(verify=True)
        except Exception as e:  # noqa: BLE001
            return AuthCallResult(
                ok=False, status_code=None, data=None,
                problems=[f"网页登录态验证失败: {e}",
                          "注：开盘啦数据在 App 端，即使网页登录成功也需 KPL_USER_ID/KPL_TOKEN 才能取数"],
            )
        return AuthCallResult(
            ok=True, status_code=None, data=None,
            problems=[
                "网页登录态已验证通过，但开盘啦数据在 App 端，需 KPL_USER_ID/KPL_TOKEN 才能调数据接口；"
                "请注入 App 令牌后重跑 connect kpl"
            ],
        )
