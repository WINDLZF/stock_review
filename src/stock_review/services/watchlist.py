"""自选股/分组服务：CRUD 用例。

分组带语义元数据（signal/weight/note），是"专业分组"的落点。回写同花顺走 sync_group。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from stock_review.domain.entities import Group
from stock_review.domain.ports import SyncResult
from stock_review.models.orm import GroupItemORM, GroupORM
from stock_review.schemas.dto import GroupCreate, GroupItemRead, GroupRead


class WatchlistService:
    def __init__(self, db: Session):
        self.db = db

    # ── 增 ──
    def create_group(self, payload: GroupCreate) -> GroupRead:
        if self.db.execute(
            select(GroupORM).where(GroupORM.name == payload.name)
        ).scalar_one_or_none():
            raise ValueError(f"分组已存在: {payload.name}")
        g = GroupORM(
            name=payload.name,
            theme=payload.theme,
            category=payload.category,
            source=payload.source,
            is_st_group=payload.is_st_group,
            sep_code=payload.sep_code,
            sep_name=payload.sep_name,
            ths_group_id=payload.ths_group_id,
            created_at=date.today(),
            extra=payload.extra,
            items=[
                GroupItemORM(
                    code=i.code,
                    name=i.name,
                    exchange=i.exchange,
                    order=i.order,
                    note=i.note,
                    signal=i.signal,
                    weight=i.weight,
                    extra=i.extra,
                )
                for i in payload.items
            ],
        )
        self.db.add(g)
        self.db.commit()
        self.db.refresh(g)
        return self._to_read(g)

    # ── 查 ──
    def list_groups(self) -> list[GroupRead]:
        rows = self.db.execute(select(GroupORM).order_by(GroupORM.name)).scalars().all()
        return [self._to_read(r) for r in rows]

    def get_group(self, name: str) -> GroupRead:
        g = self._must(name)
        return self._to_read(g)

    # ── 改（全量替换成员，防封号推荐）──
    def update_group(self, name: str, payload: GroupCreate) -> GroupRead:
        g = self._must(name)
        g.theme = payload.theme
        g.category = payload.category
        g.source = payload.source
        g.is_st_group = payload.is_st_group
        g.sep_code = payload.sep_code
        g.sep_name = payload.sep_name
        g.ths_group_id = payload.ths_group_id
        g.extra = payload.extra
        self.db.execute(delete(GroupItemORM).where(GroupItemORM.group_id == g.id))
        self.db.flush()
        g.items = [
            GroupItemORM(
                code=i.code,
                name=i.name,
                exchange=i.exchange,
                order=i.order,
                note=i.note,
                signal=i.signal,
                weight=i.weight,
                extra=i.extra,
            )
            for i in payload.items
        ]
        self.db.commit()
        self.db.refresh(g)
        return self._to_read(g)

    # ── 删 ──
    def delete_group(self, name: str) -> None:
        g = self._must(name)
        self.db.delete(g)
        self.db.commit()

    # ── 回写同花顺（操作闭环）──
    def sync_group(self, name: str) -> SyncResult:
        from stock_review.adapters.ths import build_sync  # noqa: PLC0415

        g = self._must(name)
        domain: Group = __import__(
            "stock_review.services.mappers", fromlist=["orm_to_domain_group"]
        ).orm_to_domain_group(g)
        result = build_sync().sync_group(domain, replace=True)
        if result.ok and result.detail and isinstance(result.detail, dict) and "id" in result.detail:
            g.ths_group_id = str(result.detail["id"])
            self.db.commit()
        return result

    # ── 内部 ──
    def _must(self, name: str) -> GroupORM:
        g = self.db.execute(
            select(GroupORM).where(GroupORM.name == name)
        ).scalar_one_or_none()
        if g is None:
            raise ValueError(f"分组不存在: {name}")
        return g

    @staticmethod
    def _to_read(g: GroupORM) -> GroupRead:
        return GroupRead(
            id=g.id,
            name=g.name,
            theme=g.theme,
            category=g.category,
            source=g.source,
            is_st_group=g.is_st_group,
            sep_code=g.sep_code,
            sep_name=g.sep_name,
            ths_group_id=g.ths_group_id,
            created_at=g.created_at,
            size=len(g.items),
            items=[
                GroupItemRead(
                    id=i.id,
                    group_id=i.group_id,
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
            extra=g.extra or {},
        )
