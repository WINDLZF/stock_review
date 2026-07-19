# 登录模块设计 / 「每天重写」根因分析与解决方案

> 背景：workbuddy 里经常「丢三落四」，每天都要重写登录模块。本文分析根因并给出
> **可复用、调通后不变**的方案。本仓库的登录模块即按此方案实现。

> ## ⚠️ 韭研公社（jiuyan）已标记搁置
> 韭研公社当前站点不可访问（疑似被封/关闭），接入**暂停**，待恢复后再做。
> 代码侧已通过 `BaseLoginProvider.accessible = False` 标记，CLI 的 `login` / `probe` /
> `connect` 对 `jiuyan` 一律拒绝并提示「已搁置」；`platforms` / `status` 显示为「已搁置」。
> 其余 5 个平台（ths/kpl/dxr/taoguba/xueqiu）正常接入，见下方「平台连接器」。

## 一、根因分析：为什么「每天重写」

| # | 根因 | 说明 |
|---|---|---|
| 1 | **代码未持久化（主因）** | 登录逻辑写在聊天里 / workbuddy 临时脚本，没作为正式文件进版本库。每次新会话上下文重置，代码就没了 → 只能重写。 |
| 2 | **沙盒/会话状态易失** | workbuddy 项目目录或会话很可能是临时的、会话隔离的，未落盘到稳定路径，重启即丢。 |
| 3 | **cookie 过期被误判为「模块坏了」** | 同花顺/开盘啦是**会话级 cookie，通常几小时~1 天就过期**。即使 cookie 文件在，第二天也失效 → 表现为「登录挂了」，于是连模块一起重写。 |
| 4 | **secret 与代码耦合 / 硬编码** | cookie 写死在代码或聊天里，过期后整个逻辑被推倒重来，而不是「只换 cookie」。 |

> 结论：**真正每天丢的是 cookie（过期），不是代码**。但因为没有把代码固化成组件，
> 一旦 cookie 失效，人就会连带把模块重写一遍。

## 二、解决方案：可复用、调通后不变

1. **代码入库** —— 登录模块是正式组件 `src/stock_review/core/auth/`，git 版本化 → 永不失。
2. **secret 与代码分离** —— cookie 存 gitignored 的 `.secrets/<platform>.json`（绝不入库）；代码里不出现任何明文 cookie。
3. **新鲜度探测 + 一键重登** —— `CookieStore` 记录时间戳 + TTL；`LoginManager.ensure()` 先用旧 cookie，失效才触发登录并存回。日常只需：
   ```bash
   stock-review login --platform ths --ttl 86400   # 重新登录并持久化（会话级建议 1 天）
   ```
4. **统一登录入口（跨平台复用）** —— `LoginProvider` 端口 + 注册表，`ths`/`kpl`/`dxr`/`taoguba`/`xueqiu`/`jiuyan` 共用同一套流程；新增平台只需继承 `BaseLoginProvider` 填元数据并注册到 `_PROVIDERS`。
5. **.gitignore 加固** —— `.secrets/`、`.env`、`.ths/`、`*.cookies.json` 全部排除 → 不会因「误提交再被重置」而丢。
6. **SOP 文档化** —— cookie 过期是**正常**的，跑 `login` 即可，无需重写模块。

## 三、模块结构

```
src/stock_review/core/auth/
├── __init__.py      # 导出 LoginManager / CookieStore / LoginProvider / to_cookie_header
├── ports.py         # LoginProvider 端口（Protocol）
├── cookie_store.py  # CookieStore：持久化 + TTL 新鲜度探测（gitignored 本地文件）
├── providers.py     # BaseLoginProvider + ths/kpl/dxr/taoguba/xueqiu/jiuyan（playwright 捕获，缺依赖回退手动粘贴）
└── manager.py       # LoginManager：ensure/load/cookie_header/forget
```

## 四、使用

