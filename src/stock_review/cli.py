"""命令行入口（Typer）。

常用：
  stock-review initdb           # 建表
  stock-review run              # 启动 HTTP 服务（默认 :8000）
  stock-review sync <分组名>     # 回写同花顺
"""
from __future__ import annotations

import sys

import typer

from stock_review.core.db import SessionLocal, init_db
from stock_review.core.logging import setup_logging

# Windows 默认控制台编码为 GBK，中文接口样本打印会抛 UnicodeEncodeError。
# 强制 stdout/stderr 用 UTF-8，避免 sniff/connect 等命令在非 UTF-8 终端崩溃。
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8", "utf8mb4"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

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
    platform: str = typer.Argument("ths", help="平台：ths(同花顺) kpl(开盘啦) dxr(短线侠) taoguba(淘股吧) xueqiu(雪球) jiuyan(韭研公社)"),
    ttl: int = typer.Option(0, "--ttl", help="兜底有效期秒。0=用 cookie 自带 expires 自动判定（推荐，平台说几天就几天）"),
    timeout: int = typer.Option(600, "--timeout", help="等待自动识别登录态的上限秒；超时则抓取当前登录态收尾"),
) -> None:
    """登录平台并持久化 cookie（自动读取 cookie 真实过期时间；过期只需重跑本命令）。

    弹窗里扫码/输验证码即可；若自动未识别到登录态，会在终端提示按回车抓取。
    """
    from stock_review.core.auth import LoginManager
    from stock_review.core.auth.cookie_store import CookieStore
    from stock_review.core.auth.providers import is_accessible_platform, is_known_platform

    if not is_known_platform(platform):
        typer.echo(f"未知平台 '{platform}'，可用：", err=True)
        for r in LoginManager().list_platforms():
            typer.echo(f"  {r['name']} ({r['display']})", err=True)
        raise typer.Exit(code=2)
    if not is_accessible_platform(platform):
        reason = next(
            (r["blocked_reason"] for r in LoginManager().list_platforms()
             if r["name"] == platform),
            "该平台当前不可访问",
        )
        typer.echo(f"[{platform}] 该平台当前不可访问，已搁置：{reason}", err=True)
        raise typer.Exit(code=2)
    mgr = LoginManager()
    cookies = mgr.ensure(platform, interactive=True, ttl=ttl, timeout=timeout)
    if cookies:
        days = CookieStore(platform).ttl_seconds() // 86400
        typer.echo(
            f"[{platform}] 登录成功，已持久化 {len(cookies)} 个 cookie 到 .secrets/{platform}.json；"
            f"预计有效约 {days} 天"
        )
    else:
        typer.echo(f"[{platform}] 登录失败，未获取到 cookie", err=True)
        raise typer.Exit(code=1)


