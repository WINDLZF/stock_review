"""短线侠连接器：部分软鉴权（公开接口免登录）+ 硬鉴权（私有接口必须登录）。

⚠️ 鉴权边界（务必遵守，避免封号）：
- **公开接口**（抓包确认无需登录即可访问）：ztlive / ztplate / kaipan / yidong / hotlist。
  这些走 `_call`（软鉴权）：有登录态自动附带鉴权头解锁更多数据；无登录态降级走公开。
  二者都不裸发重试、**不会越红线**——它们是公开 CDN 文件，无封号风险。
- **私有 / 需鉴权接口**（若存在）：必须用 `_call_auth`（硬鉴权），未登录直接抛 NeedLoginError，
  **绝不**在「无登录态」时去碰私有接口——那是踩红线（被封号）。

登录态获取：`stock-review login dxr`。真实 XHR 接口由 sniff 确认（见 .secrets/dxr_sniff.json），
本连接器直接对接，不再瞎猜 path。
合规边界：401/403 不重试，避免被封 IP。

已确认的接口（2026-07-18 抓包）：
- 涨停表现(实时)  GET  duanxianxia.com/vendor/stockdata/ztlive.json
                    → {result, list:[{code,name,ztyy(涨停原因),zt(几天几板),time}]}
- 涨停板块        GET  duanxianxia.com/vendor/stockdata/ztplate.json
                    → {list:[{code,plate,concept}]}
- 开盘/连板榜     POST bm.duanxianxia.com/data/getKaipanStock/web  (form plateCode)
                    → {list:[[code,name,涨幅%,...]]}
- 开盘子板块      POST bm.duanxianxia.com/data/getKaipanSubPlate   (form plateCode)
                    → {result:"<button class='subplate' plateCode='...'>..."}
- 异动全览        POST duanxianxia.com/api/getYidongAll            → HTML 异动表
- 热点榜          GET  x.duanxianxia.cn/vendor/stockdata/hotlist.json
                    → {stock_topic:[{title,url,rate,...}]}

合规边界：仅对接用户本人已合法登录站点前端自身发起的接口用于自有数据消费；
401/403 不重试，避免被封 IP。
"""
from __future__ import annotations

import json
from typing import Any

from stock_review.adapters.platforms.base import AuthCallResult, BasePlatformConnector
from stock_review.core.registry import connector_registry

_BM = "https://bm.duanxianxia.com"
_WEB = "https://duanxianxia.com"
_X = "https://x.duanxianxia.cn"


def _parse_json(res: AuthCallResult) -> AuthCallResult:
    """把 text 结果解析为 JSON；失败则标记问题并返回原 text。"""
    if not res.ok or res.data is None:
        return res
    try:
        res.data = json.loads(res.data)
    except (json.JSONDecodeError, TypeError) as e:
        return AuthCallResult(
            ok=False,
            status_code=res.status_code,
            data=res.data,
            problems=[f"响应非 JSON（可能登录态失效/被反爬）: {e}"],
        )
    return res


@connector_registry.register("dxr")
class DxrConnector(BasePlatformConnector):
    platform = "dxr"
    display = "短线侠"
    base_url = _WEB
    token_keys = ()

    # ── 软鉴权请求封装（公开接口专用）──
    def _call(self, method: str, url: str, **kw: Any) -> AuthCallResult:
        """软鉴权请求（仅用于已确认「公开可访问」的接口）：有登录态则附带鉴权头
        （解锁更多/私有数据）；无则降级到公开接口。

        不抛 NeedLoginError——基础行情无需登录即可取；若接口改用会话鉴权返回
        401/403，会附上「建议先登录」提示，而不是裸奔重试（避免被封 IP）。
        """
        res = self.request(method, url, verify_login=False, **kw)
        if not res.ok and res.status_code in (401, 403) and not self.is_logged_in():
            res.problems.append(
                f"[{self.platform}] 该接口可能需登录态：先 `stock-review login "
                f"{self.platform}` 再试（登录后数据更全）"
            )
        return res

    # ── 硬鉴权请求封装（私有/需鉴权接口专用，绝不越红线）──
    def _call_auth(self, method: str, url: str, **kw: Any) -> AuthCallResult:
        """硬鉴权请求：必须已登录，未登录直接抛 NeedLoginError，绝不裸发私有接口。

        短线侠的私有/付费数据接口必须先 `stock-review login dxr` 再调；无登录态时去碰
        会踩红线（被封号），故这里强制 verify_login=True，绝不做「无登录态降级」。
        """
        return self.request(method, url, verify_login=True, **kw)

    # ── 涨停表现 / 板块（实时榜，抓包确认）──
    def limit_up_board(self, date: str = "") -> AuthCallResult:
        """涨停表现（实时涨停榜）：取自 /vendor/stockdata/ztlive.json。

        返回 list[{code, name, ztyy(涨停原因), zt(几天几板), time}]。
        date 预留（该文件为实时榜；传参仅追加到 query，由服务端决定是否按日）。
        """
        url = f"{self.base_url}/vendor/stockdata/ztlive.json"
        if date:
            url += f"?date={date}"
        res = self._call("GET", url)
        if not res.ok:
            return res
        res = _parse_json(res)
        if res.ok and isinstance(res.data, dict):
            res.data = res.data.get("list", [])
        return res

    def limit_up_plates(self) -> AuthCallResult:
        """涨停板块：取自 /vendor/stockdata/ztplate.json，返回板块+概念。

        返回 list[{code, plate, concept}]。
        """
        res = self._call("GET", f"{self.base_url}/vendor/stockdata/ztplate.json")
        if not res.ok:
            return res
        res = _parse_json(res)
        if res.ok and isinstance(res.data, dict):
            res.data = res.data.get("list", [])
        return res

    def kaipan_board(self, plate_code: str = "801120") -> AuthCallResult:
        """开盘/连板榜：POST bm.duanxianxia.com/data/getKaipanStock/web，form plateCode。

        plateCode 默认 801120（开盘啦主连板榜）；返回 {list:[[code,name,涨幅%,...],...]}。
        """
        res = self._call(
            "POST", f"{_BM}/data/getKaipanStock/web",
            data={"plateCode": plate_code},
        )
        if not res.ok:
            return res
        return _parse_json(res)

    def kaipan_subplate(self, plate_code: str = "801120") -> AuthCallResult:
        """开盘子板块按钮：POST bm.duanxianxia.com/data/getKaipanSubPlate，form plateCode。

        返回 HTML 片段（含各子板块 plateCode，供进一步 kaipan_board 下钻）。
        """
        return self._call(
            "POST", f"{_BM}/data/getKaipanSubPlate",
            data={"plateCode": plate_code},
        )

    def yidong_all(self) -> AuthCallResult:
        """异动全览：POST /api/getYidongAll，返回 HTML 异动表（含 code/名称/异动类型/时间）。

        结构为 <tr class='yd' ...>，需另行解析；此处返回原始 HTML 文本。
        """
        return self._call("POST", f"{self.base_url}/api/getYidongAll")

    def hot_list(self) -> AuthCallResult:
        """热点榜：GET x.duanxianxia.cn/vendor/stockdata/hotlist.json。

        返回 {stock_topic:[{title,url,rate,type,...}]}。
        """
        res = self._call("GET", f"{_X}/vendor/stockdata/hotlist.json")
        if not res.ok:
            return res
        return _parse_json(res)

    def smoke(self) -> AuthCallResult:
        """冒烟：用公开接口验证连通性（无需登录即可证明网络/接口可达）。"""
        return self.limit_up_board()
