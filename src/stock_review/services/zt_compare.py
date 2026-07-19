"""多源对账引擎：把多个平台/端点的涨停池合并，交叉校验后「再下结论」。

设计动机（回应「数据有错误，对比各平台再作结论」）：
- 单一数据源（哪怕是同平台不同端点）都可能出现连板数错乱、把开板票算进涨停榜等错误。
- 本引擎按「代码」归并多源记录，对连板数做交叉校验：
    * 多源一致 → 高置信，直接采用；
    * 多源冲突 → 标记 board_conflict，默认信任主源（实时涨停榜），但把各源取值透出给前端，
      绝不静默拍板，避免把错误结论带进连板梯队/题材归类；
    * 仅单源出现 → 标记 single_source（孤证），置信度低于多源共识。
- 框架对「源」完全开放：短线侠(实时榜/连板榜) 现已接入；同花顺/开盘啦/雪球只需实现
  MarketDataSource.get_limit_up_pool() 并在 routes/zt.py 的 _SOURCES 注册即可参与对账。

约定：Stock.boards == 0 表示「该源未给出连板数」（未知），不计入连板数投票，
但仍证明该票出现在涨停池（存在性确认）。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from stock_review.domain.entities import Stock


def _info_score(s: Stock) -> int:
    """信息完整度：用于挑「代表票」（理由/封板时间/标签越多越完整）。"""
    return (
        len(s.reason or "")
        + len(s.limit_up_time or "")
        + 2 * len(s.tags or [])
    )


def merge_sources(
    records_by_source: dict[str, list[Stock]],
    primary: str = "dxr",
) -> dict[str, Any]:
    """合并多源涨停记录，产出对账结果。

    records_by_source: {源名: [Stock, ...]}。
    返回：
      {
        "reconciled": [Stock, ...],   # 去重合并后的个股（含对账元数据）
        "conflicts":  [ {...}, ... ],  # 连板数跨源冲突明细
        "per_source_counts": {源名: 数量},
        "consensus_count": int,        # 多源一致
        "single_count": int,           # 单源孤证
        "conflict_count": int,         # 连板数冲突
        "total": int,
      }
    每张 reconciled 票的 extra 含：
      sources / source_count / single_source / board_conflict /
      board_by_source / board_unknown
    """
    by_code: dict[str, list[tuple[str, Stock]]] = defaultdict(list)
    for sname, stocks in records_by_source.items():
        for s in stocks:
            if s.code:
                by_code[s.code].append((sname, s))

    per_source_counts = {sname: len(stocks) for sname, stocks in records_by_source.items()}

    reconciled: list[Stock] = []
    conflicts: list[dict[str, Any]] = []

    for code, items in by_code.items():
        srcs = [sn for sn, _ in items]
        stocks = [s for _, s in items]

        # 连板数投票：仅统计 >0（已知）的取值
        board_map: dict[str, int] = {}
        for sn, s in items:
            if s.boards and s.boards > 0:
                board_map[sn] = s.boards

        # 代表票：信息最完整者（通常来自实时涨停榜，带理由/封板时间）
        rep = max(stocks, key=_info_score)

        board_vals = list(board_map.values())
        board_conflict = len(set(board_vals)) > 1 if board_vals else False

        if board_map:
            # 默认信任主源；主源未知时取最大观测值（连板数不会更多，取最大更保守）
            final = board_map.get(primary)
            if final is None:
                final = max(board_vals)
        else:
            final = 1  # 无任何源给连板数，按首板兜底，但标记 unknown

        rep.boards = final
        rep.extra["sources"] = srcs
        rep.extra["source_count"] = len(srcs)
        rep.extra["single_source"] = len(srcs) == 1
        rep.extra["board_conflict"] = board_conflict
        rep.extra["board_unknown"] = not board_map
        rep.extra["board_by_source"] = board_map

        if board_conflict:
            conflicts.append({
                "code": code,
                "name": rep.name,
                "board_by_source": board_map,
                "resolved": final,
            })

        reconciled.append(rep)

    consensus = [s for s in reconciled if not s.extra["board_conflict"] and not s.extra["single_source"]]
    single = [s for s in reconciled if s.extra["single_source"]]

    return {
        "reconciled": reconciled,
        "conflicts": conflicts,
        "per_source_counts": per_source_counts,
        "consensus_count": len(consensus),
        "single_count": len(single),
        "conflict_count": len(conflicts),
        "total": len(reconciled),
    }
