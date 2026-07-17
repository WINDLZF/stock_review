"""复盘接口。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from stock_review.api.deps import get_db
from stock_review.schemas.dto import ReviewReportDTO
from stock_review.services.review import ReviewService

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("", response_model=ReviewReportDTO)
def review(
    trade_date: date = Query(..., description="复盘交易日，如 2026-07-18"),
    group: str | None = Query(None, description="指定分组名则对其成员做复盘（离线可用）"),
    db: Session = Depends(get_db),
) -> ReviewReportDTO:
    try:
        return ReviewService(db).run_review(trade_date, group_name=group)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)) from e