```bash
# 0) 查看支持的所有平台与登录入口
stock-review platforms
#  ths     同花顺   免登录可取部分  https://upass.10jqka.com.cn/login
#  kpl     开盘啦   免登录可取部分  https://www.kaipanla.com/user/login/
#  dxr     短线侠   免登录可取部分  https://duanxianxia.com/web/login
#  taoguba 淘股吧   免登录可取部分  https://sso.tgb.cn/web/login/index
#  xueqiu  雪球     免登录可取部分  https://xueqiu.com/account/login
#  jiuyan  韭研公社  已搁置(不可访问) https://www.jiuyangongshe.com/

# 1) 安装登录依赖（可选；不装也能用，会回退手动粘贴）
uv sync --extra auth
playwright install chromium        # 首次需下载浏览器内核

# 2) 登录（实浏览器打开登录页，你手动完成扫码/验证码；自动未识别到登录态时按回车抓取）
stock-review login --platform ths --ttl 86400
#  注：jiuyan 已搁置，stock-review login jiuyan 会被拒绝并提示「已搁置」
#  健壮性：
#   - --timeout N：自动识别登录态的等待上限（默认 600s）；超时未识别则进入有限人工确认窗口
#   - 自动未命中后给 30~180s 人工确认窗口，超时/浏览器被关都**自动抓取当前已捕获的登录态**，
#     绝不无限等待、绝不「白等半天最后崩溃啥也没存」（中断时兜底保存 cookie+localStorage）
#   - 登录态获取后，短线侠等平台会**自动附带鉴权头解锁更多数据**（软鉴权：有登录优先、无则降级公开）

# 3) 查看各平台状态（是否新鲜、剩余天数、cookie 数、localStorage 项数），不需重登
stock-review status

# 4) 验证登录态能否"带得上"（自检调用不通过）——用保存的 storage_state 恢复上下文访问
stock-review probe jiuyan

# 5) 之后所有需要 cookie 的操作自动带最新 cookie（ths 回写已接线 LoginManager）
stock-review sync 强势股

# 6) 怀疑 cookie 失效时
stock-review logout ths && stock-review login --platform ths --ttl 86400
```

### 4.0 韭研「调用不通过」根因与修复（重要）

> 现象：韭研公社 IP 被封，一直不带 cookie 裸查导致。加了登录仍然调用不通过。

**根因**：韭研公社是 **SPA，登录态（token）存在 localStorage 而非 cookie**。
早期登录只抓 `cookies`，丢了 localStorage 里的 token → 调用时鉴权不全 → 被按 IP 封。

**修复**（已落地）：
1. 登录时抓 **完整 `storage_state`**（`cookies` + `origins/localStorage`），不只抓 cookie。
2. 韭研标记 `manual_only=True`：弹窗登录、URL 不变化，不自动误判，用户登录后回车抓取。
3. 持久化 `storage_state`；取鉴权材料统一走「权威源」：
   ```python
   from stock_review.core.auth import LoginManager
   mgr = LoginManager()
   headers = mgr.auth_headers("jiuyan", token_keys=("token",))  # Cookie + token + UA + Referer
   tok = mgr.token("jiuyan")            # 取 localStorage 里的登录 token
   ss  = mgr.storage_state("jiuyan")    # 完整登录态，可喂给 playwright new_context(storage_state=ss)
   ```
4. `stock-review probe jiuyan` 会用 `storage_state` 恢复浏览器上下文访问韭研，
   直接告诉你「登录态是否真的带上了」（cookie 数 / localStorage 键 / 是否已登录）。

> 关键原则（`cookie_store.canonical_cookie`）：所有带鉴权的请求都从权威源重建
> cookie/token，**绝不返回空串裸发**——空串会被平台当成「未登录」按 IP 封。

### 4.1 新增一个平台（零侵入）

只需改 `src/stock_review/core/auth/providers.py`：

1. 继承 `BaseLoginProvider`，填元数据：
   ```python
   class NewPlatformLoginProvider(BaseLoginProvider):
       name = "newp"                 # 命令里用的短名
       display = "新平台"             # 展示名
       login_url = "https://x.com/login"
       login_page_markers = ["/login"]          # 仍在登录页的 URL 片段
       success_cookies = ["session_token"]      # 登录后才出现的会话 cookie（OR，任一命中即成功）
       needs_token = False           # 是否「不登录就被按 IP 封」之类，仅用于展示
   ```
   - 登录检测是「双通道」：先自动（出现 `success_cookies` 或离开登录页），自动未命中则
     弹窗等你手动登录、终端按回车即抓取。**不靠猜 cookie 名**，所以即使不知道会话 cookie
     名也能用（留空 `success_cookies`，靠手动通道 + 全量抓取）。