@app.command(name="login-all")
def login_all(
    timeout: int = typer.Option(1800, "--timeout", help="最大等待秒数（默认 30 分钟），超时自动抓取"),
    platforms: str = typer.Option("ths,kpl,dxr,taoguba,xueqiu", "--platforms", "-p",
                                   help="逗号分隔的平台列表（默认全部 5 个可接入平台）"),
) -> None:
    """一键登录所有平台：一个浏览器窗口多 tab，手动扫码，回车统一抓取保存。

    打开一个浏览器，为每个平台创建一个 tab。你在各 tab 逐一扫码/登录。
    全部完成后回到终端按回车，自动抓取所有平台的 cookie + localStorage 并持久化。
    不自动检测、不催促——你想登多久就多久。
    """
    from stock_review.core.auth.cookie_store import CookieStore
    import builtins as _b  # noqa: F401  # for print() in case typer shadows it
    from stock_review.core.auth.providers import get_provider, is_accessible_platform, is_known_platform

    names = [n.strip() for n in platforms.split(",") if n.strip()]
    if not names:
        print("至少指定一个平台", err=True, flush=True)
        raise typer.Exit(code=2)

    active: list[str] = []
    for n in names:
        if not is_known_platform(n):
            print(f"跳过未知平台: {n}", err=True, flush=True)
            continue
        if not is_accessible_platform(n):
            p = get_provider(n)
            print(f"[{n}] 已搁置：{p.blocked_reason}", err=True, flush=True)
            continue
        active.append(n)

    if not active:
        print("无可用的平台", err=True, flush=True)
        raise typer.Exit(code=2)

    mins = timeout // 60
    print(f"\n{'='*55}", flush=True)
    print(f"  一键登录 {len(active)} 个平台（最长 {mins} 分钟，不催你）", flush=True)
    print(f"{'='*55}", flush=True)
    for n in active:
        p = get_provider(n)
        print(f"  📌 {p.display} ({n})", flush=True)
        print(f"     {p.login_url}", flush=True)
    print(f"\n  浏览器已打开，请在各标签页逐一扫码/登录。", flush=True)
    print(f"  全部搞定后，回到这里按【回车】抓取保存。", flush=True)
    print(f"{'='*55}\n", flush=True)

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("需要 playwright：pip install playwright && playwright install chromium", err=True, flush=True)
        raise typer.Exit(code=1)

    from stock_review.core.auth.providers import _find_chromium_executable

    exe = _find_chromium_executable()
    launch_kwargs: dict[str, Any] = dict(
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
              "--disable-blink-features=AutomationControlled"],
    )
    if exe:
        launch_kwargs["executable_path"] = exe

    p = sync_playwright().start()
    browser = None

    try:
        browser = p.chromium.launch(**launch_kwargs)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        # 为每个平台打开一个 tab
        pages: dict[str, Any] = {}
        for name in active:
            page = ctx.new_page()
            provider = get_provider(name)
            try:
                page.goto(provider.login_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"  [{name}] goto 未完全就绪（可忽略）: {e}", flush=True)
            pages[name] = page

        print(f"✅ {len(pages)} 个标签页已打开，请开始登录...\n", flush=True)

        # 纯手动等待：用户按回车才抓取，超时兜底
        import threading
        done_flag = {"done": False}

        def _wait_enter():
            try:
                input(">>> 登录完成后按回车抓取...\n")
                done_flag["done"] = True
            except (EOFError, OSError):
                done_flag["done"] = True

        t = threading.Thread(target=_wait_enter, daemon=True)
        t.start()
        t.join(timeout)
        if not done_flag["done"]:
            print(f"\n⏰ {mins} 分钟超时，自动抓取当前态...", flush=True)

        # 抓取所有平台
        print("", flush=True)
        for name in pages:
            try:
                provider = get_provider(name)
                result = provider._capture_state(ctx)
                cookies = result.cookies
                if cookies or result.storage_state:
                    CookieStore(name).save(
                        cookies,
                        ttl=0,
                        expires_map=result.expires_map,
                        success_cookies=provider.success_cookies,
                        storage_state=result.storage_state,
                    )
                    days = CookieStore(name).ttl_seconds() // 86400
                    print(f"  ✅ [{name}] {provider.display}：{len(cookies)} cookie / "
                               f"{len(result.storage_state.get('origins', []))} origin / "
                               f"约 {days} 天有效", flush=True)
                else:
                    print(f"  ⚠️ [{name}] {provider.display}：未捕获到登录态", flush=True)
            except Exception as e:
                print(f"  ❌ [{name}] 抓取失败: {e}", flush=True)
    except Exception as e:
        print(f"登录流程异常: {e}", err=True, flush=True)
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            p.stop()
        except Exception:
            pass

    print(f"\n{'='*55}", flush=True)
    print("  全部完成！运行 stock-review status 查看各平台状态", flush=True)
    print(f"{'='*55}", flush=True)





