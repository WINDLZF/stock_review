"""ORM 模型：分组、成员、交易、复盘笔记、行情缓存。

设计原则：
- 业务私有数据（分组/交易/笔记）与行情缓存解耦，互不污染。
- extra 用 JSON 字段保留扩展，新增字段无需改表结构。
- 行情缓存(BarCache)支撑"离线数据"扩展点——落库即可离线复盘。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class GroupORM(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    theme: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(32), default="watchlist")
    source: Mapped[str] = mapped_column(String(64), default="")
    is_st_group: Mapped[bool] = mapped_column(default=False)
    sep_code: Mapped[str] = mapped_column(String(16), default="")
    sep_name: Mapped[str] = mapped_column(String(32), default="")
    ths_group_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[date | None] = mapped_column(Date, default=None)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    items: Mapped[list["GroupItemORM"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="GroupItemORM.order"
    )


class GroupItemORM(Base):
    __tablename__ = "group_items"
    __table_args__ = (UniqueConstraint("group_id", "code", name="uq_group_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(32), default="")
    exchange: Mapped[str] = mapped_column(String(8), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")  # 入选理由
    signal: Mapped[str] = mapped_column(String(64), default="")  # 来源信号/策略
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    group: Mapped["GroupORM"] = relationship(back_populates="items")


class TradeORM(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(32), default="")
    direction: Mapped[str] = mapped_column(String(8), default="BUY")  # BUY | SELL
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    trade_dt: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class ReviewNoteORM(Base):
    __tablename__ = "review_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class BarCacheORM(Base):
    """行情缓存（离线数据落地），复合主键 (code, date)。"""

    __tablename__ = "bar_cache"
    __table_args__ = (UniqueConstraint("code", "date", name="uq_bar_code_date"),)

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
