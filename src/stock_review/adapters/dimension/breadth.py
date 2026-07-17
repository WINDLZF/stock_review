"""市场宽度维度：涨跌家数 / 涨停跌停 / 连板分布。

以复盘上下文的涨停池(ctx.stocks)为主输入；若仓储支持，补充跌停池计数。
这是专业复盘的第一视角——市场情绪与赚钱效应。
"""
from __future__ import annotations

from stock_review.core.registry import dimension_registry
from stock_review.domain.ports import AnalysisDimension, DimensionMeta, DimensionResult, ReviewContext


@dimension_registry.register("breadth")
class BreadthDimension:
    def meta(self) -> DimensionMeta:
        return DimensionMeta(key="breadth", title="市场宽度", description="涨跌/涨停跌停/连板", order=1)

    def compute(self, ctx: ReviewContext) -> DimensionResult:
        pool = ctx.stocks
        up = len(pool)
        boards_dist: dict[int, int] = {}
        for st in pool:
            boards_dist[st.boards] = boards_dist.get(st.boards, 0) + 1
        board_rows = [
            {"连板数": k, "家数": v}
            for k, v in sorted(boards_dist.items(), reverse=True)
        ]
        summary = (
            f"当日涨停 {up} 家；最高连板 "
            f"{max(boards_dist) if boards_dist else 0} 板"
        )
        return DimensionResult(
            key="breadth",
            title="市场宽度（涨停视角）",
            summary=summary,
            tables=[{"columns": ["连板数", "家数"], "rows": board_rows}] if board_rows else [],
            data={"limit_up": up, "max_board": max(boards_dist) if boards_dist else 0},
        )
