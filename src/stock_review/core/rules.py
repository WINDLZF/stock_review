"""规则中心：所有可调阈值 / 铁律 / 权重集中到 config.yaml 的 rules: 段。

这是系统「可不断优化」的关键杠杆——调参只改 yaml，不动代码。
板块推演引擎（inference）与淘股吧校验层（validator）都从这里取参数。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from stock_review.core.config import get_settings

Severity = Literal["high", "medium", "low"]


@dataclass
class IronLaw:
    """一条淘股吧铁律：id / 名称 / 触发规则(人类可读) / 严重度 / 是否启用。"""

    id: str
    name: str
    rule: str
    severity: Severity
    enabled: bool = True


@dataclass
class InferenceParams:
    """板块推演引擎的可调参数。"""

    emotion_high: int  # 情绪周期值 ≥ 此 视为高潮
    emotion_low: int  # ≤ 此 视为冰点
    confuse_band: tuple[int, int]  # 分歧区 [下, 上]
    space_watch_boards: int  # 空间板连板数 ≥ 此 关注断板风险
    mainline_min_seal_ratio: float  # 主线封板资金占全市场比阈值


def get_rules() -> dict[str, Any]:
    """原始 rules 段（需要自定义结构时直接用）。"""
    return get_settings().rules


def iron_laws() -> list[IronLaw]:
    """返回所有「启用」的铁律（按严重度 high→low 排序）。"""
    out: list[IronLaw] = []
    for item in get_rules().get("validator", []) or []:
        out.append(
            IronLaw(
                id=item.get("id", ""),
                name=item.get("name", ""),
                rule=item.get("rule", ""),
                severity=item.get("severity", "medium"),
                enabled=bool(item.get("enabled", True)),
            )
        )
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted((l for l in out if l.enabled), key=lambda x: order.get(x.severity, 1))


def inference_params() -> InferenceParams:
    """板块推演引擎参数（带默认值，缺配也能跑）。"""
    cfg = get_rules().get("inference", {}) or {}
    band = cfg.get("confuse_band", [40, 60])
    return InferenceParams(
        emotion_high=cfg.get("emotion_high", 70),
        emotion_low=cfg.get("emotion_low", 30),
        confuse_band=(int(band[0]), int(band[1])),
        space_watch_boards=cfg.get("space_watch_boards", 5),
        mainline_min_seal_ratio=float(cfg.get("mainline_min_seal_ratio", 0.25)),
    )
