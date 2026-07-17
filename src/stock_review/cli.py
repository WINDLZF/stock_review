"""命令行入口（Typer）。

常用：
  stock-review initdb           # 建表
  stock-review run              # 启动 HTTP 服务（默认 :8000）
  stock-review sync <分组名>     # 回写同花顺
"""
from __future__ import annotations

import typer

from stock_review.core.db import SessionLocal, init_db
from stock_review.core.logging import setup_logging

app = typer.Typer(help="A股复盘服务 CLI", no_args_is_help=True)


@app.command()
def initdb() -> None:
    """初始化数据库（建表）。"""
    init_db()
    typer.echo("数据库已初始化")


@app.command()
def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动 HTTP 服务。"""
    import uvicorn  # noqa: PLC0415

    setup_logging()
    init_db()
    uvicorn.run("stock_review.app.main:app", host=host, port=port, reload=False)


@app.command()
def sync(group: str) -> None:
    """把指定分组回写到同花顺。"""
    init_db()
    db = SessionLocal()
    try:
        from stock_review.services.watchlist import WatchlistService

        result = WatchlistService(db).sync_group(group)
        typer.echo(result)
    finally:
        db.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