@app.command()
def logout(
    platform: str = typer.Argument("ths", help="平台：ths/kpl/dxr/taoguba/xueqiu/jiuyan"),
) -> None:
    """清除指定平台的持久化 cookie（下次操作会要求重新登录）。"""
    from stock_review.core.auth import LoginManager
    from stock_review.core.auth.providers import is_accessible_platform, is_known_platform

    if not is_known_platform(platform):
        typer.echo(f"未知平台 '{platform}'，可用：", err=True)
        for r in LoginManager().list_platforms():
            typer.echo(f"  {r['name']} ({r['display']})", err=True)
        raise typer.Exit(code=2)
    if not is_accessible_platform(platform):
        reason = next(
            (r["blocked_reason"] for r in LoginManager().list_platforms()
             if r["name"] == platform),
            "该平台当前不可访问",
        )
        typer.echo(f"[{platform}] 该平台当前不可访问，已搁置：{reason}", err=True)
        raise typer.Exit(code=2)
    LoginManager().forget(platform)
    typer.echo(f"[{platform}] 已清除持久化 cookie")


@app.command(name="platforms")
def list_platforms_cmd() -> None:
    """列出所有可登录平台及其登录入口。"""
    from stock_review.core.auth import LoginManager

    rows = LoginManager().list_platforms()
    typer.echo(f"共 {len(rows)} 个平台：")
    for r in rows:
        if not r.get("accessible", True):
            flag = "已搁置(不可访问)"
        elif r["needs_token"]:
            flag = "需登录解锁"
        else:
            flag = "免登录可取部分"
        typer.echo(
            f"  {r['name']:<8} {r['display']:<6} {flag}  {r['login_url']}"
        )


@app.command()
def status() -> None:
    """查看各平台登录状态与剩余有效期（cookie 数 + localStorage 项数）。"""
    from stock_review.core.auth import LoginManager

    rows = LoginManager().status()
    typer.echo(f"{'平台':<8}{'名称':<7}{'状态':<8}{'剩余':<7}{'cookie':<7}{'localStorage':<13}登录页")
    for r in rows:
        if not r.get("accessible", True):
            typer.echo(
                f"{r['name']:<8}{r['display']:<7}{'已搁置':<8}{'-':<7}{'-':<7}{'-':<13}{r['login_url']}"
            )
            continue
        if not r.get("saved"):
            state, left, cnt, ls = "未登录", "-", "-", "-"
        else:
            state = "有效" if r["fresh"] else "已过期"
            left = f"{r['days_left']}天" if r["days_left"] is not None else "会话级"
            cnt = str(r["cookie_count"])
            ls = str(r.get("ls_count", 0))
        typer.echo(
            f"{r['name']:<8}{r['display']:<7}{state:<8}{left:<7}{cnt:<7}{ls:<13}{r['login_url']}"
        )


@app.command()
def probe(
    platform: str = typer.Argument(..., help="平台：ths/kpl/dxr/taoguba/xueqiu"),
) -> None:
    """验证某平台登录态能否带上（自检「调用不通过」）。

    用已保存的 storage_state 恢复浏览器上下文访问平台，报告是否已登录、
    抓到的 cookie 数与 localStorage 键（韭研的 token 就在这里）。
    """
    from stock_review.core.auth import LoginManager
    from stock_review.core.auth.providers import is_accessible_platform, is_known_platform

    if not is_known_platform(platform):
        typer.echo(f"未知平台 '{platform}'", err=True)
        raise typer.Exit(code=2)
    if not is_accessible_platform(platform):
        reason = next(
            (r["blocked_reason"] for r in LoginManager().list_platforms()
             if r["name"] == platform),
            "该平台当前不可访问",
        )
        typer.echo(f"[{platform}] 该平台当前不可访问，已搁置：{reason}", err=True)
        raise typer.Exit(code=2)
    r = LoginManager().verify(platform)
    ok = r.get("ok")
    typer.echo(f"[{platform}] 登录态验证：{'通过' if ok else '未通过'}")
    typer.echo(f"  原因      : {r.get('reason')}")
    typer.echo(f"  HTTP 状态 : {r.get('http_status')}")
    typer.echo(f"  已登录判定: {r.get('logged_in')}")
    typer.echo(f"  cookie 数 : {r.get('cookie_count')}")
    ls_keys = r.get("ls_keys") or []
    typer.echo(f"  localStorage 键: {ls_keys if ls_keys else '（无）'}")
    if not ok:
        typer.echo(
            f"  → 建议重登：stock-review login {platform}", err=True
        )
        raise typer.Exit(code=1)


