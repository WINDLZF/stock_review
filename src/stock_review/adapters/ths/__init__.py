"""同花顺回写适配器：把分组写回同花顺，完成操作闭环。

回写方式两种（config.yaml 的 ths.sync_mode 切换）：
- http：调用同花顺开放 API（cookie 由浏览器登录获取，放 .env，绝不入库）。
- file：导出标准导入文件（JSON + 每行一个代码的 txt），在同花顺客户端导入。
浏览器登录拿 cookie 的逻辑在系统外（你已跑通），本模块只负责"带着 cookie 调 API"。
"""
from __future__ import annotations

from stock_review.core.config import get_settings
from stock_review.domain.entities import Group
from stock_review.domain.ports import GroupSyncPort, SyncResult


def _resolve_ths_cookie() -> str:
    """cookie 解析顺序：配置/环境变量 → 本仓库持久化登录 cookie（非交互读取）。

    这样 `stock-review login` 一次后，后续 sync 自动带最新 cookie，无需手动填 .env。
    """
    try:
        from stock_review.core.auth import LoginManager, to_cookie_header

        cookies = LoginManager().load("ths")
        return to_cookie_header(cookies) if cookies else ""
    except Exception:  # noqa: BLE001
        return ""


def _to_payload(group: Group) -> dict:
    return {
        "group_name": group.name,
        "category": group.category,
        "sep_code": group.sep_code,
        "sep_name": group.sep_name,
        "stocks": [
            {"code": i.code, "name": i.name, "weight": i.weight, "note": i.note, "signal": i.signal}
            for i in group.items
        ],
    }


class ThsHttpSync:
    name = "ths-http"

    def __init__(self, api_base: str | None = None, cookie: str | None = None):
        s = get_settings().ths
        self.api_base = (api_base or s.api_base or "").rstrip("/")
        self.cookie = cookie or s.cookie or _resolve_ths_cookie()

    def sync_group(self, group: Group, *, replace: bool = True) -> SyncResult:
        if not self.api_base or not self.cookie:
            return SyncResult(
                ok=False,
                group_name=group.name,
                target="ths",
                problems=["未配置 SR_THS_API_BASE / SR_THS_COOKIE（cookie 由浏览器登录获取）"],
            )
        payload = _to_payload(group)
        payload["replace"] = replace
        headers = {"Cookie": self.cookie, "Content-Type": "application/json"}
        try:
            import httpx  # noqa: PLC0415

            r = httpx.post(
                f"{self.api_base}/custom-block", json=payload, headers=headers, timeout=30
            )
            r.raise_for_status()
            return SyncResult(ok=True, group_name=group.name, target="ths", detail=r.json())
        except Exception as e:  # noqa: BLE001
            return SyncResult(ok=False, group_name=group.name, target="ths", problems=[str(e)])

    def list_remote_groups(self) -> list[dict]:
        if not self.api_base or not self.cookie:
            return []
        try:
            import httpx  # noqa: PLC0415

            r = httpx.get(
                f"{self.api_base}/custom-block", headers={"Cookie": self.cookie}, timeout=30
            )
            r.raise_for_status()
            return r.json().get("groups", [])
        except Exception:  # noqa: BLE001
            return []


class FileExporter:
    """导出标准导入文件：JSON（供程序消费）+ txt（同花顺客户端导入，每行一个 6 位代码）。"""

    name = "file"

    def __init__(self, export_dir: str | None = None):
        from stock_review.core.config import get_settings as _gs  # noqa: PLC0415

        s = _gs()
        self.export_dir = __import__("pathlib").Path(export_dir or s.ths.export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def sync_group(self, group: Group, *, replace: bool = True) -> SyncResult:
        import json  # noqa: PLC0415

        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in group.name)
        json_path = self.export_dir / f"{safe}.json"
        txt_path = self.export_dir / f"{safe}.txt"
        payload = _to_payload(group)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path.write_text("\n".join(i.code for i in group.items), encoding="utf-8")
        return SyncResult(
            ok=True,
            group_name=group.name,
            target="file",
            detail={"json": str(json_path), "txt": str(txt_path)},
        )

    def list_remote_groups(self) -> list[dict]:
        return []


def build_sync() -> GroupSyncPort:
    """按配置选择回写适配器。"""
    mode = get_settings().ths.sync_mode
    return ThsHttpSync() if mode == "http" else FileExporter()
