"""通达信离线数据源：直接读取通达信本地 .day 行情文件，无需联网/登录。

文件结构（以默认安装目录 vipdoc 为例）：
    <vipdoc>/sh/lday/sh600000.day
    <vipdoc>/sz/lday/sz000001.day
    <vipdoc>/bj/lday/bj8xxxxx.day

每根日K线 32 字节，小端：
    date(int, YYYYMMDD) open(int,*100) high(*100) low(*100) close(*100)
    amount(float32, 元) volume(int, 股) reserved(int)

这是"离线数据源"的落地：实现 MarketDataSource 并标记 is_local=True，
仓储层据此直接读本地文件、跳过 DB 缓存。后续 cookie 类平台（同花顺/开盘啦/
短线侠）走同一端口，只是 __init__ 多带一个 cookie（由 .env 注入）。
"""
from __future__ import annotations

import struct
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_review.core.config import get_settings
from stock_review.core.registry import source_registry
from stock_review.domain.entities import Bar, Quote, Stock
from stock_review.domain.ports import MarketDataSource

_DAY_RECORD = struct.Struct("<IIIIIfII")  # 4*5 + 4(float) + 4 + 4 = 32 字节


def _parse_date(raw: int) -> datetime:
    """通达信日期整数：YYYYMMDD（新格式）或 YYMMDD（老格式），两者兼容。"""
    if raw > 19_000_000:  # 如 20240315
        return datetime.strptime(str(raw), "%Y%m%d")
    yy, mm, dd = raw // 10000, (raw // 100) % 100, raw % 100
    year = 2000 + yy if yy < 100 else yy
    return datetime(year, mm, dd)


def _parse_day_buffer(buf: bytes) -> list[Bar]:
    """解析 .day 文件二进制缓冲（不依赖真实文件，便于单测）。"""
    bars: list[Bar] = []
    for off in range(0, len(buf) - _DAY_RECORD.size + 1, _DAY_RECORD.size):
        d, o, h, l, c, amount, vol, _ = _DAY_RECORD.unpack_from(buf, off)
        bars.append(
            Bar(
                date=_parse_date(d),
                open=o / 100.0,
                high=h / 100.0,
                low=l / 100.0,
                close=c / 100.0,
                volume=float(vol),  # 单位：股
                amount=float(amount),  # 单位：元
            )
        )
    return bars


@source_registry.register("tdx")
class TdxDataSource:
    """通达信离线行情数据源。"""

    name = "tdx"
    is_local = True  # 离线本地源：仓储直接读文件，不写 DB 缓存

    def __init__(self, vipdoc_path: str | None = None):
        self.vipdoc = Path(vipdoc_path or get_settings().tdx_vipdoc_path)

    # ── 代码 → 文件路径 ──
    @staticmethod
    def _resolve_path(code: str, vipdoc: Path) -> Path:
        raw = code.strip().lower()
        for p in ("sh", "sz", "bj"):
            if raw.startswith(p):
                market, pure = p, raw[len(p):]
                break
        else:
            pure = raw
            market = (
                "sh"
                if pure.startswith("6")
                else "bj"
                if pure.startswith(("4", "8"))
                else "sz"
            )
        pure = pure.zfill(6)
        return vipdoc / market / "lday" / f"{market}{pure}.day"

    # ── MarketDataSource 接口 ──
    def get_daily_bars(self, code: str, start: date, end: date) -> list[Bar]:
        path = self._resolve_path(code, self.vipdoc)
        if not path.exists():
            raise FileNotFoundError(
                f"未找到通达信日线文件: {path}\n"
                f"请检查 SR_TDX_VIPDOC_PATH（当前: {self.vipdoc}）"
            )
        bars = _parse_day_buffer(path.read_bytes())
        return [b for b in bars if start <= b.date.date() <= end]

    def get_realtime_quotes(self, codes: list[str]) -> list[Quote]:
        raise NotImplementedError("通达信离线文件不含实时行情；请用在线数据源（如 akshare）")

    def get_limit_up_pool(self, trade_date: date) -> list[Stock]:
        raise NotImplementedError("通达信离线文件不含涨停池；请用在线数据源（如 akshare）")

    def get_money_flow(self, code: str, start: date, end: date) -> dict[str, Any]:
        raise NotImplementedError("通达信日线文件不含资金流；请用在线数据源")

    def get_fundamentals(self, code: str) -> dict[str, Any]:
        raise NotImplementedError("通达信日线文件不含基本面；请用在线数据源（如 tushare）")
