"""涨停复盘 API：任意平台 → 多源对账 → 统一引擎 → 题材族群看板。"""
from __future__ import annotations

import concurrent.futures
import logging
import re
from datetime import date

from fastapi import APIRouter

from stock_review.adapters.datasource.akshare_source import AKShareSource
from stock_review.adapters.datasource.dxr_source import DxrKaipanSource, DxrLimitUpSource
from stock_review.adapters.platforms import get_connector
from stock_review.services.enrich import enrich_history
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


def _fetch_group_ctx() -> dict:
    """分组上下文（best-effort）：短线侠异动/热股集合，失败降级为空。

    用于「最近异动」「最近热股」分类；解析宽松（提取恰好 6 位数字的 A 股代码）。
    每个接口带 12s 硬性超时护栏，绝不因短线侠接口卡死而拖垮整个复盘 API。
    """
    ctx: dict[str, set] = {"yidong_codes": set(), "hot_codes": set()}
    stats: dict[str, int] = {"yidong": 0, "hot": 0}

    def _safe(fn):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(fn).result(timeout=12)
        except Exception:  # noqa: BLE001
            return None

    try:
        c = get_connector("dxr")
        ry = _safe(lambda: c.yidong_all())
        if ry and ry.ok and ry.data:
            codes = re.findall(r"(?<!\d)(\d{6})(?!\d)", str(ry.data))
            ctx["yidong_codes"].update(codes)
            stats["yidong"] = len(codes)
        rh = _safe(lambda: c.hot_list())
        if rh and rh.ok and isinstance(rh.data, dict):
            for t in rh.data.get("stock_topic", []):
                txt = f"{t.get('title', '')} {t.get('url', '')} {t.get('name', '')}"
                codes = re.findall(r"(?<!\d)(\d{6})(?!\d)", txt)
                ctx["hot_codes"].update(codes)
                stats["hot"] += len(codes)
    except Exception as e:  # noqa: BLE001
        logger.warning("分组上下文预取失败（降级）: %s", e)
    ctx["_stats"] = stats
    return ctx


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
    reconciled = cmp["reconciled"]

    # 历史涨幅富集（非涨停排序 func 用），失败静默降级（不阻断主流程）
    try:
        enrich_history(reconciled, td)
    except Exception as e:  # noqa: BLE001
        logger.warning("历史涨幅富集失败（降级）: %s", e)

    # 分组上下文：异动/热股集合（best-effort，失败降级为空）
    group_ctx = _fetch_group_ctx()

    report = build_report(reconciled, trade_date, group_ctx=group_ctx)
    # 透出对账元数据，前端据此展示一致性/分歧
    report["compare"] = {k: v for k, v in cmp.items() if k != "reconciled"}
    report["sources_used"] = list(records_by_source.keys())
    # 抓取统计（异动/热股接口是否取到数据，便于排查空桶）
    report["group_ctx"] = group_ctx.get("_stats", {"yidong": 0, "hot": 0})
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