2. 在文件底部 `_PROVIDERS` 注册表追加一行：`"newp": NewPlatformLoginProvider`。
3. （可选）在下游数据源用 `LoginManager().load("newp")` / `cookie_header("newp")` 取 cookie。

> 关键：`providers.py` 里所有 cookie 名只是「停止等待」的判定信号，真正落盘的是浏览器
> 上下文里的**全部** cookie。所以不确定会话 cookie 名时，留空也能正常工作。

## 五、平台连接器（保证登录态、不重复试错）

登录态拿到后，要「调得通」且**绝不裸发/反复试错导致被封 IP**，靠 `adapters/platforms/` 下的
连接器。每个平台一个连接器，统一继承 `BasePlatformConnector` 并 `@connector_registry.register` 注册。

**核心保证（直接回应「鉴权接口不要重复试错、保证登录态」）**：
1. **登录态闸门** `ensure_logged_in()`：任何鉴权调用前必过；本地无新鲜登录态直接抛
   `NeedLoginError`，**绝不裸发空 cookie**（空 cookie 会被按 IP 封）。
2. **只发一次** `request()`：注入完整鉴权头（Cookie 权威源 + localStorage token + UA/Referer +
   平台特有头，如雪球强制 `x` 头）；遇到 401/403 视为登录态失效，返回明确失败，**不重试**。
3. **显式自检** `verify_login()`（浏览器 probe）：恢复 storage_state 访问平台确认「带得上」，
   是 CLI `probe` / `connect --action verify` 的实现，不放在每次请求里（避免每次拉起浏览器）。

```bash
# 列已注册连接器
python -c "from stock_review.adapters.platforms import list_connectors; print(list_connectors())"
# ['ths','kpl','dxr','taoguba','xueqiu']

# 浏览器 probe：确认登录态能否带上（真实无头浏览器恢复 storage_state 访问平台）
stock-review connect ths --action verify

# 直接调具体数据方法（受登录态闸门保护，不重试）
stock-review connect xueqiu -c quote:SH600000     # 雪球行情快照（已验证接口）
stock-review connect ths    -c custom_blocks       # 同花顺自定义板块（需 SR_THS_API_BASE）
stock-review connect kpl    -c sector_strength:801159  # 开盘啦板块强度（需 App 令牌）
stock-review connect taoguba -c user_blog:<用户id>      # 淘股吧用户主页
```

### 5.1 各平台鉴权真相（调研结论，避免闭门造车）

> 接口路径来自公开逆向项目 + 实际浏览器抓包，而非凭空猜测。

| 平台 | 端 | 鉴权 | 真实接口状态 | 借鉴来源 |
|------|-----|------|--------------|----------|
| 同花顺 ths | 网页 | cookie（user/userid/ticket） | **回写 `/custom-block` 已验证**；行情快照路径待抓包 | `adapters/ths/__init__.py` 的 ThsHttpSync、`panghu11033/thsdk` |
| 雪球 xueqiu | 网页 | cookie + **强制 `x` 头**（值取自 `xq_r_token`） | **`/v5/stock/quote.json` 已验证** | 雪球公开 API 形态 |
| 淘股吧 taoguba | 网页 | cookie（登录后 Request.cookies） | 页面型 URL（blog/{id}、原贴链接）已接；列表 ajax 待抓包 | `HRedL/taoguba` |
| 短线侠 dxr | 网页 | **接口公开，无需登录**（vendor/stockdata + /api） | **ztlive/ztplate/getKaipanStock/getYidongAll/hotlist 已验证**；`connect dxr -c limit_up_board` 等已调通 | `stock-review sniff dxr` 抓包确认 |
| 开盘啦 kpl | **App 端** | **URL 内 UserID+Token**（非网页 cookie）+ Dalvik UA | **网页 cookie 调不通 App 接口**；需注入 `KPL_USER_ID`/`KPL_TOKEN` 走 App 接口 | `Rainynitesky/kaipanla-data-parser`、`jinhao2003/kaipanla-crawler` |

