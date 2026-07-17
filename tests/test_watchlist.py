"""分组 CRUD 冒烟测试（内存 SQLite，无需网络）。"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from stock_review.models.orm import Base
from stock_review.schemas.dto import GroupCreate
from stock_review.services.watchlist import WatchlistService


def _make_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_group_crud():
    db = _make_session()
    svc = WatchlistService(db)

    # 增
    g = svc.create_group(
        GroupCreate(name="强势股", category="strategy_pool", items=[{"code": "600000", "name": "浦发银行", "weight": 1.0}])
    )
    assert g.size == 1

    # 查
    assert svc.list_groups()[0].name == "强势股"
    assert svc.get_group("强势股").items[0].code == "600000"

    # 改（全量替换成员）
    svc.update_group("强势股", GroupCreate(name="强势股", items=[{"code": "000001", "name": "平安银行"}]))
    assert svc.get_group("强势股").size == 1
    assert svc.get_group("强势股").items[0].code == "000001"

    # 删
    svc.delete_group("强势股")
    assert svc.list_groups() == []


def test_duplicate_group_rejected():
    db = _make_session()
    svc = WatchlistService(db)
    svc.create_group(GroupCreate(name="dup"))
    try:
        svc.create_group(GroupCreate(name="dup"))
        raise AssertionError("重复分组应被拒绝")
    except ValueError:
        pass
