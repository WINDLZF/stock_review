"""多平台登录提供者。统一基于 playwright 实浏览器捕获，缺依赖回退手动粘贴。

关键修复（对齐 zt-review 的一步到位方案）：
- 优先用系统已装的 Edge/Chrome 内核（executable_path），而非 Playwright 自带的
  "Chrome for Testing"。同花顺 Nginx 反爬会识别后者并直接 403，系统浏览器则正常。
- 抓取用 **storage_state（含 localStorage）**，不只抓 cookie。
  这是修复「韭研调用不通过」的核心：韭研公社是 SPA，登录态（token）在
  localStorage 而非 cookie；只抓 cookie 会丢登录凭证，导致"登录了却等于没登"，
  裸发请求被按 IP 封 → 调用不通过。
- 登录检测「双通道 + manual_only」：
  * 自动通道：login_page_markers（离开登录页=成功）+ success_cookies（会话票出现=成功）。
    不靠「任意带未来过期的 cookie」判断——同花顺匿名 token(v) 自带 399 天 expires，
    会被误判为已登录导致抓到空态。
  * manual_only：SPA 弹窗登录、URL 不变、登录态在 localStorage（如韭研）——不自动
    检测，直接提示用户登录后回车抓取，避免干等超时与误判。
  * 手动通道：自动未命中时用户在弹窗完成登录，回终端按回车即抓取。

新增平台：只需继承 BaseLoginProvider，填 name / display / login_url /
login_page_markers / success_cookies（可留空）/ manual_only，并加进 _PROVIDERS。
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# 优先使用系统已装的 Chromium 内核浏览器（Edge/Chrome），避免 Playwright 自带的
# "Chrome for Testing" 被同花顺 Nginx 反爬 403 拦截。
_EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_chromium_executable() -> str | None:
    for cand in _EDGE_CANDIDATES:
        try:
            if os.path.exists(cand):
                return cand
        except OSError:
            continue
    return None


def _parse_cookie(raw: str) -> dict[str, Any]:
    """把 'name=value; name2=value2' 解析为字典。"""
    out: dict[str, Any] = {}
    for part in raw.strip().split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _timed_input(prompt: str, timeout: int) -> str | None:
    """带超时的 input：超时返回 None（不抛）。

    Windows 无 SIGALRM，用守护线程读 stdin；超时未确认即返回 None，
    让登录流程自动抓取「当前已捕获的登录态」，避免无限干等。
    """
    import threading

    buf: dict[str, str] = {}

    def _read() -> None:
        try:
            buf["val"] = input(prompt)
        except Exception:  # noqa: BLE001
            buf["val"] = ""  # EOF / 中断一律视为空输入

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None
    return buf.get("val")


@dataclass
class LoginResult:
    """一次登录的完整产物。

    - cookies：name->value（便于拼 Cookie 头）。
    - expires_map：name->绝对过期时间戳（秒），仅持久 cookie。
    - storage_state：Playwright 完整登录态（cookies + origins/localStorage），
      SPA（韭研）的 token 在这里，是"调用能通过"的关键。
    """

    cookies: dict[str, Any] = field(default_factory=dict)
    expires_map: dict[str, float] = field(default_factory=dict)
    storage_state: dict[str, Any] = field(default_factory=dict)


class BaseLoginProvider:
    name: str = "base"
    display: str = "基础平台"
    login_url: str = ""
    # 仍在登录页时的 URL 子串；当前 URL 不含任一标记即视为「已离开登录页=登录成功」
    login_page_markers: list[str] = []
    # 登录成功后才出现的会话票 Cookie 名（OR 逻辑：任一出现即可）；兜底检测信号
    success_cookies: list[str] = []
    # True=不自动检测，直接提示用户登录后回车抓取。
    # 适用于 SPA 弹窗登录、URL 不变化、登录态在 localStorage 的站点（如韭研公社）。
    manual_only: bool = False
    # 该平台数据是否「不登录也能取一部分、登录后取更多/解 IP 封」（仅展示用）
    needs_token: bool = False
    # 当前是否可接入：站点不可用/被封时置 False，CLI 拒绝登录/调用并提示「已搁置」。
    # 这是用户明确要求「标记一下」韭研公社的机制。
    accessible: bool = True
    blocked_reason: str = ""

    def login(self, *, interactive: bool = True, timeout: int = 600) -> LoginResult:
        """执行登录，返回 LoginResult（cookies + expires_map + storage_state）。

        - 自动等待登录（非 manual_only）：轮询浏览器，离开登录页或出现会话票即完成。
        - 自动未命中：给一个有限的人工确认窗口（_manual_grace），超时/浏览器被关则
          **直接抓取当前已捕获的登录态**，绝不丢空、绝不无限等待。
        - **健壮性**：任何中断（用户关浏览器、超时、异常）都会尝试兜底保存已捕获的
          登录态，避免「白等半天、最后崩溃、啥也没存」。
        - 用系统内核(Edge/Chrome)规避 Nginx 403；隐藏 webdriver 特征。
        - 抓取 storage_state（含 localStorage）——SPA 登录态在此，绝不能只抓 cookie。
        """
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError:
            return LoginResult(cookies=self._manual(interactive))

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
            launch_kwargs["executable_path"] = exe  # 用系统内核，绕过反爬 403

        p = sync_playwright().start()
        browser = None
        ctx = None
        result: LoginResult | None = None
        try:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            # 隐藏 webdriver 标志，规避同花顺对自动化浏览器的 Nginx 403 拦截
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{ get: () => undefined });"
            )
            page = ctx.new_page()
            print(f"[{self.name}] 正在打开登录页：{self.login_url}")
            try:
                # domcontentloaded：登录页第三方资源多，load 会卡住；DOM 解析完即可见
                page.goto(self.login_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] goto 未完全就绪(可忽略，页面通常已可见): {e}")

            logged = False
            if not self.manual_only:
                logged = self._wait_login(page, ctx, timeout=timeout)

            if not logged:
                if interactive and sys.stdin.isatty():
                    grace = self._manual_grace(timeout)
                    hint = "（SPA 弹窗登录）" if self.manual_only else "（扫码/验证码）"
                    print(
                        f"[{self.name}] {timeout}s 内未自动识别登录态。请在浏览器完成登录"
                        f"{hint}，成功后回车抓取登录态；{grace}s 内未确认将自动抓取当前态…"
                    )
                    if _timed_input("> ", grace) is None:
                        print(f"[{self.name}] 超时未确认，自动抓取当前已捕获的登录态")
                else:
                    print(f"[{self.name}] 非交互模式，直接抓取当前登录态")

            result = self._capture_state(ctx)
            return result
        except (KeyboardInterrupt, Exception) as e:  # noqa: BLE001
            # 健壮性：浏览器被关/超时/异常，都尝试兜底保存已捕获的登录态
            print(
                f"[{self.name}] 登录流程中断（{type(e).__name__}: {e}），"
                f"尝试兜底保存已捕获的登录态…"
            )
            if ctx is not None:
                try:
                    result = self._capture_state(ctx)
                    print(
                        f"[{self.name}] 兜底保存成功：{len(result.cookies)} cookie / "
                        f"{len(result.storage_state.get('origins', []))} origin"
                    )
                except Exception as e2:  # noqa: BLE001
                    print(f"[{self.name}] 兜底保存失败（浏览器已不可达）: {e2}")
            return result or LoginResult()
        finally:
            try:
                if browser is not None:
                    browser.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                p.stop()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _manual_grace(timeout: int) -> int:
        """人工确认窗口：自动等待已用掉 timeout，这里给一个有限的补充确认时间。"""
        return max(30, min(int(timeout), 180))

    def _capture_state(self, ctx) -> LoginResult:
        """从浏览器上下文抓取完整 storage_state（含 localStorage）——SPA 登录态在此。"""
        try:
            state = ctx.storage_state()
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] storage_state 抓取失败，回退仅抓 cookie: {e}")
            try:
                state = {"cookies": ctx.cookies(), "origins": []}
            except Exception:  # noqa: BLE001
                return LoginResult()
        raw = state.get("cookies", [])
        cookies = {c["name"]: c["value"] for c in raw}
        expires_map = {
            c["name"]: c["expires"]
            for c in raw
            if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0
        }
        state["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        n_ls = sum(len(o.get("localStorage", [])) for o in state.get("origins", []))
        print(
            f"[{self.name}] 抓取到 {len(cookies)} 个 cookie、"
            f"{len(state.get('origins', []))} 个 origin、{n_ls} 个 localStorage 项"
        )
        return LoginResult(cookies=cookies, expires_map=expires_map, storage_state=state)

    def _wait_login(self, page, ctx, timeout: int = 600) -> bool:
        """登录检测（自动通道），满足任一即视为成功（严格，防匿名 token / 空白页误判）：

        1. success_cookies 中任一会话票出现（如 ths 的 user/userid/ticket）——权威信号
        2. 先确认曾到达登录页（URL 含 login_page_markers），再检测「已离开登录页」
           ——必须排除 goto 失败导致 page.url=about:blank 的误判。
        ⚠️ 不靠「任意带未来过期的 cookie」判断——同花顺匿名 token(v) 自带 399 天
           expires，会被误判为已登录导致抓到空态。
        """
        start = time.time()
        reached_login = False
        while time.time() - start < timeout:
            url = page.url or ""
            if self.login_page_markers and any(m in url for m in self.login_page_markers):
                reached_login = True
            cs = ctx.cookies()
            names = {c["name"] for c in cs}
            hit_session = bool(self.success_cookies and (names & set(self.success_cookies)))
            if hit_session:
                print(f"[{self.name}] 检测到会话票 {names & set(self.success_cookies)}，登录成功")
                return True
            if reached_login and self.login_page_markers and not any(
                m in url for m in self.login_page_markers
            ):
                print(f"[{self.name}] 已离开登录页({url})，登录成功")
                return True
            time.sleep(2)
        return False

    # 验证登录态用的页面（默认取登录页 origin 的主页）；子类可覆盖为需登录的页面
    verify_url: str = ""
    # localStorage 里登录 token 的候选 key（用于 SPA 如韭研）
    token_keys: list[str] = []

    def verify(self, storage_state: dict[str, Any], *, timeout: int = 20) -> dict[str, Any]:
        """用已保存的 storage_state 恢复浏览器上下文，验证「登录态是否真的带得上」。

        这是对 SPA + localStorage 场景最可靠的「调用能否通过」验证：
        直接把登录态灌回浏览器访问平台，看是否处于已登录状态。

        返回：{ok, http_status, logged_in, reason, cookie_count, ls_keys}
        """
        cookies = (storage_state or {}).get("cookies", [])
        origins = (storage_state or {}).get("origins", [])
        ls_keys: list[str] = []
        for o in origins:
            ls_keys += [i.get("name") for i in o.get("localStorage", []) if i.get("name")]

        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError:
            return {
                "ok": bool(cookies or ls_keys),
                "http_status": None,
                "logged_in": None,
                "reason": "未装 playwright，仅静态判断：登录态非空",
                "cookie_count": len(cookies),
                "ls_keys": ls_keys,
            }

        url = self.verify_url or self.login_url
        exe = _find_chromium_executable()
        launch_kwargs: dict[str, Any] = dict(headless=True, args=["--no-sandbox", "--disable-gpu"])
        if exe:
            launch_kwargs["executable_path"] = exe
        http_status = None
        logged_in = None
        reason = ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                ctx = browser.new_context(storage_state=storage_state)
                page = ctx.new_page()
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    http_status = resp.status if resp else None
                except Exception as e:  # noqa: BLE001
                    reason = f"访问 {url} 异常: {e}"
                logged_in, why = self._is_logged_in(page)
                if why:
                    reason = why
                browser.close()
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False, "http_status": http_status, "logged_in": None,
                "reason": f"验证浏览器启动失败: {e}",
                "cookie_count": len(cookies), "ls_keys": ls_keys,
            }

        # 已权威判定为登录态（命中会话票 / localStorage token）即视为 ok，
        # 不被登录页本身的 401 掩盖（登录页无需鉴权，返回 4xx 属正常）。
        if logged_in is True:
            ok = True
        else:
            ok = bool(cookies or ls_keys)
            if http_status is not None and http_status >= 400:
                reason = reason or f"HTTP {http_status}（可能被反爬/未登录拦截）"
        return {
            "ok": ok, "http_status": http_status, "logged_in": logged_in,
            "reason": reason or ("已登录" if ok else "未检测到登录态"),
            "cookie_count": len(cookies), "ls_keys": ls_keys,
        }

    def _is_logged_in(self, page) -> tuple[bool | None, str]:
        """通用登录态判定：会话票 cookie 命中，或 localStorage 里有 token。

        子类可覆盖为更精确的页面判定（如检测无「登录/注册」按钮）。
        """
        try:
            names = {c["name"] for c in page.context.cookies()}
        except Exception:  # noqa: BLE001
            names = set()
        if self.success_cookies and (names & set(self.success_cookies)):
            return True, f"命中会话票 {names & set(self.success_cookies)}"
        # localStorage token（SPA）
        keys = self.token_keys or []
        try:
            js = "() => Object.keys(window.localStorage)"
            ls_keys = set(page.evaluate(js) or [])
        except Exception:  # noqa: BLE001
            ls_keys = set()
        if keys and (ls_keys & set(keys)):
            return True, f"localStorage 命中 token: {ls_keys & set(keys)}"
        if any("token" in k.lower() for k in ls_keys):
            return True, "localStorage 含 token 类键"
        return None, ""  # 无法确定，交由上层用「登录态非空」兜底

    def _manual(self, interactive: bool) -> dict[str, Any]:
        if not interactive:
            print(f"[{self.name}] 未安装 playwright 且非交互模式，放弃")
            return {}
        raw = input(
            f"[{self.name}] 未安装 playwright，请粘贴浏览器 cookie 字符串"
            f"（name=value; …）:\n> "
        )
        return _parse_cookie(raw)


class THSLoginProvider(BaseLoginProvider):
    name = "ths"
    display = "同花顺"
    login_url = "https://upass.10jqka.com.cn/login"
    login_page_markers = ["/login"]
    success_cookies = ["userid", "user", "ticket"]
    needs_token = False


class KPLLoginProvider(BaseLoginProvider):
    name = "kpl"
    display = "开盘啦"
    login_url = "https://www.kaipanla.com/user/login/"
    login_page_markers = ["/user/login/"]
    success_cookies = ["user_UserID", "user_token"]
    needs_token = False


class DXRLoginProvider(BaseLoginProvider):
    name = "dxr"
    display = "短线侠"
    # 注意：旧代码写成 duanxianx.com（拼写错误），正确主域是 duanxianxia.com
    login_url = "https://duanxianxia.com/web/login"
    login_page_markers = ["/web/login"]
    success_cookies = []
    needs_token = False


class TaogubaLoginProvider(BaseLoginProvider):
    name = "taoguba"
    display = "淘股吧"
    login_url = "https://sso.tgb.cn/web/login/index"
    login_page_markers = ["/login", "/web/login"]
    success_cookies = ["user", "token", "TGB_TOKEN", "tgb_user", "remember_token"]
    needs_token = False


class XueqiuLoginProvider(BaseLoginProvider):
    name = "xueqiu"
    display = "雪球"
    login_url = "https://xueqiu.com/account/login"
    login_page_markers = ["/account/login", "/login"]
    success_cookies = ["xq_a_token"]
    needs_token = False


class JiuyanLoginProvider(BaseLoginProvider):
    name = "jiuyan"
    display = "韭研公社"
    login_url = "https://www.jiuyangongshe.com/"
    # 韭研是 SPA：登录为主页弹窗、/login 会 302 回主页、URL 不变化，
    # 登录态（token）在 localStorage 而非 cookie。故不自动检测，手动确认后
    # 抓完整 storage_state（含 localStorage）——这是"调用能通过"的关键。
    login_page_markers = []
    success_cookies = []
    manual_only = True
    needs_token = True  # 不带头部裸查会被按 IP 封；登录 token 解锁访问
    # 硬鉴权平台：必须登录，连接器 ensure_logged_in 在未登录时直接抛 NeedLoginError。
    # 当前 IP 被封，暂时搁置接入；连接器代码保留，解封后直接改回 accessible=True 即可。
    accessible = False
    blocked_reason = "IP 已被平台封禁，暂时搁置接入"
    verify_url = "https://www.jiuyangongshe.com/"
    token_keys = ["token", "Authorization", "authorization", "access_token"]


# 平台注册表：新增平台只需在此追加一行 + 上面的 class
_PROVIDERS: dict[str, type[BaseLoginProvider]] = {
    "ths": THSLoginProvider,
    "kpl": KPLLoginProvider,
    "dxr": DXRLoginProvider,
    "taoguba": TaogubaLoginProvider,
    "xueqiu": XueqiuLoginProvider,
    "jiuyan": JiuyanLoginProvider,
}


def get_provider(name: str) -> BaseLoginProvider:
    if name not in _PROVIDERS:
        raise KeyError(f"未知登录平台 '{name}'，可用: {sorted(_PROVIDERS)}")
    return _PROVIDERS[name]()


def list_platforms() -> list[dict[str, Any]]:
    """返回所有已注册平台的元数据（用于 CLI 展示 / status）。"""
    return [
        {
            "name": cls.name,
            "display": cls.display,
            "login_url": cls.login_url,
            "needs_token": cls.needs_token,
            "manual_only": cls.manual_only,
            "has_success_cookies": bool(cls.success_cookies),
            "accessible": cls.accessible,
            "blocked_reason": cls.blocked_reason,
        }
        for cls in _PROVIDERS.values()
    ]


def is_known_platform(name: str) -> bool:
    return name in _PROVIDERS


def is_accessible_platform(name: str) -> bool:
    """已知且当前可接入。韭研等被标记 accessible=False 的平台返回 False。"""
    if name not in _PROVIDERS:
        return False
    return _PROVIDERS[name].accessible
