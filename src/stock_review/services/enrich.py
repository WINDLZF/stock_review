"""历史涨幅 enrichment：为非涨停排序提供 chg_5d / chg_10d。

仅 akshare 能免登录取历史 K 线；拉取失败/超时则静默降级（保持 0，
引擎排序退化为只用「今日涨幅」），不影响主流程与其他源。

非涨停排序 func（见 zt_engine.strength_score）：
    strength = 0.5*今日涨幅 + 0.3*近5日涨幅 + 0.2*近10日涨幅
权重集中放在本模块，便于调参。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any

from stock_review.domain.entities import Stock

logger = logging.getLogger(__name__)

# 非涨停排序 func 权重：(今日, 近5日, 近10日)
_STRENGTH_WEIGHTS = (0.5, 0.3, 0.2)


def _ak():
    try:
        import akshare as ak  # noqa: PLC0415
        return ak
    except ImportError:
        return None


def _compute_chg(closes: list[float], n: int) -> float:
    """最近 n 个交易日累计涨幅 %。closes 已按时间升序。"""
    if len(closes) < n + 1:
        return 0.0
    base = closes[-(n + 1)]
    if base <= 0:
        return 0.0
    return round((closes[-1] / base - 1) * 100, 2)


def _fetch_one(ak, code: str, end: date) -> tuple[str, dict[str, float]]:
    start = end - timedelta(days=35)
    df = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"), adjust="qfq",
    )
    closes = [float(x) for x in df["收盘"].tolist()] if df is not None and len(df) else []
    return code, {
        "chg_5d": _compute_chg(closes, 5),
        "chg_10d": _compute_chg(closes, 10),
    }


def strength_score(s: Stock) -> float:
    """非涨停排序强度分：今日/近5日/近10日 加权，降序即越强。"""
    return (_STRENGTH_WEIGHTS[0] * s.change_pct
            + _STRENGTH_WEIGHTS[1] * s.chg_5d
            + _STRENGTH_WEIGHTS[2] * s.chg_10d)


def enrich_history(
    stocks: list[Stock],
    trade_date: date | None = None,
    max_workers: int = 8,
    budget_sec: int = 45,
) -> None:
    """就地填充每只票的 chg_5d / chg_10d。任何失败静默降级（不抛）。"""
    ak = _ak()
    if ak is None or not stocks:
        return
    td = trade_date or date.today()
    codes = sorted({s.code for s in stocks if s.code})
    if not codes:
        return

    import time  # noqa: PLC0415
    t0 = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_fetch_one, ak, c, td): c for c in codes}
            finished = 0
            for f in as_completed(futs):
                finished += 1
                try:
                    code, res = f.result()
                    for s in stocks:
                        if s.code == code:
                            s.chg_5d = res["chg_5d"]
                            s.chg_10d = res["chg_10d"]
                except Exception as e:  # noqa: BLE001
                    logger.warning("历史涨幅拉取失败(%s): %s", futs[f], e)
                # 预算保护：超过预算则不再等待剩余（已填充的保留）
                if budget_sec and (time.monotonic() - t0) > budget_sec:
                    logger.warning("enrich_history 超时预算(%ss)，剩余 %d 只未拉取",
                                   budget_sec, len(futs) - finished)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("enrich_history 异常降级: %s", e)
