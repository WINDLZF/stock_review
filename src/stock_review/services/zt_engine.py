"""涨停复盘引擎：通过 MarketDataSource 端口接入任意平台。

设计原则：
  - 数据源通过 @source_registry 注册，主题配置为纯数据，引擎负责编排
  - 题材分类规则来自 theme_config.py（用户知识库）
  - 族群聚合用于前端展示，排序/分组规则见下方

排序规则（用户设计，先分类再排序）：
  1) 涨停排序：涨停幅度 30cm>20cm>10cm → 连板数 N 降序 → 跨度天数 M 升序 → 封板时间升序
  2) 非涨停排序：strength = 0.5*今日涨幅 + 0.3*近5日 + 0.2*近10日，降序
  3) 题材/分组内部：涨停股用涨停排序、非涨停股用非涨停排序，涨停在前

分组规则（题材内再分小组，分隔符按用户优先级）：
  最近异动 > 最近多板 > 强势股 > 大盘股 > 科创板 > 创业板 > 北交所 > 最近热股 > (其他兜底)
  「待淘汰」为独立尾部组（炸板/末端连板风险），命中票额外进入，不与主组互斥。
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

# 大盘股：流通市值阈值（元），akshare 的 float_mv 单位元 → 200 亿
BIG_MV = 2e10
# 强势股：非连板但近 10 日涨幅阈值（%）
STRONG_10D = 20.0

# 题材内主分组分隔符优先级（待淘汰单独处理）
GROUP_SEP_ORDER = [
    "最近异动", "最近多板", "强势股", "大盘股",
    "科创板", "创业板", "北交所", "最近热股",
]
GROUP_SEP_ALL = GROUP_SEP_ORDER + ["其他"]


def _best_theme(stock: Stock) -> str:
    """判定单只股票归属题材（公告优先）。

    优先级：公告催化关键词 > reason 关键词 > tags 映射 > 兜底"其他"。
    """
    text = f"{stock.reason or ''} {' '.join(stock.tags or [])}"
    # 公告优先：业绩/中标/重组等公告驱动的票优先聚到「公告催化」
    if any(kw in text for kw in SECTOR_THEMES["公告催化"]["keywords"]):
        return "公告催化"

    for theme, cfg in SECTOR_THEMES.items():
        if theme == "公告催化":
            continue
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


def _is_limit_up(s: dict | Stock) -> bool:
    chg = s.get("change_pct", 0.0) if isinstance(s, dict) else s.change_pct
    return (chg or 0.0) >= 9.5


def _time_int(t: str) -> int:
    """'09:35:12' → 93512；异常 → 999999（排最后）。"""
    if not t:
        return 999999
    digits = "".join(ch for ch in t if ch.isdigit())
    return int(digits) if digits else 999999


def _strength(d: dict) -> float:
    """非涨停排序 func：今日/近5日/近10日 加权。"""
    return 0.5 * (d.get("change_pct", 0.0) or 0.0) \
        + 0.3 * (d.get("chg_5d", 0.0) or 0.0) \
        + 0.2 * (d.get("chg_10d", 0.0) or 0.0)


def _limit_up_key(d: dict) -> tuple:
    """涨停排序键：30>20>10、N降序、M升序、时间升序。"""
    return (
        -(d.get("limit_pct", 10) or 10),
        -(d.get("boards", 1) or 1),
        d.get("days", 1) or 1,
        _time_int(d.get("limit_up_time", "")),
    )


def _non_limit_key(d: dict) -> float:
    """非涨停排序键（降序用负号）。"""
    return -_strength(d)


def _sort_group(items: list[dict]) -> list[dict]:
    """组内排序：涨停股用涨停排序、非涨停股用非涨停排序，涨停在前。"""
    limit = [d for d in items if _is_limit_up(d)]
    non = [d for d in items if not _is_limit_up(d)]
    limit.sort(key=_limit_up_key)
    non.sort(key=_non_limit_key)
    return limit + non


def _stock_dict(s: Stock) -> dict[str, Any]:
    return {
        "code": s.code, "name": s.name, "exchange": s.exchange.value,
        "boards": s.boards, "days": s.days, "limit_pct": s.limit_pct,
        "limit_type": s.limit_type.value,
        "limit_up_time": s.limit_up_time, "open_times": s.open_times,
        "reason": s.reason, "theme": s.theme, "tags": s.tags or [],
        "is_st": s.is_st,
        "change_pct": s.change_pct, "chg_5d": s.chg_5d, "chg_10d": s.chg_10d,
        "group_seps": s.group_seps or [],
        "extra": s.extra,
    }


# ── 小组分隔符判定 ──
def _matches_sep(sep: str, s: Stock, ctx: dict) -> bool:
    if sep == "最近异动":
        return s.code in ctx.get("yidong_codes", set())
    if sep == "最近多板":
        return s.boards >= 2
    if sep == "强势股":
        return s.boards < 2 and (s.chg_10d or 0.0) >= STRONG_10D
    if sep == "大盘股":
        return (s.extra.get("float_mv") or 0.0) >= BIG_MV
    if sep == "科创板":
        return s.limit_pct == 20 and s.code.startswith(("688", "689"))
    if sep == "创业板":
        return s.limit_pct == 20 and s.code.startswith(("300", "301"))
    if sep == "北交所":
        return s.limit_pct == 30
    if sep == "最近热股":
        return s.code in ctx.get("hot_codes", set())
    return False


def _is_eliminate(s: Stock) -> bool:
    """待淘汰：炸板过的票（连板不稳），作为风险尾部组。"""
    return (s.open_times or 0) > 0


def _assign_group_seps(s: Stock, ctx: dict) -> list[str]:
    """收集该票命中的所有分隔符（用于明细标签 + 主分组 + 待淘汰）。"""
    seps: list[str] = []
    for sep in GROUP_SEP_ORDER:
        if _matches_sep(sep, s, ctx):
            seps.append(sep)
    if _is_eliminate(s):
        seps.append("待淘汰")
    return seps


def _main_sep(s: Stock, ctx: dict) -> str:
    """主分组：按优先级取第一个命中的分隔符，未命中则「其他」。"""
    for sep in GROUP_SEP_ORDER:
        if _matches_sep(sep, s, ctx):
            return sep
    return "其他"


def build(
    records: list[Stock],
    trade_date: date | str | None = None,
    group_ctx: dict | None = None,
) -> dict[str, Any]:
    """输入涨停股列表，输出完整复盘报告。

    records 可由任意实现了 MarketDataSource.get_limit_up_pool() 的源产生。
    group_ctx: 可选 {yidong_codes:set, hot_codes:set}，用于「最近异动/最近热股」分组。
    """
    td = str(trade_date) if trade_date else ""
    ctx = group_ctx or {}
    stocks = list(records)

    # 分类（公告优先）
    for s in stocks:
        s.theme = _best_theme(s)
        s.group_seps = _assign_group_seps(s, ctx)

    normal = [s for s in stocks if not s.is_st]
    st_list = [s for s in stocks if s.is_st]

    # 分组（按题材）
    groups: dict[str, list[Stock]] = defaultdict(list)
    for s in normal:
        groups[s.theme or "其他"].append(s)
    if st_list:
        groups["ST板块"] = st_list

    # 族群聚合
    family_map: dict[str, list[dict]] = defaultdict(list)
    orphans: list[dict] = []
    st_group = None

    for theme, members in groups.items():
        fam = THEME_FAMILY.get(theme, "")
        # 题材内小组分隔
        gmap = {sep: [] for sep in GROUP_SEP_ALL}
        eliminate: list[dict] = []
        for s in members:
            sd = _stock_dict(s)
            sep = _main_sep(s, ctx)
            gmap[sep].append(sd)
            if _is_eliminate(s):
                eliminate.append(sd)
        if eliminate:
            gmap["待淘汰"] = eliminate

        topic_groups = []
        for sep in GROUP_SEP_ALL + (["待淘汰"] if eliminate else []):
            lst = gmap.get(sep)
            if lst:
                topic_groups.append({"sep": sep, "stocks": _sort_group(lst)})

        item = {
            "name": theme,
            "stocks": _sort_group([_stock_dict(s) for s in members]),
            "groups": topic_groups,
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

    all_stocks = _sort_group([_stock_dict(s) for s in stocks])
    boards = [s.boards for s in stocks]
    first = sum(1 for b in boards if b == 1)

    # 连板梯队（按 N 降序）
    tiers: dict[int, list] = defaultdict(list)
    for s in all_stocks:
        tiers[s["boards"]].append(s)

    families_view = {}
    for fam in fam_order:
        if fam in family_map:
            families_view[fam] = {
                "topics": [{"name": t["name"], "count": t["count"],
                            "stocks": t["stocks"], "groups": t["groups"]}
                           for t in family_map[fam]],
                "total": sum(t["count"] for t in family_map[fam]),
            }
    if orphans:
        families_view["其他"] = {
            "topics": [{"name": t["name"], "count": t["count"],
                        "stocks": t["stocks"], "groups": t["groups"]}
                       for t in orphans],
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
