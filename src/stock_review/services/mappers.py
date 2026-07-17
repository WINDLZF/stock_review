"""ORM <-> 领域实体 映射。"""
from __future__ import annotations

from stock_review.domain.entities import Group, GroupItem
from stock_review.models.orm import GroupItemORM, GroupORM


def orm_to_domain_group(g: GroupORM) -> Group:
    return Group(
        name=g.name,
        theme=g.theme,
        category=g.category,
        source=g.source,
        is_st_group=g.is_st_group,
        sep_code=g.sep_code,
        sep_name=g.sep_name,
        ths_group_id=g.ths_group_id,
        created_at=g.created_at,
        extra=g.extra or {},
        items=[
            GroupItem(
                code=i.code,
                name=i.name,
                exchange=i.exchange,
                order=i.order,
                note=i.note,
                signal=i.signal,
                weight=i.weight,
                extra=i.extra or {},
            )
            for i in g.items
        ],
    )
