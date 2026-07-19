"""涨停复盘引擎：通过 MarketDataSource 端口接入任意平台。

设计原则：
  - 数据源通过 @source_registry 注册，主题配置为纯数据，引擎负责编排
  - 题材分类规则来自 theme_config.py（用户知识库），不可照搬但可引用
  - 族群聚合用于前端展示，排序规则可配置
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from stock_review.domain.entities import Stock
from stock_review.services.theme_config import (
    FAMILIES, KP_THEME_MAP, SECTOR_THEMES,
    THEME_FAMILY, THEME_PRIORITY,
)


def _best_theme(stock: Stock) -> str:
    """判定单只股票归属题材。

    优先级：reason 关键词 > tags 映射 > 兜底"其他"
    """
    text = f"{stock.reason or ''} {' '.join(stock.tags or [])}"

    for theme, cfg in SECTOR_THEMES.items():
        if any(kw in text for kw in cfg["keywords"]):
            return theme

    best, best_pri = "", 0
    for tag in (stock.tags or []):
        mapped = KP_THEME_MAP.get(tag, "")
        if mapped and mapped not in ("业绩", "重组", "摘帽"):
            pri = THEME_PRIORITY.get(mapped, 0)
            if pri > best_pri:
                best, best_pri = mapped, pri
    return best or "其他"


def _sort_stocks(items: list[dict]) -> list[dict]:
    """组内排序：连板降序 → 封板时间升序。"""
    return sorted(items, key=lambda s: (-s.get("boards", 0), s.get("limit_up_time", "99:99:99")))


def _stock_dict(s: Stock) -> dict[str, Any]:
    return {
        "code": s.code, "name": s.name, "exchange": s.exchange.value,
        "boards": s.boards, "limit_type": s.limit_type.value,
        "limit_up_time": s.limit_up_time, "reason": s.reason,
        "theme": s.theme, "tags": s.tags or [],
        "is_st": s.is_st, "extra": s.extra,
    }


def build(records: list[Stock], trade_date: date | str | None = None) -> dict[str, Any]:
    """输入涨停股列表，输出完整复盘报告。

    records 可由任意实现了 MarketDataSource.get_limit_up_pool() 的源产生，
    不绑定特定平台。
    """
    td = str(trade_date) if trade_date else ""
    stocks = list(records)

    # 分类
    for s in stocks:
        s.theme = _best_theme(s)

    normal = [s for s in stocks if not s.is_st]
    st_list = [s for s in stocks if s.is_st]

    # 分组
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in normal:
        groups[s.theme or "其他"].append(_stock_dict(s))
    if st_list:
        groups["ST板块"] = [_stock_dict(s) for s in st_list]

    # 族群聚合排序
    family_map: dict[str, list[dict]] = defaultdict(list)
    orphans: list[dict] = []
    st_group = None

    for theme, members in groups.items():
        fam = THEME_FAMILY.get(theme, "")
        item = {
            "name": theme,
            "stocks": _sort_stocks(members),
            "count": len(members),
            "family": fam or "其他",
        }
        if theme == "ST板块":
            item["family"] = "ST板块"
            st_group = item
        elif fam:
            family_map[fam].append(item)
        else:
            orphans.append(item)

    fam_order = list(FAMILIES.keys())
    for fam in family_map:
        family_map[fam].sort(key=lambda t: -t["count"])
    orphans.sort(key=lambda t: -t["count"])

    topics = []
    for fam in fam_order:
        if fam in family_map:
            topics.extend(family_map[fam])
    topics.extend(orphans)
    if st_group:
        topics.append(st_group)

    all_stocks = _sort_stocks([_stock_dict(s) for s in stocks])
    boards = [s.boards for s in stocks]
    first = sum(1 for b in boards if b == 1)

    # 连板梯队
    tiers: dict[int, list] = defaultdict(list)
    for s in all_stocks:
        tiers[s["boards"]].append(s)

    # 族群视图（带主题列表）
    families_view = {}
    for fam in fam_order:
        if fam in family_map:
            families_view[fam] = {
                "topics": [{"name": t["name"], "count": t["count"],
                            "stocks": t["stocks"]} for t in family_map[fam]],
                "total": sum(t["count"] for t in family_map[fam]),
            }

    if orphans:
        families_view["其他"] = {
            "topics": [{"name": t["name"], "count": t["count"],
                        "stocks": t["stocks"]} for t in orphans],
            "total": sum(t["count"] for t in orphans),
        }

    return {
        "trade_date": td,
        "summary": {
            "total": len(stocks), "first_board": first,
            "multi_board": len(stocks) - first - len(st_list),
            "max_board": max(boards) if boards else 0,
            "st": len(st_list), "theme_count": len(groups),
        },
        "board_tiers": {str(k): v for k, v in sorted(tiers.items(), key=lambda x: -x[0])},
        "families": families_view,
        "topics": topics,
        "stocks": all_stocks,
    }
