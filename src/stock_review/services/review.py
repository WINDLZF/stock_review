"""复盘服务：编排各分析维度，产出结构化复盘报告。

- 标的可来自分组（离线可用）或涨停池（需实时数据源）。
- 维度由 config.yaml 驱动、注册表自动发现，新增维度零侵入。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from stock_review.adapters.dimension.bootstrap import ensure_dimensions
from stock_review.adapters.repository.composite import CompositeRepository
from stock_review.core.config import get_settings
from stock_review.core.registry import dimension_registry
from stock_review.domain.entities import LimitType, Stock
from stock_review.domain.ports import ReviewContext
from stock_review.schemas.dto import DimensionResultDTO, ReviewReportDTO
from stock_review.services.watchlist import WatchlistService


def latest_trading_day() -> date:
    """推断最近交易日：周末回退到周五；节假日靠数据源返回空来体现。"""
    d = date.today()
    while d.weekday() >= 5:  # 5=周六 6=周日
        d -= timedelta(days=1)
    return d


class ReviewService:
    def __init__(self, db: Session):
        self.db = db

    def run_review(self, trade_date: date | None = None, group_name: str | None = None) -> ReviewReportDTO:
        if trade_date is None:
            trade_date = latest_trading_day()
        ensure_dimensions()
        s = get_settings()

        # 数据源缺失时退化为 None（离线模式仍可用）
        source = None
        try:
            from stock_review.adapters.datasource.factory import first_source  # noqa: PLC0415

            source = first_source()
        except Exception:  # noqa: BLE001
            source = None

        repo = CompositeRepository(source, self.db, mode=s.plugins.repository_mode)

        # 标的选择：指定分组（离线可用）或涨停池（需实时）
        if group_name:
            g = WatchlistService(self.db).get_group(group_name)
            stocks = []
            for i in g.items:
                ex = i.extra or {}
                lt_raw = ex.get("limit_type", "")
                try:
                    limit_type = LimitType(lt_raw)
                except ValueError:
                    limit_type = LimitType.NONE
                stocks.append(
                    Stock(
                        code=i.code,
                        name=i.name,
                        price=float(ex.get("price", 0.0)),
                        change_pct=float(ex.get("change_pct", 0.0)),
                        boards=int(ex.get("boards", 1)),
                        reason=ex.get("reason", "") or i.note,
                        limit_type=limit_type,
                        theme=ex.get("theme", ""),
                        tags=ex.get("tags", []),
                    )
                )
        else:
            stocks = repo.get_limit_up_pool(trade_date)

        ctx = ReviewContext(trade_date=trade_date, stocks=stocks, repository=repo)

        results: list[DimensionResultDTO] = []
        for name in s.plugins.dimensions:
            try:
                dim = dimension_registry.get(name)()
                r = dim.compute(ctx)
                results.append(
                    DimensionResultDTO(
                        key=r.key, title=r.title, summary=r.summary, data=r.data, tables=r.tables
                    )
                )
            except Exception as e:  # noqa: BLE001
                results.append(
                    DimensionResultDTO(key=name, title=name, summary=f"维度计算失败: {e}")
                )

        return ReviewReportDTO(
            trade_date=trade_date, dimensions=results, generated_at=datetime.now()
        )
