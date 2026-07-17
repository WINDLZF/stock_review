"""组合仓储：实时优先、失败回退离线（对应"实时/离线数据扩展"端口）。

- mode=realtime_preferred：先问数据源，成功后写入缓存；失败回退离线缓存。
- mode=offline_only：只读缓存（无网络/保护 API 时使用）。
写入缓存由本类统一负责，保证"抓一次、多处复用"。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from stock_review.core.config import get_settings
from stock_review.domain.entities import Bar, Stock
from stock_review.domain.ports import MarketDataRepository, MarketDataSource
from stock_review.models.orm import BarCacheORM


class CompositeRepository:
    def __init__(self, source: MarketDataSource | None, db: Session, *, mode: str | None = None):
        self.source = source
        self.db = db
        self.mode = mode or get_settings().plugins.repository_mode

    # ── 日K线 ──
    def get_bars(
        self, code: str, start: date, end: date, *, realtime: bool = False
    ) -> list[Bar]:
        want_realtime = realtime or self.mode == "realtime_preferred"
        if want_realtime:
            if self.source is None:
                raise RuntimeError("未配置可用数据源；离线模式请设 repository_mode=offline_only")
            try:
                bars = self.source.get_daily_bars(code, start, end)
                self._save_bars(code, bars)
                return bars
            except Exception:
                if self.mode == "offline_only":
                    raise
                # 实时失败 → 回退离线
        return self._read_bars(code, start, end)

    def get_realtime(self, codes: list[str]) -> Any:
        if self.source is None:
            raise RuntimeError("未配置可用数据源，无法获取实时行情")
        return self.source.get_realtime_quotes(codes)

    def get_limit_up_pool(self, trade_date: date, *, realtime: bool = False) -> list[Stock]:
        want_realtime = realtime or self.mode == "realtime_preferred"
        if want_realtime:
            if self.source is None:
                raise RuntimeError("未配置可用数据源，无法获取涨停池")
            try:
                return self.source.get_limit_up_pool(trade_date)
            except Exception:
                if self.mode == "offline_only":
                    raise
        raise NotImplementedError("涨停池无离线缓存，请切 realtime_preferred 模式")

    # ── 内部：缓存读写 ──
    def _save_bars(self, code: str, bars: list[Bar]) -> None:
        for b in bars:
            self.db.merge(
                BarCacheORM(
                    code=code,
                    date=b.date,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    amount=b.amount,
                )
            )
        self.db.commit()

    def _read_bars(self, code: str, start: date, end: date) -> list[Bar]:
        from stock_review.adapters.repository.offline import OfflineRepository

        return OfflineRepository(self.db).get_bars(code, start, end)
