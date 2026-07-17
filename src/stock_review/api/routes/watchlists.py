"""分组/自选股 CRUD 与回写同花顺。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from stock_review.api.deps import get_db
from stock_review.schemas.dto import GroupCreate, GroupRead
from stock_review.services.watchlist import WatchlistService

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


@router.post("", response_model=GroupRead, status_code=201)
def create(payload: GroupCreate, db: Session = Depends(get_db)) -> GroupRead:
    try:
        return WatchlistService(db).create_group(payload)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("", response_model=list[GroupRead])
def list_groups(db: Session = Depends(get_db)) -> list[GroupRead]:
    return WatchlistService(db).list_groups()


@router.get("/{name}", response_model=GroupRead)
def get(name: str, db: Session = Depends(get_db)) -> GroupRead:
    try:
        return WatchlistService(db).get_group(name)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.put("/{name}", response_model=GroupRead)
def update(name: str, payload: GroupCreate, db: Session = Depends(get_db)) -> GroupRead:
    try:
        return WatchlistService(db).update_group(name, payload)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/{name}", status_code=204)
def delete(name: str, db: Session = Depends(get_db)) -> None:
    try:
        WatchlistService(db).delete_group(name)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/{name}/sync", summary="回写同花顺（操作闭环）")
def sync(name: str, db: Session = Depends(get_db)):
    try:
        return WatchlistService(db).sync_group(name)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
