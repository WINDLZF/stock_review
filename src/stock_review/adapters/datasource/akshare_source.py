"""akshare 数据源：免费、覆盖最广，默认启用。

借鉴 zt-review 的"用 akshare 取行情/涨停池"思路，但重写为类型安全、可降级的实现；
akshare 缺失时给出明确错误，不影响系统其他部分。新增 tushare/平台API/通达信离线只需
在同级加一个模块并 @source_registry.register，无需改此处。
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from stock_review.core.registry import source_registry
from stock_review.domain.entities import Bar, Quote, Stock
from stock_review.domain.ports import MarketDataSource


def _ak():
    try:
        import akshare as ak  # noqa: PLC0415
        return ak
    except ImportError as e:  # 缺失即降级报错，不静默
        raise RuntimeError(
            "未安装 akshare。请 `uv add akshare` 或在 config.yaml 关闭该数据源。"
        ) from e


def _strip_prefix(code: str) -> str:
    """akshare 用 6 位纯数字代码；去掉 sh/sz/bj 前缀。"""
    return code.replace("sh", "", 1).replace("sz", "", 1).replace("bj", "", 1).zfill(6)


def _market_of(code: str) -> str:
    return "sh" if code.startswith("6") else "sz"


@source_registry.register("akshare")
class AKShareSource:
    name = "akshare"

    # ── 日K线 ──
    def get_daily_bars(self, code: str, start: date, end: date) -> list[Bar]:
        ak = _ak()
        df = ak.stock_zh_a_hist(
            symbol=_strip_prefix(code),
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
        bars: list[Bar] = []
        for _, r in df.iterrows():
            bars.append(
                Bar(
                    date=pd.to_datetime(r["日期"]).to_pydatetime(),
                    open=float(r["开盘"]),
                    high=float(r["最高"]),
                    low=float(r["最低"]),
                    close=float(r["收盘"]),
                    volume=float(r["成交量"]),
                    amount=float(r["成交额"]),
                )
            )
        return bars

    # ── 实时快照（全市场快照过滤，批量少时可用）──
    def get_realtime_quotes(self, codes: list[str]) -> list[Quote]:
        ak = _ak()
        df = ak.stock_zh_a_spot_em()
        want = {_strip_prefix(c) for c in codes}
        out: list[Quote] = []
        for _, r in df.iterrows():
            if str(r["代码"]) in want:
                out.append(
                    Quote(
                        code=str(r["代码"]),
                        name=str(r["名称"]),
                        price=float(r["最新价"]),
                        change_pct=float(r["涨跌幅"]),
                        volume=float(r["成交量"]),
                        amount=float(r["成交额"]),
                    )
                )
        return out

    # ── 涨停池（复盘核心输入）──
    def get_limit_up_pool(self, trade_date: date) -> list[Stock]:
        ak = _ak()
        df = ak.stock_zt_pool_em(date=trade_date.strftime("%Y%m%d"))
        stocks: list[Stock] = []
        for _, r in df.iterrows():
            stocks.append(
                Stock(
                    code=str(r["代码"]),
                    name=str(r["名称"]),
                    price=float(r["收盘价"]),
                    change_pct=float(r["涨跌幅"]),
                    limit_up_time=str(r.get("涨停时间", "") or ""),
                    open_times=int(r.get("打开次数", 0) or 0),
                    boards=int(r.get("连板数", 1) or 1),
                    reason=str(r.get("涨停原因类别", "") or ""),
                )
            )
        return stocks

    # ── 个股资金流 ──
    def get_money_flow(self, code: str, start: date, end: date) -> dict[str, Any]:
        ak = _ak()
        df = ak.stock_individual_fund_flow(
            stock=_strip_prefix(code), market=_market_of(_strip_prefix(code))
        )
        mask = (df["日期"] >= pd.Timestamp(start)) & (df["日期"] <= pd.Timestamp(end))
        return df.loc[mask].to_dict(orient="records")

    # ── 基本面：akshare 财务口径不稳，交给 tushare；此处明确不支持 ──
    def get_fundamentals(self, code: str) -> dict[str, Any]:
        raise NotImplementedError("akshare 财务口径不稳，请用 tushare 数据源实现")
