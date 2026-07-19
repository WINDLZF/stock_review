"""持久化 cookie 仓储：gitignored 本地文件，带时间戳与 TTL 新鲜度探测。

这是解决『每天重写登录模块』的核心：
- cookie 写在稳定的 .secrets/<platform>.json（gitignored），跨会话/跨机器重启都不丢文件；
- 代码在仓库里，更不会丢；
- 过期的只是 cookie，重新跑一次 login 即可，无需重写模块。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DEFAULT_SECRETS_DIR = Path(".secrets")


class CookieStore:
    def __init__(self, platform: str, base_dir: Path | str = DEFAULT_SECRETS_DIR):
        self.platform = platform
        self.path = Path(base_dir) / f"{platform}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        cookies: dict[str, Any],
        ttl: int = 0,
        expires_map: dict[str, float] | None = None,
        success_cookies: list[str] | None = None,
        storage_state: dict[str, Any] | None = None,
    ) -> None:
        """保存登录态。

        持久化内容：
        - cookies：name->value（便于快速拼 Cookie 头）。
        - storage_state：Playwright 完整登录态（cookies + origins/localStorage）。
          **这是修复「韭研调用不通过」的核心** —— SPA 的 token 在 localStorage，
          只存 cookie 会丢登录凭证，调用时鉴权不全被按 IP 封。

        TTL 计算（对齐 zt-review 的真实会话票寿命）：
        - 优先取 success_cookies（会话票，如 ths 的 user/userid/ticket）自带的
          expires 最小值 → 你扫码选 30 天就是 30 天，不靠手填。
        - 会话票是 session 型(无 expires) 或平台未配置 → 回退到传入 ttl。
        - 绝不取「所有持久 cookie 的最小值」——那会被长期匿名 token（如 v 存活近一年）
          误导；也不取最大值（追踪 cookie 近一年，会把失效会话误判长期有效）。
        """
        expires_map = expires_map or {}
        success_cookies = success_cookies or []
        now = time.time()
        eff_ttl = int(ttl)
        # 仅看会话票的 expires
        sess_exps = [e for n in success_cookies if n in expires_map
                     for e in [expires_map[n]] if isinstance(e, (int, float)) and e > now]
        if sess_exps:
            eff_ttl = int(min(sess_exps) - now)
        payload = {
            "platform": self.platform,
            "saved_at": now,
            "ttl": eff_ttl,
            "expires_map": expires_map,
            "cookies": cookies,
            "storage_state": storage_state or {},
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def ttl_seconds(self) -> int:
        """返回已记录的 TTL（秒），无则 0。"""
        if not self.path.exists():
            return 0
        try:
            return int(json.loads(self.path.read_text(encoding="utf-8")).get("ttl", 0))
        except Exception:
            return 0

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data.get("cookies")

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def load_storage_state(self) -> dict[str, Any] | None:
        """读取完整 storage_state（含 localStorage），供 playwright 恢复上下文/取 token。"""
        state = self._read().get("storage_state") or None
        return state if state else None

    def canonical_cookie(self) -> str:
        """从权威源重建 cookie 字符串（修复「调用不带 cookie」的核心）。

        优先级：storage_state.cookies（最可靠）→ 顶层 cookies 字典。
        两者皆空返回空串（调用方应据此判定"未登录/需重登"，切勿裸发）。
        """
        data = self._read()
        ss = data.get("storage_state") or {}
        cks = ss.get("cookies") or []
        if cks:
            return "; ".join(f"{c.get('name')}={c.get('value')}" for c in cks)
        cookies = data.get("cookies") or {}
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def local_storage(self, origin_substr: str = "") -> dict[str, str]:
        """取 localStorage 键值（SPA 的登录 token 在此，如韭研）。

        origin_substr 非空时只取匹配 origin 的项；为空则合并所有 origin。
        """
        ss = self._read().get("storage_state") or {}
        out: dict[str, str] = {}
        for o in ss.get("origins", []):
            if origin_substr and origin_substr not in (o.get("origin") or ""):
                continue
            for item in o.get("localStorage", []):
                name = item.get("name")
                if name is not None:
                    out[name] = item.get("value", "")
        return out

    def token(self, *keys: str) -> str | None:
        """从 localStorage 里按候选 key 顺序取第一个非空值（如韭研的 token）。"""
        ls = self.local_storage()
        for k in keys:
            v = ls.get(k)
            if v:
                return v
        # 宽松匹配：任何 key 含 'token' 且有值
        if not keys:
            for k, v in ls.items():
                if "token" in k.lower() and v:
                    return v
        return None

    def is_fresh(self, ttl: int = 0) -> bool:
        """文件不存在 / 解析失败 / 超过 TTL 都视为不新鲜。"""
        if not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return False
        saved = data.get("saved_at", 0.0)
        eff_ttl = ttl or data.get("ttl", 0)
        if eff_ttl and (time.time() - saved) > eff_ttl:
            return False
        return True

    def saved_at(self) -> float | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("saved_at")
        except Exception:
            return None

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
