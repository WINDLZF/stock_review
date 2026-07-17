"""对外 DTO：请求/响应按强类型定义，便于 Java 侧中台直接消费。

分组带语义元数据（signal/weight/note），对应"专业分组"需求。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ── 分组成员 ──
class GroupItemCreate(BaseModel):
    code: str
    name: str = ""
    exchange: str = ""
    order: int = 0
    note: str = ""
    signal: str = ""
    weight: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class GroupItemRead(GroupItemCreate):
    id: int
    group_id: int


# ── 分组 ──
class GroupCreate(BaseModel):
    name: str
    theme: str = ""
    category: str = "watchlist"  # watchlist | strategy_pool | sector
    source: str = ""
    is_st_group: bool = False
    sep_code: str = ""
    sep_name: str = ""
    ths_group_id: str = ""
    items: list[GroupItemCreate] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class GroupRead(BaseModel):
    id: int
    name: str
    theme: str = ""
    category: str = "watchlist"
    source: str = ""
    is_st_group: bool = False
    sep_code: str = ""
    sep_name: str = ""
    ths_group_id: str = ""
    created_at: date | None = None
    size: int = 0
    items: list[GroupItemRead] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


# ── 交易 ──
class TradeCreate(BaseModel):
    code: str
    name: str = ""
    direction: str = "BUY"  # BUY | SELL
    price: float
    qty: float
    fee: float = 0.0
    trade_dt: date
    note: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class TradeRead(TradeCreate):
    id: int

    model_config = {"from_attributes": True}


# ── 复盘笔记 ──
class ReviewNoteCreate(BaseModel):
    trade_date: date
    title: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ReviewNoteRead(ReviewNoteCreate):
    id: int

    model_config = {"from_attributes": True}


# ── 复盘维度结果 ──
class DimensionResultDTO(BaseModel):
    key: str
    title: str
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    tables: list[dict[str, Any]] = Field(default_factory=list)


class ReviewReportDTO(BaseModel):
    trade_date: date
    dimensions: list[DimensionResultDTO] = Field(default_factory=list)
    generated_at: datetime | None = None
