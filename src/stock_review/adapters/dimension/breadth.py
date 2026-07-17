"""市场宽度维度：连板天梯 / 涨停明细。

直接展示 akshare 拉取的当日真实涨停数据（连板数、封板资金、所属行业、
首次/最后封板时间、炸板次数、涨停统计等），不做指标计算。
"""
from __future__ import annotations

from stock_review.core.registry import dimension_registry
from stock_review.domain.ports import AnalysisDimension, DimensionMeta, DimensionResult, ReviewContext


def _yi(x: float) -> str:
    """金额转为「亿」，保留 1 位小数。"""
    try:
        return f"{x / 1e8:.1f}"
    except (TypeError, ValueError):
        return "—"


def _time(hhmmss: str) -> str:
    """封板时间 '092500' -> '09:25'。"""
    s = str(hhmmss or "").strip()
    if len(s) >= 6:
        return f"{s[0:2]}:{s[2:4]}"
    if len(s) == 4:
        return f"{s[0:2]}:{s[2:4]}"
    return s or "—"


def _board_label(boards: int) -> str:
    if boards >= 2:
        return f"{boards}板"
    if boards == 1:
        return "首板"
    return "—"


@dimension_registry.register("breadth")
class BreadthDimension:
    def meta(self) -> DimensionMeta:
        return DimensionMeta(key="breadth", title="市场宽度", description="连板天梯/涨停明细", order=1)

    def compute(self, ctx: ReviewContext) -> DimensionResult:
        pool = ctx.stocks
        up = len(pool)
        if up == 0:
            return DimensionResult(
                key="breadth",
                title="市场宽度（涨停视角）",
                summary="当日无涨停数据（可能为非交易日或数据源返回为空）。",
                tables=[],
                data={"limit_up": 0, "max_board": 0},
            )

        # 连板天梯：连板数 -> 家数 / 代表个股
        boards_dist: dict[int, int] = {}
        board_names: dict[int, list[str]] = {}
        for st in pool:
            boards_dist[st.boards] = boards_dist.get(st.boards, 0) + 1
            board_names.setdefault(st.boards, []).append(st.name or st.code)
        ladder_rows = [
            {
                "连板数": _board_label(k),
                "涨停家数": v,
                "代表个股": "、".join(board_names[k][:8]),
            }
            for k, v in sorted(boards_dist.items(), reverse=True)
        ]

        # 涨停明细：按连板数、封板资金排序，展示真实字段
        detail_rows = []
        total_seal = 0.0
        one_word = 0
        for st in sorted(pool, key=lambda s: (-s.boards, -s.extra.get("seal_amount", 0.0))):
            ex = st.extra or {}
            seal = float(ex.get("seal_amount", 0.0) or 0.0)
            total_seal += seal
            if st.limit_type.value == "一字板":
                one_word += 1
            detail_rows.append(
                {
                    "序号": ex.get("order", ""),
                    "名称": st.name,
                    "代码": st.code,
                    "连板": _board_label(st.boards),
                    "涨跌幅%": round(st.change_pct, 2),
                    "所属行业": ex.get("industry", st.theme or "—"),
                    "首次封板": _time(ex.get("first_time", "")),
                    "封板资金(亿)": _yi(seal),
                    "成交额(亿)": _yi(float(ex.get("amount", 0.0) or 0.0)),
                    "流通市值(亿)": _yi(float(ex.get("float_mv", 0.0) or 0.0)),
                    "换手率%": round(float(ex.get("turnover", 0.0) or 0.0), 2),
                    "炸板次数": st.open_times,
                    "涨停统计": ex.get("zt_stat", "—"),
                }
            )

        max_board = max(boards_dist) if boards_dist else 0
        summary = (
            f"当日涨停 {up} 家；最高 {max_board} 连板；一字板 {one_word} 家；"
            f"封板资金合计约 {total_seal / 1e8:.0f} 亿"
        )
        return DimensionResult(
            key="breadth",
            title="市场宽度（涨停视角）",
            summary=summary,
            tables=[
                {"title": "连板天梯", "columns": ["连板数", "涨停家数", "代表个股"], "rows": ladder_rows},
                {
                    "title": "涨停明细",
                    "columns": [
                        "序号", "名称", "代码", "连板", "涨跌幅%", "所属行业",
                        "首次封板", "封板资金(亿)", "成交额(亿)", "流通市值(亿)",
                        "换手率%", "炸板次数", "涨停统计",
                    ],
                    "rows": detail_rows,
                },
            ],
            data={"limit_up": up, "max_board": max_board},
        )
