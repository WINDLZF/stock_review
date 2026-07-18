# 登录模块设计 / 「每天重写」根因分析与解决方案

> 背景：workbuddy 里经常「丢三落四」，每天都要重写登录模块。本文分析根因并给出
> **可复用、调通后不变**的方案。本仓库的登录模块即按此方案实现。

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
4. **统一登录入口（跨平台复用）** —— `LoginProvider` 端口 + 注册，`ths`/`kpl`/`dxr` 共用同一套流程；新增平台只需继承 `BaseLoginProvider` 填 `name`/`login_url` 并注册。
5. **.gitignore 加固** —— `.secrets/`、`.env`、`.ths/`、`*.cookies.json` 全部排除 → 不会因「误提交再被重置」而丢。
6. **SOP 文档化** —— cookie 过期是**正常**的，跑 `login` 即可，无需重写模块。

## 三、模块结构

```
src/stock_review/core/auth/
├── __init__.py      # 导出 LoginManager / CookieStore / LoginProvider / to_cookie_header
├── ports.py         # LoginProvider 端口（Protocol）
├── cookie_store.py  # CookieStore：持久化 + TTL 新鲜度探测（gitignored 本地文件）
├── providers.py     # BaseLoginProvider + ths/kpl/dxr（playwright 捕获，缺依赖回退手动粘贴）
└── manager.py       # LoginManager：ensure/load/cookie_header/forget
```

## 四、使用

```bash
# 1) 安装登录依赖（可选；不装也能用，会回退手动粘贴）
uv sync --extra auth
playwright install chromium        # 首次需下载浏览器内核

# 2) 登录（实浏览器打开登录页，你手动完成验证码/短信，按回车即捕获 cookie）
stock-review login --platform ths --ttl 86400

# 3) 之后所有需要 cookie 的操作自动带最新 cookie（ths 回写已接线 LoginManager）
stock-review sync 强势股

# 4) 怀疑 cookie 失效时
stock-review logout ths && stock-review login --platform ths --ttl 86400
```

## 五、与「取源不重算 / 可迁移」的关系

- 登录模块获取的是**平台访问凭证**，让 `MarketDataSource` 的 `platform_api` 实现、`GroupSyncPort` 的 `ThsHttpSync` 能拿到 cookie 操作——是「可迁移复用」的钥匙。
- cookie 过期≠模块要重写；模块已固化，过期只刷新凭证。