⚠️ **关键校准**：开盘啦/短线侠曾被当作「网页登录 cookie 即可调」是错的。开盘啦数据在 App 端
（`apphwshhq.longhuvip.com` 等），鉴权靠 URL 内 UserID+Token，网页登录 cookie 无效。本连接器
**诚实区分**：有 App 令牌才走真实数据接口，否则明确报错提示注入令牌，绝不假装调通。

### 5.2 直接调数据方法（CLI）

```bash
stock-review connect <platform> -c <method>:<arg>
# 支持方法（详见各 connectors/*.py）：
#   xueqiu : quote:SH600000 | kline:SH600000
#   kpl    : sector_strength:801159   （需 KPL_USER_ID / KPL_TOKEN 环境变量）
#   taoguba: user_blog:<id> | post:<topic>_<reply>
#   ths    : custom_blocks | quote:600519（行情路径待抓包确认）
#   dxr    : limit_up_board
```

### 5.3 登录后抓包：确定「待抓包」平台的真实接口（sniff）

部分平台登录后由 JS 动态加载，真实 XHR 无公开文档。不要瞎猜 path，
用 `sniff` 命令打开浏览器（自动复用已保存登录态；无登录态也能抓**公开**接口），
**自动遍历同域导航链接**触发各板块数据 XHR（免人工点菜单），抓到确切接口 URL：

```bash
# 短线侠数据接口是公开的，连登录都不需要，直接抓：
stock-review sniff dxr
# 同花顺等需登录的平台，先登录再抓：
stock-review login ths && stock-review sniff ths -u https://dq.10jqka.com.cn/zt
#   结果落盘 .secrets/<platform>_sniff.json，并打印「自动遍历 N 个链接 + 抓到 M 个接口」：
#   [200] GET  duanxianxia.com/vendor/stockdata/ztlive.json   x1
#         └ {"result":"success","list":[...]}
# 把清单里真实的接口 path 填进 adapters/platforms/<platform>.py 的方法即可。
```

实现见 `core/auth/sniffer.py`：复用已保存的 storage_state 恢复登录态（无需重登），
系统内核浏览器规避反爬，监听所有响应筛出 API 型调用（xhr/fetch、json、含 `/api`），
加载入口后自动 `document.querySelectorAll('a[href]')` 发现同域菜单链接并逐个访问。
⚠️ **已知限制**：若站点导航是 SPA 按钮（非 `<a>` 链接，如短线侠），自动发现可能为空
（`explored:[]`），但默认首页加载通常已打出核心数据 XHR；缺哪块用 `--url` 补采即可。
仅观察前端自身发起的请求用于对接自有消费，不做风控绕过/签名破解。

**新增一个平台连接器**（零侵入，与登录 provider 解耦）：
```python
# adapters/platforms/newp.py
from stock_review.adapters.platforms.base import BasePlatformConnector
from stock_review.core.registry import connector_registry

@connector_registry.register("newp")
class NewpConnector(BasePlatformConnector):
    platform = "newp"
    display = "新平台"
    base_url = "https://x.com"
    token_keys = ("token",)            # 从 localStorage 取登录 token 的候选 key（SPA 用）

    def smoke(self):                   # 一次有代表性的鉴权调用（连通性自检）
        return self.get(f"{self.base_url}/api/me")
```
`adapters/platforms/__init__.py` 已 import 本模块触发注册，无需改其他文件。

## 六、与「取源不重算 / 可迁移」的关系

- 登录模块获取的是**平台访问凭证**，让 `MarketDataSource` 的 `platform_api` 实现、`GroupSyncPort` 的 `ThsHttpSync` 能拿到 cookie 操作——是「可迁移复用」的钥匙。
- cookie 过期≠模块要重写；模块已固化，过期只刷新凭证。