@app.command()
def connect(
    platform: str = typer.Argument(..., help="平台：ths/kpl/dxr/taoguba/xueqiu"),
    action: str = typer.Option(
        "smoke", "--action", "-a",
        help="smoke=受控鉴权调用连通性自检；verify=仅浏览器 probe 验证登录态",
    ),
    call: str = typer.Option(
        "", "--call", "-c",
        help=(
            "直接调具体方法，格式 '方法:参数'，如 "
            "xueqiu 用 quote:SH600000 / kline:SH600000；"
            "kpl 用 sector_strength:801159（需 KPL_USER_ID/KPL_TOKEN）；"
            "taoguba 用 user_blog:<用户id> / post:<topic>_<reply>；"
            "ths 用 quote:600519"
        ),
    ),
) -> None:
    """平台连接器：保证登录态后尝试调用（杜绝裸发/重复试错）。

    - verify：用已保存 storage_state 恢复浏览器上下文验证登录态能否带上。
    - smoke ：先验证登录态，再做一次受控鉴权调用（自动带 Cookie+token+平台特有头）；
      无登录态直接报错提示重登；401/403 视为失效、不重试。
    - -c/--call：直接调具体数据方法（见 --call 说明），例如
      `stock-review connect xueqiu -c quote:SH600000`
    """
    from stock_review.adapters.platforms import NeedLoginError, get_connector
    from stock_review.core.auth import LoginManager
    from stock_review.core.auth.providers import is_accessible_platform, is_known_platform

    if not is_known_platform(platform):
        typer.echo(f"未知平台 '{platform}'", err=True)
        raise typer.Exit(code=2)
    if not is_accessible_platform(platform):
        reason = next(
            (r["blocked_reason"] for r in LoginManager().list_platforms()
             if r["name"] == platform),
            "该平台当前不可访问",
        )
        typer.echo(f"[{platform}] 该平台当前不可访问，已搁置：{reason}", err=True)
        raise typer.Exit(code=2)
    try:
        c = get_connector(platform)
    except KeyError as e:
        typer.echo(f"无可用连接器: {e}", err=True)
        raise typer.Exit(code=2)

    if action == "verify":
        r = c.verify_login()
        ok = r.get("ok")
        typer.echo(f"[{platform}] 登录态验证（浏览器 probe）：{'通过' if ok else '未通过'}")
        typer.echo(f"  原因      : {r.get('reason')}")
        typer.echo(f"  HTTP 状态 : {r.get('http_status')}")
        typer.echo(f"  已登录判定: {r.get('logged_in')}")
        ls_keys = r.get("ls_keys") or []
        typer.echo(f"  cookie 数 : {r.get('cookie_count')}  localStorage 键: {ls_keys if ls_keys else '（无）'}")
        if not ok:
            typer.echo(f"  → 建议重登：stock-review login {platform}", err=True)
            raise typer.Exit(code=1)
        return

    # -c/--call：直接调具体数据方法
    if call:
        _dispatch_call(c, call, platform)
        return

    # smoke：受控鉴权调用
    try:
        res = c.smoke()
    except NeedLoginError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    typer.echo(
        f"[{platform}] 连通性自检：{'通过' if res.ok else '未通过'}"
        f"（HTTP {res.status_code}）"
    )
    if res.problems:
        for p in res.problems:
            typer.echo(f"  - {p}")
    if res.ok and isinstance(res.data, str) and res.data:
        typer.echo(f"  返回长度: {len(res.data)} 字符（已带登录态成功调通）")


