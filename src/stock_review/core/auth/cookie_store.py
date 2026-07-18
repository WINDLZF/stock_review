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

    def save(self, cookies: dict[str, Any], ttl: int = 0) -> None:
        """保存 cookie。ttl>0 表示有效期秒数（用于新鲜度判定）。"""
        payload = {
            "platform": self.platform,
            "saved_at": time.time(),
            "ttl": int(ttl),
            "cookies": cookies,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data.get("cookies")

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
