"""行情数据接口：K线、可交易标的、可用数据源。

离线源（tdx）直接读本地 .day 文件；在线源（akshare）按需联网。
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from stock_review.adapters.datasource.factory import build_enabled_sources, build_source

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/sources")
def list_sources() -> list[dict]:
    out = []
    for s in build_enabled_sources():
        out.append({"name": s.name, "is_local": getattr(s, "is_local", False)})
    return out


@router.get("/stocks")
def list_stocks(source: str = Query("tdx")) -> list[dict]:
    """列出离线源 vipdoc 下可用的日线标的（扫描 lday 目录）。"""
    try:
        src = build_source(source)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
    vipdoc = getattr(src, "vipdoc", None)
    if vipdoc is None or not Path(vipdoc).exists():
        return []
    stocks: list[dict] = []
    for market in ("sh", "sz", "bj"):
        d = Path(vipdoc) / market / "lday"
        if not d.exists():
            continue
        for f in sorted(d.glob(f"{market}*.day")):
            stocks.append({"code": f.stem, "market": market})
    return stocks


@router.get("/bars")
def bars(
    code: str = Query(..., description="股票代码，如 600000 / sh600000"),
    source: str = Query("tdx"),
    start: str = Query("", description="起始 YYYYMMDD，默认近两年"),
    end: str = Query("", description="结束 YYYYMMDD，默认今天"),
) -> list[dict]:
    try:
        src = build_source(source)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e

    end_d = date.today()
    start_d = end_d - timedelta(days=730)
    if end:
        end_d = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    if start:
        start_d = date(int(start[:4]), int(start[4:6]), int(start[6:8]))

    try:
        data = src.get_daily_bars(code, start_d, end_d)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(400, str(e)) from e

    return [
        {
            "date": b.date.strftime("%Y-%m-%d"),
            "open": round(b.open, 2),
            "high": round(b.high, 2),
            "low": round(b.low, 2),
            "close": round(b.close, 2),
            "volume": b.volume,
            "amount": b.amount,
        }
        for b in data
    ]
