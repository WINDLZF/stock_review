"""生成演示用通达信 vipdoc 行情（合成数据，仅供本地预览页面）。

用法：
    python scripts/seed_demo_tdx.py            # 写入 ./demo_vipdoc
    SR_TDX_VIPDOC_PATH=./demo_vipdoc 再启动服务即可在页面看到 K 线

仅用标准库，无需安装任何依赖；数据用固定随机种子，可复现。
"""
from __future__ import annotations

import random
import struct
from datetime import date, timedelta
from pathlib import Path

# (代码含市场前缀, 名称, 起始价)
STOCKS = [
    ("sh600000", "浦发银行", 9.5),
    ("sh600036", "招商银行", 35.0),
    ("sh600519", "贵州茅台", 1680.0),
    ("sh601318", "中国平安", 48.0),
    ("sz000001", "平安银行", 11.0),
    ("sz000858", "五粮液", 150.0),
    ("sz300750", "宁德时代", 210.0),
    ("bj830799", "艾融软件", 12.0),
]

_REC = struct.Struct("<IIIIIfII")
TRADING_DAYS = 600
SEED = 20240718
OUT = Path("demo_vipdoc")


def _trading_dates(n: int) -> list[date]:
    out: list[date] = []
    d = date.today()
    while len(out) < n:
        if d.weekday() < 5:  # 跳过周末
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def _make_day(code: str, base: float) -> Path:
    market = code[:2]
    pure = code[2:]
    rng = random.Random(SEED + int(pure))
    dates = _trading_dates(TRADING_DAYS)
    out = OUT / market / "lday"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{code}.day"
    price = base
    buf = b""
    for d in dates:
        # 随机游走 + 轻微 drift
        ret = rng.gauss(0.0004, 0.018)
        open_p = price * (1 + rng.gauss(0, 0.006))
        close_p = max(0.5, open_p * (1 + ret))
        high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, 0.008)))
        low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, 0.008)))
        vol = int(rng.uniform(5e5, 5e7))
        amount = vol * (open_p + close_p) / 2
        raw = int(f"{d.year:04d}{d.month:02d}{d.day:02d}")
        buf += _REC.pack(
            raw,
            int(round(open_p * 100)),
            int(round(high_p * 100)),
            int(round(low_p * 100)),
            int(round(close_p * 100)),
            float(amount),
            vol,
            0,
        )
        price = close_p
    path.write_bytes(buf)
    return path


def main() -> None:
    print(f"写入演示行情目录: {OUT.resolve()}")
    for code, name, base in STOCKS:
        p = _make_day(code, base)
        print(f"  {code} {name:6s} -> {p}")
    print("完成。启动服务前设置 SR_TDX_VIPDOC_PATH=./demo_vipdoc")


if __name__ == "__main__":
    main()
