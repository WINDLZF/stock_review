"""生成演示数据：合成通达信行情 + 演示复盘分组（仅供本地预览）。

用法：
    python scripts/seed_demo_tdx.py
    SR_TDX_VIPDOC_PATH=./demo_vipdoc 再启动服务，即可在复盘页看到完整报告

- 行情：仅用标准库写入 ./demo_vipdoc，固定随机种子可复现。
- 分组：写入「演示池」自选分组，携带连板/涨幅/涨停原因，使 /api/review 离线可出内容。
"""
from __future__ import annotations

import random
import struct
import sys
from datetime import date, timedelta
from pathlib import Path

# 让脚本在仓库任意位置均可导入 src 下的包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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

# 演示池：连板高度 + 当日涨幅 + 涨停原因（合成，仅用于预览复盘报告形态）
DEMO_POOL = [
    ("sh600519", "贵州茅台", 5, 10.0, "一字板", "白酒龙头，中报超预期+机构回补"),
    ("sz000858", "五粮液", 3, 10.0, "换手板", "次高端复苏，北向连续净买入"),
    ("sh601318", "中国平安", 3, 9.8, "换手板", "保险负债端改善，权益市场回暖"),
    ("sz300750", "宁德时代", 2, 10.0, "T字板", "固态电池量产进展，出海订单落地"),
    ("sh600036", "招商银行", 2, 9.7, "换手板", "息差企稳，高股息避险属性"),
    ("sz000001", "平安银行", 1, 10.0, "", "银行板块轮动补涨"),
    ("sh600000", "浦发银行", 1, 10.0, "", "低估值+高分红，资金避险"),
    ("bj830799", "艾融软件", 1, 10.0, "", "北交所流动性改善，金融IT题材"),
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


def seed_group() -> None:
    """写入「演示池」分组（依赖已安装的业务依赖；缺失则跳过并打印提示）。"""
    try:
        from stock_review.core.db import SessionLocal
        from stock_review.schemas.dto import GroupCreate
        from stock_review.services.watchlist import WatchlistService
    except Exception as e:  # noqa: BLE001
        print(f"[跳过] 演示分组写入失败（缺少依赖？）：{e}")
        return

    db = SessionLocal()
    try:
        svc = WatchlistService(db)
        try:
            svc.get_group("演示池")
            print("[分组] 「演示池」已存在，跳过写入")
            return
        except ValueError:
            pass
        items = [
            {
                "code": code,
                "name": name,
                "note": reason,
                "extra": {
                    "boards": boards,
                    "change_pct": change,
                    "limit_type": limit_type,
                    "reason": reason,
                    "theme": "演示",
                },
            }
            for (code, name, boards, change, limit_type, reason) in DEMO_POOL
        ]
        svc.create_group(
            GroupCreate(
                name="演示池",
                theme="复盘演示",
                category="watchlist",
                source="demo",
                items=items,
            )
        )
        print(f"[分组] 已写入「演示池」（{len(items)} 只）")
    finally:
        db.close()


def main() -> None:
    print(f"写入演示行情目录: {OUT.resolve()}")
    for code, name, base in STOCKS:
        p = _make_day(code, base)
        print(f"  {code} {name:6s} -> {p}")
    print("完成行情生成。")
    seed_group()
    print("\n下一步：启动服务前设置 SR_TDX_VIPDOC_PATH=./demo_vipdoc，打开 / 即复盘页")


if __name__ == "__main__":
    main()
