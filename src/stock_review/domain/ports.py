"""扩展端口（Protocol 契约）：系统的四大可插拔扩展点。

领域层只依赖这些抽象，具体实现在 adapters/ 下。新增任何数据源、
分析维度、回写终端，只要实现对应 Protocol 即可，无需改动核心逻辑。

四大端口：
  1. MarketDataSource    —— 数据源扩展（各平台 API / 通达信离线 / akshare）
  2. MarketDataRepository —— 离线/实时数据扩展（缓存、组合、回退）
  3. AnalysisDimension   —— 分析维度扩展（技术面/宽度/题材/资金面...）
  4. GroupSyncPort       —— 分组回写扩展（同花顺/文件导出/其他终端）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

from .entities import Bar, Group, Quote, Stock


# ═══════════════════════ 1. 数据源扩展 ═══════════════════════
@runtime_checkable
class MarketDataSource(Protocol):
    """行情/财务/资金流数据源。各平台 API、通达信离线文件都实现它。

    实现类应对不支持的能力抛 NotImplementedError，由上层仓储做能力探测/回退。
    """

    name: str

    def get_daily_bars(self, code: str, start: date, end: date) -> list[Bar]:
        """日K线。"""
        ...

    def get_realtime_quotes(self, codes: list[str]) -> list[Quote]:
        """实时快照。"""
        ...

    def get_limit_up_pool(self, trade_date: date) -> list[Stock]:
        """涨停池（复盘核心输入）。"""
        ...

    def get_money_flow(self, code: str, start: date, end: date) -> dict[str, Any]:
        """资金流。"""
        ...

    def get_fundamentals(self, code: str) -> dict[str, Any]:
        """基本面/财务快照。"""
        ...

    # ── v2 可选能力：平台「预计算」数据（取源不重算的核心）──
    # 不支持的源对这些方法抛 NotImplementedError，由上层做能力探测/回退。
    def get_precomputed_indicators(self, code: str) -> dict[str, Any]:
        """预计算技术指标（MA/MACD/RSI/KDJ/BOLL），取自同花顺/通达信/东财。

        取源不重算：优先用平台算好的；本地计算仅作离线兜底。
        """
        ...

    def get_market_sentiment(self, trade_date: date) -> dict[str, Any]:
        """市场情绪（封板率/涨停家数/跌停家数/连板梯队），取自开盘啦。"""
        ...

    def get_emotion_cycle(self, trade_date: date) -> dict[str, Any]:
        """情绪周期值 + 昨日涨停溢价率，取自短线侠。"""
        ...

    def get_limit_up_reason(self, trade_date: date) -> dict[str, Any]:
        """涨停原因 / 题材标签 / 题材强度，取自开盘啦题材库。"""
        ...

    def get_dragon_tiger(self, trade_date: date) -> list[dict[str, Any]]:
        """龙虎榜席位（机构/游资人设），取自开盘啦。"""
        ...


# ═══════════════════════ 2. 离线/实时仓储扩展 ═══════════════════════
@runtime_checkable
class MarketDataRepository(Protocol):
    """数据获取仓储：屏蔽"离线 or 实时"的差异，对上层提供统一入口。

    - OfflineRepository：只读本地缓存/数据库（离线可用）。
    - RealtimeRepository：包一层 Source 并写缓存。
    - CompositeRepository：实时优先、失败回退离线（配置切换）。
    """

    def get_bars(
        self, code: str, start: date, end: date, *, realtime: bool = False
    ) -> list[Bar]:
        ...

    def get_realtime(self, codes: list[str]) -> list[Quote]:
        ...

    def get_limit_up_pool(self, trade_date: date, *, realtime: bool = False) -> list[Stock]:
        ...


# ═══════════════════════ 3. 分析维度扩展 ═══════════════════════
@dataclass
class ReviewContext:
    """一次复盘的输入上下文，供各维度共享。"""

    trade_date: date
    stocks: list[Stock] = field(default_factory=list)  # 复盘标的（如涨停池）
    repository: MarketDataRepository | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionMeta:
    """维度元信息。"""

    key: str
    title: str
    description: str = ""
    order: int = 100  # 报告中的排序


@dataclass
class DimensionResult:
    """维度计算结果（结构化，供 API/报告渲染）。"""

    key: str
    title: str
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    tables: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class AnalysisDimension(Protocol):
    """一个复盘分析维度。注册后自动纳入复盘流程。"""

    def meta(self) -> DimensionMeta:
        ...

    def compute(self, ctx: ReviewContext) -> DimensionResult:
        ...


# ═══════════════════════ 4. 分组回写扩展 ═══════════════════════
@dataclass
class SyncResult:
    """回写结果。"""

    ok: bool
    group_name: str
    target: str = ""  # 终端标识（如 ths / file）
    detail: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


@runtime_checkable
class GroupSyncPort(Protocol):
    """把分组回写到外部终端（同花顺 / 文件导出 / 其他）。"""

    name: str

    def sync_group(self, group: Group, *, replace: bool = True) -> SyncResult:
        """回写单个分组。replace=True 时全量替换（防封号推荐）。"""
        ...

    def list_remote_groups(self) -> list[dict[str, Any]]:
        """列出远端已有分组（用于对齐/核验）。"""
        ...
