"""各平台登录提供者。统一基于 playwright 实浏览器捕获，缺依赖回退手动粘贴。

新增平台：继承 BaseLoginProvider，填 name / login_url，注册到 _PROVIDERS 即可。
"""
from __future__ import annotations

from typing import Any


def _parse_cookie(raw: str) -> dict[str, Any]:
    """把 'name=value; name2=value2' 解析为字典。"""
    out: dict[str, Any] = {}
    for part in raw.strip().split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


class BaseLoginProvider:
    name = "base"
    login_url = ""

    def login(self, *, interactive: bool = True) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError:
            if not interactive:
                return {}
            return self._manual()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto(self.login_url)
            if interactive:
                input(
                    f"[{self.name}] 请在浏览器完成登录（含验证码），"
                    f"登录成功后回到此处按回车继续…"
                )
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            browser.close()
            return cookies

    def _manual(self) -> dict[str, Any]:
        raw = input(
            f"[{self.name}] 未安装 playwright，请粘贴浏览器 cookie 字符串"
            f"（name=value; …）:\n> "
        )
        return _parse_cookie(raw)


class THSLoginProvider(BaseLoginProvider):
    name = "ths"
    login_url = "https://upass.10jqka.com.cn/login"


class KPLLoginProvider(BaseLoginProvider):
    name = "kpl"
    login_url = "https://www.kpl.com.cn/"


class DXRLoginProvider(BaseLoginProvider):
    name = "dxr"
    login_url = "https://www.duanxianx.com/"


_PROVIDERS: dict[str, type[BaseLoginProvider]] = {
    "ths": THSLoginProvider,
    "kpl": KPLLoginProvider,
    "dxr": DXRLoginProvider,
}


def get_provider(name: str) -> BaseLoginProvider:
    if name not in _PROVIDERS:
        raise KeyError(f"未知登录平台 '{name}'，可用: {sorted(_PROVIDERS)}")
    return _PROVIDERS[name]()
