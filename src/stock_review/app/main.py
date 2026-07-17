"""FastAPI 应用入口：组装路由、生命周期初始化。

启动：uv run python -m stock_review.app.main 或 `stock-review run`
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from stock_review.api.routes import health, review, watchlists
from stock_review.core.db import init_db
from stock_review.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()  # 首次启动建表
    yield


app = FastAPI(title="A股复盘服务", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(watchlists.router)
app.include_router(review.router)


@app.get("/")
def root() -> dict:
    return {"service": "stock-review", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    setup_logging()
    init_db()
    uvicorn.run("stock_review.app.main:app", host="127.0.0.1", port=8000, reload=False)
