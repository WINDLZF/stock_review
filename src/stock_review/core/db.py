"""数据库会话管理：SQLAlchemy 2.0。

默认 SQLite（零配置，Mac 双击即跑）；切 Postgres 只改 SR_DB_URL。
注意：SQLite 文件路径父目录在此处自动创建，避免运行时报找不到文件。
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()
_url = _settings.db_url

if _url.startswith("sqlite"):
    m = re.search(r"sqlite:///(?:\./)?(.+)", _url)
    if m:
        Path(m.group(1)).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(_url, future=True, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（首次运行调用）。"""
    from stock_review.models.orm import Base

    Base.metadata.create_all(engine)
