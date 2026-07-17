"""通达信 .day 解析单元测试：用合成二进制验证，不依赖真实行情文件。"""
from __future__ import annotations

import struct
from datetime import date

from stock_review.adapters.datasource.tdx_source import (
    TdxDataSource,
    _parse_date,
    _parse_day_buffer,
)

_REC = struct.Struct("<IIIIIfII")


def _make_buffer() -> bytes:
    buf = b""
    # 2024-03-15: O=100 H=110 L=95 C=105 额=1234567 量=100000
    buf += _REC.pack(20240315, 10000, 11000, 9500, 10500, 1234567.0, 100000, 0)
    # 2024-03-18: O=105 H=108 L=104 C=107 额=2345678 量=200000
    buf += _REC.pack(20240318, 10500, 10800, 10400, 10700, 2345678.0, 200000, 0)
    return buf


def test_parse_day_buffer() -> None:
    bars = _parse_day_buffer(_make_buffer())
    assert len(bars) == 2

    b0 = bars[0]
    assert b0.date.date() == date(2024, 3, 15)
    assert b0.open == 100.0
    assert b0.high == 110.0
    assert b0.low == 95.0
    assert b0.close == 105.0
    assert b0.volume == 100000
    assert b0.amount == 1234567.0

    b1 = bars[1]
    assert b1.date.date() == date(2024, 3, 18)
    assert b1.close == 107.0
    assert b1.volume == 200000


def test_parse_date_yyyymmdd() -> None:
    assert _parse_date(20240315).date() == date(2024, 3, 15)


def test_parse_date_yymmdd_fallback() -> None:
    # 老格式（6位YYMMDD）：170303 -> 2017-03-03
    assert _parse_date(170303).date() == date(2017, 3, 3)


def test_resolve_path_sh() -> None:
    from pathlib import Path

    p = TdxDataSource._resolve_path("600000", Path("/vip"))
    assert p == Path("/vip/sh/lday/sh600000.day")


def test_resolve_path_sz_with_prefix() -> None:
    from pathlib import Path

    p = TdxDataSource._resolve_path("sz000001", Path("/vip"))
    assert p == Path("/vip/sz/lday/sz000001.day")


def test_resolve_path_bj() -> None:
    from pathlib import Path

    p = TdxDataSource._resolve_path("8xxxxx", Path("/vip"))
    assert p == Path("/vip/bj/lday/bj8xxxxx.day")
