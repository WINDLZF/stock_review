"""登录后网络抓包：用已保存登录态打开浏览器，自动遍历菜单捕获真实 XHR/fetch 接口。

用途（回应「短线侠/同花顺行情 XHR 路径待抓包」）：
这类平台登录后由 JS 动态加载数据，真实接口无公开文档，需在登录态下浏览页面时
观察 Network。本模块把这一过程自动化，避免闭门造车瞎猜 path：

- 复用 CookieStore 里保存的 storage_state 恢复登录态（无需重登）；缺登录态则打开
  登录页让用户先登录（headed）。
- 用系统内核浏览器（Edge/Chrome，规避反爬 403）+ 隐藏 webdriver 特征。
- 监听所有响应，筛出「API 型」调用（resource_type=xhr/fetch、响应 content-type 含
  json、或 URL 含 /api 或以 .json 结尾），记录 method/path/query/status/
  content-type/响应片段/POST 体。
- **自动遍历（auto_explore，默认开）**：加载入口页后，从 DOM 抓取同域导航链接，
  逐一访问触发 XHR——无需人工点菜单。也可指定 --url 补采特定板块。
- 结果按 (method, path) 去重，落盘 .secrets/<platform>_sniff.json，并打印接口清单，
  供直接填入连接器。

合规边界：仅用于用户本人已合法登录的站点、观察其前端自身发起的请求，用于对接自有
数据消费；不做风控绕过 / 签名破解。401/403 记录但不重试。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from stock_review.core.auth.cookie_store import DEFAULT_SECRETS_DIR, CookieStore
from stock_review.core.auth.providers import _find_chromium_executable, get_provider

# 各平台抓包的入口 URL（触发登录后 XHR）。其余菜单由 auto_explore 自动发现。
_ENTRY_URLS: dict[str, list[str]] = {
    "dxr": [
        "https://duanxianxia.com/web/",
    ],
    "ths": [
        "https://dq.10jqka.com.cn/",
    ],
    "taoguba": [
        "https://www.taoguba.com.cn/",
    ],
    "xueqiu": [
        "https://xueqiu.com/",
    ],
    "kpl": [
        "https://www.kaipanla.com/",
    ],
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def _is_api_response(resource_type: str, url: str, content_type: str) -> bool:
    """判定一次响应是否是「数据接口」而非静态资源/页面。"""
    if resource_type in ("xhr", "fetch"):
        return True
    ct = (content_type or "").lower()
    if "json" in ct:
        return True
    low = url.lower()
    path = urlsplit(low).path
    if "/api" in path or path.endswith(".json"):
        return True
    return False


def _discover_links(page: Any, origin: str, max_links: int = 50) -> list[str]:
    """从当前页面 DOM 抓取同域导航链接（去重），用于自动遍历触发 XHR。

    只取 a[href] 中同域、且路径不含典型静态资源后缀的链接，避免把 css/js/img 当菜单。
    """
    try:
        hrefs = page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
        )
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(hrefs, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for h in hrefs:
        if not isinstance(h, str) or not h.startswith(origin):
            continue
        clean = h.split("#")[0].rstrip("/")
        if not clean or clean in seen:
            continue
        low = clean.lower()
        if any(low.endswith(s) for s in (".css", ".js", ".png", ".jpg", ".jpeg",
                                          ".gif", ".svg", ".ico", ".woff", ".woff2")):
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= max_links:
            break
    return out


def sniff(
    platform: str,
    *,
    extra_urls: list[str] | None = None,
    wait: bool = True,
    auto_explore: bool = True,
    max_links: int = 50,
    timeout: int = 600,
    max_snippet: int = 400,
    secrets_dir: Path | str = DEFAULT_SECRETS_DIR,
) -> dict[str, Any]:
    """打开已登录浏览器抓取 API 接口，返回 {ok, endpoints, report_path, error, explored}。

    - platform：ths/kpl/dxr/taoguba/xueqiu 等。
    - extra_urls：除内置入口外，额外要访问的 URL（会自动导航触发 XHR）。
    - auto_explore：加载入口后自动发现并遍历同域菜单链接（默认开，免人工点菜单）。
    - wait：仅在 auto_explore 关闭且处于交互终端时，才暂停等人工点菜单回车收集。
    - 结果按 (method, path) 去重，落盘 .secrets/<platform>_sniff.json。
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        return {"ok": False, "endpoints": [], "report_path": None, "explored": [],
                "error": "未安装 playwright，无法抓包：pip install playwright && playwright install"}

    store = CookieStore(platform, secrets_dir)
    state = store.load_storage_state()
    # 旧格式兼容：无 storage_state 但有 cookie 时，用登录页 host 重建最小 state
    if not state:
        cookies = store.load() or {}
        if cookies:
            try:
                host = urlsplit(get_provider(platform).login_url).netloc
            except Exception:  # noqa: BLE001
                host = ""
            state = {
                "cookies": [
                    {"name": k, "value": v, "domain": host, "path": "/",
                     "expires": -1, "httpOnly": False, "secure": False}
                    for k, v in cookies.items()
                ],
                "origins": [],
            }

    entry_urls = list(_ENTRY_URLS.get(platform, []))
    if extra_urls:
        entry_urls += list(extra_urls)
    if not entry_urls:
        try:
            entry_urls = [get_provider(platform).login_url]
        except Exception:  # noqa: BLE001
            entry_urls = []

    # (method, path) -> 记录（去重，保留首个样本）
    captured: dict[tuple[str, str], dict[str, Any]] = {}
    explored: list[str] = []

    exe = _find_chromium_executable()
    launch_kwargs: dict[str, Any] = dict(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    if exe:
        launch_kwargs["executable_path"] = exe

    def _on_response(response: Any) -> None:
        try:
            req = response.request
            rtype = req.resource_type
            url = response.url
            headers = response.headers or {}
            ctype = headers.get("content-type", "")
            if not _is_api_response(rtype, url, ctype):
                return
            parts = urlsplit(url)
            path = parts.path
            method = req.method
            key = (method, f"{parts.netloc}{path}")
            if key in captured:
                captured[key]["hits"] += 1
                return
            snippet = ""
            try:
                if "json" in ctype.lower() or rtype in ("xhr", "fetch"):
                    body = response.text()
                    snippet = body[:max_snippet].replace("\n", " ")
            except Exception:  # noqa: BLE001
                snippet = "(响应体读取失败/二进制)"
            post_data = ""
            try:
                if method == "POST":
                    post_data = (req.post_data or "")[:max_snippet]
            except Exception:  # noqa: BLE001
                post_data = ""
            captured[key] = {
                "method": method,
                "host": parts.netloc,
                "path": path,
                "query": parts.query,
                "status": response.status,
                "content_type": ctype,
                "resource_type": rtype,
                "post_data": post_data,
                "sample": snippet,
                "hits": 1,
            }
        except Exception:  # noqa: BLE001
            return

    error = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            ctx_kwargs: dict[str, Any] = {"user_agent": _UA}
            if state:
                ctx_kwargs["storage_state"] = state
            ctx = browser.new_context(**ctx_kwargs)
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = ctx.new_page()
            page.on("response", _on_response)

            origin = urlsplit(entry_urls[0]).netloc if entry_urls else ""

            for u in entry_urls:
                print(f"[{platform}][sniff] 打开 {u}")
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)  # 等页面 JS 发起首批 XHR
                except Exception as e:  # noqa: BLE001
                    print(f"[{platform}][sniff] goto 未完全就绪(可忽略): {e}")

            if not state:
                print(f"[{platform}][sniff] ⚠️ 本地无登录态，请先在浏览器里登录")

            # 自动遍历：发现同域菜单链接并逐个访问，触发各自的数据 XHR
            if auto_explore and origin:
                links = _discover_links(page, f"https://{origin}", max_links=max_links)
                links += _discover_links(page, f"http://{origin}", max_links=max_links)
                links = list(dict.fromkeys(links))  # 保序去重
                print(f"[{platform}][sniff] 自动发现 {len(links)} 个同域链接，开始遍历")
                for link in links:
                    try:
                        page.goto(link, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2200)
                        explored.append(link)
                    except Exception as e:  # noqa: BLE001
                        print(f"[{platform}][sniff] 遍历 {link} 失败(可忽略): {e}")

            # 人工补采（仅 auto_explore 关闭且交互终端时暂停等回车）
            if wait and not auto_explore and sys.stdin.isatty():
                input(
                    f"[{platform}][sniff] 请在浏览器中点开各菜单"
                    f"（竞价/复盘/涨停表现/龙虎榜等），触发数据加载后回车收集…\n> "
                )
            else:
                # 非交互：多等一会，尽量收集延迟加载的 XHR
                deadline = time.time() + min(timeout, 12)
                while time.time() < deadline:
                    page.wait_for_timeout(1000)

            browser.close()
    except Exception as e:  # noqa: BLE001
        error = f"抓包过程异常: {e}"

    endpoints = sorted(
        captured.values(), key=lambda r: (-r["hits"], r["host"], r["path"])
    )
    report_path = Path(secrets_dir) / f"{platform}_sniff.json"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "platform": platform,
                    "saved_at": time.time(),
                    "explored": explored,
                    "endpoints": endpoints,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        error = error or f"报告落盘失败: {e}"

    return {
        "ok": bool(endpoints) and not error,
        "endpoints": endpoints,
        "report_path": str(report_path),
        "explored": explored,
        "error": error,
    }
