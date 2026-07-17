"""离线仓储：只读本地缓存(BarCache)，支撑离线复盘与 API 限流保护。

所有抓取到的行情都先落 BarCache（见 CompositeRepository），本类负责读回。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_review.domain.entities import Bar, Stock
from stock_review.domain.ports import MarketDataRepository
from stock_review.models.orm import BarCacheORM


class OfflineRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_bars(
        self, code: str, start: date, end: date, *, realtime: bool = False
    ) -> list[Bar]:
        rows = (
            self.db.execute(
                select(BarCacheORM)
                .where(
                    BarCacheORM.code == code,
                    BarCacheORM.date >= start,
                    BarCacheORM.date <= end,
                )
                .order_by(BarCacheORM.date)
            )
            .scalars()
            .all()
        )
        return [
            Bar(
                date=r.date,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                amount=r.amount,
            )
            for r in rows
        ]

    def get_realtime(self, codes: list[str]) -> Any:
        raise NotImplementedError("离线模式不支持实时行情；切 realtime_preferred 模式")

    def get_limit_up_pool(self, trade_date: date, *, realtime: bool = False) -> list[Stock]:
        raise NotImplementedError("离线模式不支持涨停池；切 realtime_preferred 模式")
