"""技术面维度：均线 / MACD / RSI / KDJ。

指标用 pandas 手算（不依赖 pandas-ta，减少依赖）；新增维度只需在同级加模块并
@dimension_registry.register，复盘流程自动纳入，无需改核心代码。
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from stock_review.core.registry import dimension_registry
from stock_review.domain.entities import Bar
from stock_review.domain.ports import AnalysisDimension, DimensionMeta, DimensionResult, ReviewContext


def _ma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = -delta.clip(upper=0).rolling(n).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - 100 / (1 + rs)).fillna(100)


def _macd(close: pd.Series) -> pd.Series:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    return (dif - dea) * 2  # MACD 柱


def _kdj(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    low_n = df["low"].rolling(9).min()
    high_n = df["high"].rolling(9).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, pd.NA) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


@dimension_registry.register("technical")
class TechnicalDimension:
    def meta(self) -> DimensionMeta:
        return DimensionMeta(key="technical", title="技术面", description="均线/MACD/RSI/KDJ", order=10)

    def compute(self, ctx: ReviewContext) -> DimensionResult:
        if ctx.repository is None:
            return DimensionResult(key="technical", title="技术面", summary="无数据仓储，跳过")

        end = ctx.trade_date
        start = end - timedelta(days=180)
        rows: list[dict] = []
        for st in ctx.stocks[:30]:  # 限制样本量，避免长耗时
            bars = ctx.repository.get_bars(st.code, start, end)
            if len(bars) < 30:
                continue
            df = pd.DataFrame(
                [{"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close}
                for b in bars]
            ).set_index("date")
            close = df["close"]
            ma20 = _ma(close, 20).iloc[-1]
            ma60 = _ma(close, 60).iloc[-1]
            macd = _macd(close).iloc[-1]
            rsi = _rsi(close).iloc[-1]
            k, d, j = _kdj(df)
            rows.append(
                {
                    "code": st.code,
                    "name": st.name,
                    "close": round(close.iloc[-1], 2),
                    "ma20": round(float(ma20), 2),
                    "ma60": round(float(ma60), 2),
                    "trend": "多头" if close.iloc[-1] > ma20 > ma60 else ("空头" if close.iloc[-1] < ma20 < ma60 else "震荡"),
                    "macd": round(float(macd), 3),
                    "rsi14": round(float(rsi), 1),
                    "kdj_j": round(float(j.iloc[-1]), 1),
                }
            )
        return DimensionResult(
            key="technical",
            title="技术面（近 30 只样本）",
            summary=f"已计算 {len(rows)} 只；多头排列需 close>ma20>ma60",
            tables=[{"columns": list(rows[0].keys()), "rows": rows}] if rows else [],
            data={"count": len(rows)},
        )
