"""涨停复盘 API：任意平台 → 多源对账 → 统一引擎 → 题材族群看板。"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter

from stock_review.adapters.datasource.akshare_source import AKShareSource
from stock_review.adapters.datasource.dxr_source import DxrKaipanSource, DxrLimitUpSource
from stock_review.services.zt_compare import merge_sources
from stock_review.services.zt_engine import build as build_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/zt", tags=["涨停复盘"])

# 可用源列表：新增平台（同花顺/开盘啦/雪球）只需实现 get_limit_up_pool 并在此注册，
# 即自动参与多源对账，无需改动引擎与前端。主源（实时涨停榜）放首位。
#   dxr     : 短线侠实时涨停榜（软鉴权公开接口）
#   dxr_kp  : 短线侠开盘连板榜（同源独立端点，交叉校验连板数）
#   akshare : 东方财富涨停池（免登录，独立第三方，提供权威连板数）
_SOURCES = {
    "dxr": DxrLimitUpSource,
    "dxr_kp": DxrKaipanSource,
    "akshare": AKShareSource,
}
_PRIMARY = "dxr"


@router.get("/pool")
def zt_pool(trade_date: date | None = None, source: str = "dxr,dxr_kp,akshare"):
    """涨停复盘报告：多源合并对账 → 族群聚合 / 题材分组 / 连板梯队。

    source: 逗号分隔的多源清单，默认 dxr(实时涨停榜),dxr_kp(开盘连板榜) 双源对账。
    返回 report 含 compare 段（共识/分歧/单源统计 + 各源贡献 + 冲突明细）。
    """
    td = trade_date or date.today()
    records_by_source: dict[str, list] = {}
    for name in source.split(","):
        name = name.strip()
        if name not in _SOURCES:
            continue
        try:
            recs = _SOURCES[name]().get_limit_up_pool(td)
            if recs:
                records_by_source[name] = recs
        except Exception as e:  # noqa: BLE001
            logger.warning("源 %s 拉取失败：%s", name, e)

    if not records_by_source:
        return build_report([], trade_date)

    cmp = merge_sources(records_by_source, primary=_PRIMARY)
    report = build_report(cmp["reconciled"], trade_date)
    # 透出对账元数据，前端据此展示一致性/分歧
    report["compare"] = {k: v for k, v in cmp.items() if k != "reconciled"}
    report["sources_used"] = list(records_by_source.keys())
    return report


@router.get("/sources")
def zt_sources():
    return {
        "sources": list(_SOURCES.keys()),
        "primary": _PRIMARY,
        "displays": {k: v().display for k, v in _SOURCES.items()},
    }


@router.get("/hot")
def zt_hot():
    try:
        return {"topics": _SOURCES["dxr"]().get_hot_list()}
    except Exception:
        return {"topics": []}
