"""DXR 短线侠数据源：实现 MarketDataSource 协议，提供实时涨停池。"""
from __future__ import annotations

import re
from datetime import date

from stock_review.adapters.platforms import get_connector
from stock_review.core.config import get_settings
from stock_review.core.registry import source_registry
from stock_review.domain.entities import Exchange, LimitType, Stock


def _code_to_exchange(code: str) -> Exchange:
    if code.startswith("6"):
        return Exchange.SH
    if code.startswith(("0", "3")):
        return Exchange.SZ
    if code.startswith(("8", "4")):
        return Exchange.BJ
    return Exchange.UNKNOWN


def _code_to_limit_pct(code: str) -> int:
    """涨停幅度档位：北交所 30cm / 创业板·科创板 20cm / 主板 10cm。

    仅依代码前缀判定，与是否真涨停无关（用于排序的 30>20>10 分层）。
    """
    if code.startswith(("688", "689")):
        return 20  # 科创板
    if code.startswith(("300", "301")):
        return 20  # 创业板
    if code.startswith(("8", "4", "920")):
        return 30  # 北交所（8/4 开头，920 为新代码段）
    return 10  # 主板（60/00/30 外的上深主）


def _parse_board_full(text: str) -> tuple[int | None, int | None]:
    """解析'X天Y板' → (天数 M, 连板数 Y)。

    '3天2板' → (3, 2)  | '首板' → (1, 1)  | '2连板' → (2, 2)
    '7天4板' → (7, 4)  | 解析不出 → (None, None)
    注意：M 是天数（连板跨度），N 是连板数；排序用 N 降序、M 升序。
    """
    if not text:
        return (None, None)
    if "首板" in text:
        return (1, 1)
    m = re.search(r"(\d+)天(\d+)板", text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d+)连板", text)
    if m:
        return (int(m.group(1)), int(m.group(1)))
    m = re.search(r"(\d+)板", text)
    if m:
        n = int(m.group(1))
        return (n, n)
    return (None, None)


@source_registry.register("dxr")
class DxrLimitUpSource:
    """DXR 涨停池数据源。name 与连接器平台名一致，便于统一寻址。"""

    name = "dxr"
    display = "短线侠"
    is_online = True

    def get_daily_bars(self, code: str, start: date, end: date):
        raise NotImplementedError("DXR 不提供 K 线")

    def get_realtime_quotes(self, codes: list[str]):
        raise NotImplementedError("DXR 不提供实时行情")

    def get_limit_up_pool(self, trade_date: date) -> list[Stock]:
        """从 DXR 实时涨停榜拉取，解析为 Stock 列表。"""
        c = get_connector("dxr")
        r = c.limit_up_board()
        if not r.ok or not isinstance(r.data, list):
            return []

        # 取板块映射（code → plate/concept）
        plate_map = {}
        rp = c.limit_up_plates()
        if rp.ok and isinstance(rp.data, list):
            for p in rp.data:
                plate_map[p.get("code", "")] = p

        stocks: list[Stock] = []
        for item in r.data:
            code = str(item.get("code", "")).strip()
            if not code or len(code) != 6:
                continue
            name = str(item.get("name", "")).strip()
            zt_text = str(item.get("zt", "")).strip()
            reason = str(item.get("ztyy", "")).strip()
            ft = str(item.get("time", "")).strip()

            plate_info = plate_map.get(code, {})
            plate = str(plate_info.get("plate", "")).strip()
            concept = str(plate_info.get("concept", "")).strip()
            theme = concept or plate

            days, boards = _parse_board_full(zt_text)
            lt = LimitType.ONE_WORD if "一字" in zt_text else (
                LimitType.T_WORD if "T字" in zt_text else LimitType.TURNOVER
            )

            stocks.append(Stock(
                code=code,
                name=name,
                exchange=_code_to_exchange(code),
                price=0.0,
                change_pct=10.0,
                limit_up_time=ft,
                limit_type=lt,
                boards=boards or 1,
                days=days or 1,
                limit_pct=_code_to_limit_pct(code),
                reason=reason,
                theme=theme,
                tags=[plate, concept] if plate or concept else [],
                extra={
                    "source": "dxr",
                    "zt_text": zt_text,
                    "plate": plate,
                    "concept": concept,
                },
            ))
        return stocks

    # ── 平台特有数据 ──
    def get_hot_list(self) -> list[dict]:
        c = get_connector("dxr")
        r = c.hot_list()
        if r.ok and isinstance(r.data, dict):
            return r.data.get("stock_topic", [])
        return []

    def get_limit_up_plates(self) -> list[dict]:
        c = get_connector("dxr")
        r = c.limit_up_plates()
        if r.ok and isinstance(r.data, list):
            return r.data
        return []

    def get_money_flow(self, code: str, start: date, end: date):
        raise NotImplementedError

    def get_fundamentals(self, code: str):
        raise NotImplementedError


@source_registry.register("dxr_kp")
class DxrKaipanSource:
    """DXR 开盘连板榜：与 zt_limit_up 同源但**独立端点**（bm.duanxianxia.com 连板榜），
    用作多源对账的第二信号，交叉校验连板数与涨停真伪。

    行结构（抓包确认）：
      [0]code [1]name [2]今日涨幅% [3]? [4]原始连板数(不可靠，弃用)
      [5]价格 [6]? [7..11]资金流 [12]连板文本('3天2板'/'首板'/'2连板') [13]龙头位('龙一')
    """

    name = "dxr_kp"
    display = "短线侠·连板榜"
    is_online = True

    def get_daily_bars(self, code: str, start: date, end: date):
        raise NotImplementedError("DXR 不提供 K 线")

    def get_realtime_quotes(self, codes: list[str]):
        raise NotImplementedError("DXR 不提供实时行情")

    def get_limit_up_pool(self, trade_date: date) -> list[Stock]:
        c = get_connector("dxr")
        r = c.kaipan_board()
        if not r.ok or not isinstance(r.data, dict):
            return []
        rows = r.data.get("list", [])
        stocks: list[Stock] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 14:
                continue
            code = str(row[0]).strip()
            if not code or len(code) != 6:
                continue
            chg = float(row[2]) if isinstance(row[2], (int, float)) else 0.0
            # 仅保留真实涨停（连板榜可能混入开板票），避免把非涨停带进池子
            if chg < 9.5:
                continue
            name = str(row[1]).strip()
            board_text = str(row[12]).strip()
            rank = str(row[13]).strip()
            days, boards = _parse_board_full(board_text)
            stocks.append(Stock(
                code=code,
                name=name,
                exchange=_code_to_exchange(code),
                price=float(row[5]) if isinstance(row[5], (int, float)) else 0.0,
                change_pct=chg,
                limit_type=LimitType.TURNOVER,
                boards=boards or 1,
                days=days or 1,
                limit_pct=_code_to_limit_pct(code),
                reason="",
                theme="",
                tags=[rank] if rank else [],
                extra={
                    "source": "dxr_kp",
                    "board_text": board_text,
                    "kp_raw_num": row[4],  # 仅供透明展示，不参与研判
                    "kp_rank": rank,
                },
            ))
        return stocks

    def get_money_flow(self, code: str, start: date, end: date):
        raise NotImplementedError

    def get_fundamentals(self, code: str):
        raise NotImplementedError
