"""淘股吧连接器：登录态保证 + 受控请求。

鉴权方式：网页 cookie（参考 github.com/HRedL/taoguba：登录后把 cookies 作为会话鉴权，
Scrapy 里放 Request.cookies；我们用 httpx 放 headers 等价）。淘股吧为论坛社区，数据以
页面型 URL 为主（用户主页 + 原贴链接），部分列表有 ajax 接口。

接口说明（已确认的形态）：
- 用户主页：https://www.taoguba.com.cn/blog/{user_id}
- 原贴链接：由 new_topic_id + new_reply_id + "_1" 拼接
- 鉴权：cookie（TGB_TOKEN/user 等会话票），无 cookie 只能看有限内容

本连接器提供 `user_blog()` / `post()` 两个真实页面型接口（受控、带登录态、不重试），
以及 `search_posts()` 占位（真实 ajax 路径待抓包确认）。
"""
from __future__ import annotations

from stock_review.adapters.platforms.base import AuthCallResult, BasePlatformConnector
from stock_review.core.registry import connector_registry


@connector_registry.register("taoguba")
class TaogubaConnector(BasePlatformConnector):
    platform = "taoguba"
    display = "淘股吧"
    base_url = "https://www.taoguba.com.cn"
    token_keys = ()

    def smoke_url(self) -> str:
        # 首页（登录态可访问，验证 cookie 鉴权能带上）
        return f"{self.base_url}/"

    def user_blog(self, user_id: str) -> AuthCallResult:
        """用户主页（参考 HRedL/taoguba 的 blog/{user_id} 拼接规则）。"""
        self.ensure_logged_in(verify=False)
        return self.get(f"{self.base_url}/blog/{user_id}", verify_login=False)

    def post(self, topic_id: str, reply_id: str = "") -> AuthCallResult:
        """原贴页（topic_id + reply_id + "_1" 拼接，参考 HRedL/taoguba）。"""
        self.ensure_logged_in(verify=False)
        path = f"{topic_id}{reply_id}_1"
        return self.get(f"{self.base_url}/{path}", verify_login=False)

    def search_posts(self, keyword: str) -> AuthCallResult:
        """搜索帖子。

        ⚠️ 接口待抓包确认：淘股吧真实搜索 ajax 接口路径待登录后浏览器 Network 确认。
        """
        self.ensure_logged_in(verify=False)
        raise NotImplementedError(
            "淘股吧搜索 XHR 接口 path 待抓包确认，暂不可用。"
            "请在登录后浏览器 Network 中确认搜索请求路径后更新 search_posts() 实现。"
        )