def _dispatch_call(c, call: str, platform: str) -> None:
    """解析 'method:arg' 并调用连接器方法（受登录态闸门保护，不重试）。"""
    from stock_review.adapters.platforms.base import NeedLoginError

    if ":" in call:
        method, arg = call.split(":", 1)
    else:
        method, arg = call, ""
    method = method.strip()
    if not hasattr(c, method) or method in ("request", "get", "post", "smoke"):
        typer.echo(
            f"[{platform}] 不支持的方法 '{method}'；可用方法见各平台连接器源码"
            f"（如 xueqiu: quote/kline，kpl: sector_strength，taoguba: user_blog/post，ths: quote）",
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(f"[{platform}] 调用 {method}('{arg}')（受登录态闸门保护）…")
    try:
        if arg:
            res = getattr(c, method)(arg)
        else:
            res = getattr(c, method)()
    except NeedLoginError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"  结果：{'通过' if res.ok else '未通过'}（HTTP {res.status_code}）")
    if res.problems:
        for p in res.problems:
            typer.echo(f"  - {p}")
    if res.ok and res.data is not None:
        if isinstance(res.data, str):
            snippet = res.data[:500].replace("\n", " ")
            typer.echo(f"  返回长度: {len(res.data)} 字符；前 500 字: {snippet}")
        else:
            import json as _json

            text = _json.dumps(res.data, ensure_ascii=False, indent=2)
            typer.echo(f"  返回（已解析，共 {len(res.data) if hasattr(res.data, '__len__') else '?'} 项）:")
            # 长结果截断，避免刷屏
            typer.echo(text[:1500])


@app.command()
def sniff(
    platform: str = typer.Argument(..., help="平台：ths/kpl/dxr/taoguba/xueqiu"),
    url: list[str] = typer.Option(
        [], "--url", "-u",
        help="额外要访问的 URL（可多次），会自动导航触发 XHR",
    ),
    no_auto: bool = typer.Option(
        False, "--no-auto",
        help="关闭自动遍历菜单（改为仅访问入口 + 指定 URL，需手动点菜单时加 --no-wait）",
    ),
    no_wait: bool = typer.Option(
        False, "--no-wait",
        help="不暂停等待手动点菜单，仅收集自动加载的接口",
    ),
) -> None:
    """登录后自动抓包：打开已登录浏览器，自动遍历菜单捕获真实 XHR/fetch 接口。

    用于短线侠/同花顺等「登录后 JS 动态加载」平台——真实接口路径无公开文档。
    默认自动发现并遍历全站同域菜单链接（免人工点菜单），抓到确切 URL 后落盘清单，
    避免瞎猜 path。补采特定板块用 --url。

    典型用法：
      stock-review login dxr && stock-review sniff dxr   # 登录后自动遍历全站
      stock-review sniff ths -u https://dq.10jqka.com.cn/zt  # 指定入口+补采
    """
    from stock_review.core.auth.providers import is_accessible_platform, is_known_platform
    from stock_review.core.auth.sniffer import sniff as run_sniff

    if not is_known_platform(platform):
        typer.echo(f"未知平台 '{platform}'", err=True)
        raise typer.Exit(code=2)
    if not is_accessible_platform(platform):
        typer.echo(f"[{platform}] 该平台当前不可访问，已搁置", err=True)
        raise typer.Exit(code=2)

    res = run_sniff(
        platform,
        extra_urls=list(url) or None,
        wait=not no_wait,
        auto_explore=not no_auto,
    )
    eps = res.get("endpoints") or []
    explored = res.get("explored") or []
    typer.echo(
        f"[{platform}] 自动遍历 {len(explored)} 个链接，抓到 {len(eps)} 个数据接口，"
        f"已保存到 {res.get('report_path')}"
    )
    if explored:
        typer.echo("  已遍历:")
        for link in explored[:30]:
            typer.echo(f"    - {link}")
        if len(explored) > 30:
            typer.echo(f"    ... 其余 {len(explored) - 30} 个见报告文件")
    if res.get("error"):
        typer.echo(f"  ⚠️ {res['error']}", err=True)
    for e in eps[:40]:
        typer.echo(
            f"  [{e['status']}] {e['method']} {e['host']}{e['path']}"
            f"{('?' + e['query']) if e['query'] else ''}  x{e['hits']}"
        )
        if e.get("sample"):
            typer.echo(f"      └ {e['sample'][:160]}")
    if len(eps) > 40:
        typer.echo(f"  ... 其余 {len(eps) - 40} 个见报告文件")
    if not eps:
        typer.echo(
            "  未抓到接口：请确认已登录（先 stock-review login dxr），"
            "或加 --url 指定带数据的板块页",
            err=True,
        )
        raise typer.Exit(code=1)


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
