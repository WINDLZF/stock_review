"""认证 / 登录基础设施：可复用、跨平台、cookie 持久化且新鲜度可控。

设计目标（直击『workbuddy 每天重写登录模块』）：
- 代码入库永不失：本模块是正式组件，git 版本化，不写在聊天里。
- secret 与代码分离：cookie 存 gitignored 的 .secrets/<platform>.json，绝不入库。
- 新鲜度可控：CookieStore 记录时间戳 + TTL；失效才触发重登，日常一条命令刷新。
- 跨平台复用：LoginProvider 端口 + 注册，ths/kpl/dxr 共用一套流程。
"""
from stock_review.core.auth.cookie_store import CookieStore
from stock_review.core.auth.manager import LoginManager, to_cookie_header
from stock_review.core.auth.ports import LoginProvider

__all__ = ["CookieStore", "LoginManager", "LoginProvider", "to_cookie_header"]
