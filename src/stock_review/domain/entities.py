"""领域实体：系统核心业务对象，与存储/接口无关。

借鉴 zt-review 的 ZtStock/ZtTopic 分区设计，但去掉同花顺耦合，
用 `extra` 字段保留可扩展性。市场枚举独立到 adapters/ths/market_codes。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Exchange(str, Enum):
    """交易所（与同花顺市场码解耦，回写时再映射）。"""

    SH = "SH"  # 上交所
    SZ = "SZ"  # 深交所
    BJ = "BJ"  # 北交所
    UNKNOWN = "UNKNOWN"


class LimitType(str, Enum):
    """涨停类型。"""

    NONE = ""
    ONE_WORD = "一字板"
    T_WORD = "T字板"
    TURNOVER = "换手板"


@dataclass(slots=True)
class Stock:
    """个股。分区设计：基础 / 行情 / 涨停属性 / 题材 / 扩展。"""

    code: str
    name: str = ""
    exchange: Exchange = Exchange.UNKNOWN

    # 行情区
    price: float = 0.0
    change_pct: float = 0.0

    # 涨停属性区（复盘用）
    limit_up_time: str = ""
    open_times: int = 0
    limit_type: LimitType = LimitType.NONE
    boards: int = 1  # 连板数
    reason: str = ""

    # 题材区
    theme: str = ""
    tags: list[str] = field(default_factory=list)

    # 扩展区（因子、财务等自由挂载）
    extra: dict = field(default_factory=dict)

    @property
    def is_st(self) -> bool:
        up = self.name.upper()
        return "ST" in up or "*" in self.name


@dataclass(slots=True)
class Bar:
    """K线（日/分钟通用）。"""

    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0


@dataclass(slots=True)
class Quote:
    """实时快照。"""

    code: str
    name: str
    price: float
    change_pct: float
    volume: float = 0.0
    amount: float = 0.0
    ts: datetime | None = None


@dataclass(slots=True)
class GroupItem:
    """分组成员。带语义元数据（入选逻辑/权重），这是"专业分组"的关键。"""

    code: str
    name: str = ""
    exchange: Exchange = Exchange.UNKNOWN
    order: int = 0
    note: str = ""  # 入选理由
    signal: str = ""  # 来源信号/策略
    weight: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class Group:
    """自选股分组/股票池。可回写同花顺，也可本地持久化。"""

    name: str
    items: list[GroupItem] = field(default_factory=list)
    theme: str = ""
    category: str = "watchlist"  # watchlist | strategy_pool | sector
    source: str = ""  # 由哪个策略/复盘生成
    is_st_group: bool = False
    sep_code: str = ""  # 概念分隔符（同花顺回写用）
    sep_name: str = ""
    ths_group_id: str = ""  # 关联的同花顺分组 id（回写后回填）
    created_at: date | None = None
    extra: dict = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.items)

    @property
    def display_name(self) -> str:
        return f"{self.name}({self.size}只)"


@dataclass(slots=True)
class ReviewNote:
    """复盘笔记。"""

    trade_date: date
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
</parameter>
<parameter name="explanation">创建领域实体，包含 Stock/Bar/Quote/Group/GroupItem/ReviewNote，分区设计并预留扩展，分组带语义元数据。