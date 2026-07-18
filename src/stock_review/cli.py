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


@app.command()
def login(
    platform: str = typer.Argument("ths", help="平台：ths(同花顺)/kpl(开盘啦)/dxr(短线侠)"),
    ttl: int = typer.Option(0, "--ttl", help="cookie 有效期秒，0=不强制过期（会话级 cookie 建议设 86400）"),
) -> None:
    """登录平台并持久化 cookie（解决『每天重写登录模块』：过期只需重跑本命令）。"""
    from stock_review.core.auth import LoginManager

    mgr = LoginManager()
    cookies = mgr.ensure(platform, interactive=True, ttl=ttl)
    if cookies:
        typer.echo(f"[{platform}] 登录成功，已持久化 {len(cookies)} 个 cookie 到 .secrets/{platform}.json")
    else:
        typer.echo(f"[{platform}] 登录失败，未获取到 cookie", err=True)
        raise typer.Exit(code=1)


@app.command()
def logout(
    platform: str = typer.Argument("ths", help="平台：ths/kpl/dxr"),
) -> None:
    """清除指定平台的持久化 cookie（下次操作会要求重新登录）。"""
    from stock_review.core.auth import LoginManager

    LoginManager().forget(platform)
    typer.echo(f"[{platform}] 已清除持久化 cookie")


@app.command()
def bars(
    code: str = typer.Argument(..., help="股票代码，如 600000 或 sh600000"),
    source: str = typer.Option("", "--source", "-s", help="数据源名，默认用配置中第一个"),
    start: str = typer.Option("20240101", "--start", help="起始日期 YYYYMMDD"),
    end: str = typer.Option("20241231", "--end", help="结束日期 YYYYMMDD"),
) -> None:
    """从数据源读取日K线并打印前若干根（验证数据流程）。"""
    from datetime import datetime as _dt

    from stock_review.adapters.datasource.factory import build_enabled_sources, build_source

    src = build_source(source) if source else build_enabled_sources()[0]
    start_d = _dt.strptime(start, "%Y%m%d").date()
    end_d = _dt.strptime(end, "%Y%m%d").date()
    bs = src.get_daily_bars(code, start_d, end_d)
    typer.echo(f"数据源={src.name} 共 {len(bs)} 根K线（{code}）")
    for b in bs[:5]:
        typer.echo(
            f"  {b.date.date()} O={b.open:.2f} H={b.high:.2f} "
            f"L={b.low:.2f} C={b.close:.2f} V={b.volume:.0f} A={b.amount:.0f}"
        )
    if len(bs) > 5:
        typer.echo(f"  ... 其余 {len(bs) - 5} 根")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
