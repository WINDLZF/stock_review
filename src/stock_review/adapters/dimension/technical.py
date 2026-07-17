"""板块热点维度：按 akshare 涨停池的「所属行业」聚合涨停分布。

纯展示真实数据（行业、涨停家数、封板资金、代表个股），不做指标计算；
指标计算（如行业强度评分）作为后续增强。
"""
from __future__ import annotations

from stock_review.core.registry import dimension_registry
from stock_review.domain.ports import AnalysisDimension, DimensionMeta, DimensionResult, ReviewContext


@dimension_registry.register("sector")
class SectorDimension:
    def meta(self) -> DimensionMeta:
        return DimensionMeta(key="sector", title="板块热点", description="行业涨停分布", order=5)

    def compute(self, ctx: ReviewContext) -> DimensionResult:
        pool = ctx.stocks
        if not pool:
            return DimensionResult(
                key="sector",
                title="板块热点（行业分布）",
                summary="当日无涨停数据，无法统计板块分布。",
                tables=[],
                data={"sectors": 0},
            )

        by_ind: dict[str, dict] = {}
        for st in pool:
            ind = (st.extra or {}).get("industry") or st.theme or "其他"
            d = by_ind.setdefault(ind, {"count": 0, "seal": 0.0, "names": []})
            d["count"] += 1
            d["seal"] += float((st.extra or {}).get("seal_amount", 0.0) or 0.0)
            d["names"].append(st.name)

        rows = [
            {
                "行业": ind,
                "涨停家数": d["count"],
                "封板资金(亿)": round(d["seal"] / 1e8, 1),
                "代表个股": "、".join(d["names"][:6]),
            }
            for ind, d in by_ind.items()
        ]
        rows.sort(key=lambda x: (-x["涨停家数"], -x["封板资金(亿)"]))

        top = rows[0] if rows else None
        summary = (
            f"共 {len(rows)} 个行业出现涨停"
            + (f"；最热：{top['行业']}（{top['涨停家数']} 家）" if top else "")
        )
        return DimensionResult(
            key="sector",
            title="板块热点（行业分布）",
            summary=summary,
            tables=[
                {
                    "title": "行业涨停分布",
                    "columns": ["行业", "涨停家数", "封板资金(亿)", "代表个股"],
                    "rows": rows,
                }
            ],
            data={"sectors": len(rows)},
        )
