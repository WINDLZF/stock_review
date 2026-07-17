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
        board_names: dict[int, list[str]] = {}
        for st in pool:
            boards_dist[st.boards] = boards_dist.get(st.boards, 0) + 1
            board_names.setdefault(st.boards, []).append(st.name or st.code)

        # 连板天梯：连板数 -> 家数 / 代表个股
        ladder_rows = [
            {
                "连板数": f"{k}板" if k >= 2 else ("首板" if k == 1 else "—"),
                "家数": v,
                "代表个股": "、".join(board_names[k][:6]),
            }
            for k, v in sorted(boards_dist.items(), reverse=True)
        ]
        # 涨停明细：个股 / 连板 / 涨幅 / 涨停原因
        detail_rows = [
            {
                "个股": f"{st.name}({st.code})",
                "连板": f"{st.boards}板" if st.boards >= 2 else ("首板" if st.boards == 1 else "—"),
                "涨幅%": round(st.change_pct, 2),
                "涨停类型": st.limit_type.value or "—",
                "涨停原因": st.reason or "—",
            }
            for st in sorted(pool, key=lambda s: -s.boards)
        ]
        max_board = max(boards_dist) if boards_dist else 0
        summary = (
            f"当日涨停 {up} 家；最高连板 {max_board} 板"
            + ("，市场情绪偏强" if max_board >= 4 else "，连板高度有限")
        )
        return DimensionResult(
            key="breadth",
            title="市场宽度（涨停视角）",
            summary=summary,
            tables=[
                {"title": "连板天梯", "columns": ["连板数", "家数", "代表个股"], "rows": ladder_rows},
                {"title": "涨停明细", "columns": ["个股", "连板", "涨幅%", "涨停类型", "涨停原因"], "rows": detail_rows},
            ],
            data={"limit_up": up, "max_board": max_board},
        )
