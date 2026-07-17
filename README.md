# A股复盘服务 (stock-review)

模块化、服务化的 A 股复盘与自选股管理系统。**Mac / Linux / Windows 皆可运行**，git 友好。

> 设计原则：**六边形 + 端口/适配器**。核心业务（分组、复盘、回写）不依赖任何外部细节；
> 数据源、行情缓存、分析维度、同花顺回写都是可插拔适配器，新增扩展只改配置、不动主流程。

## 架构

```
HTTP / CLI ──► API(FastAPI) ──► Service(用例) ──► Domain(实体+端口)
                                         │
                          Adapter(可插拔): datasource / repository / dimension / ths
                                         │
                              Infra: SQLite/PG · Cache · Config
```

四大扩展端口（见 `src/stock_review/domain/ports.py`）：
1. `MarketDataSource` —— 数据源：akshare（默认）/ tushare / 平台API(cookie) / 通达信离线
2. `MarketDataRepository` —— 离线↔实时：OfflineRepository / CompositeRepository（实时优先、失败回退）
3. `AnalysisDimension` —— 分析维度：technical（均线/MACD/RSI/KDJ）/ breadth（市场宽度），注册即用
4. `GroupSyncPort` —— 分组回写：同花顺 HTTP(cookie) / 文件导出，闭合操作闭环

## 快速开始（Mac）

```bash
# 1. 环境（推荐 uv，比 pip 快且跨平台一致）
brew install uv            # 或：pipx install uv
uv sync                    # 安装依赖（含 dev）
uv sync --extra akshare    # 若要用实时行情，加 akshare

# 2. 配置
cp .env.example .env       # 按需填 SR_THS_API_BASE / SR_THS_COOKIE（回写同花顺用）

# 3. 初始化 + 启动
uv run stock-review initdb
uv run stock-review run    # http://127.0.0.1:8000，文档 /docs

# 或用 uvicorn
uv run uvicorn stock_review.app.main:app --reload
```

## 常用接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/watchlists` | 新建分组（带 signal/weight/note 元数据）|
| GET | `/api/watchlists` | 列出分组 |
| GET | `/api/watchlists/{name}` | 分组详情 |
| PUT | `/api/watchlists/{name}` | 全量更新成员 |
| DELETE | `/api/watchlists/{name}` | 删除分组 |
| POST | `/api/watchlists/{name}/sync` | **回写同花顺**（操作闭环）|
| GET | `/api/review?trade_date=2026-07-18&group=强势股` | 跑复盘（指定分组可离线）|

## 同花顺回写闭环

回写由本系统的 `GroupSyncPort` 完成，两种方式（`config.yaml` 的 `ths.sync_mode` 切换）：
- **http**：携带浏览器登录获取的 cookie 调同花顺开放 API（`SR_THS_API_BASE` / `SR_THS_COOKIE`），
  cookie **由浏览器登录获取，放本地 `.env`，已被 `.gitignore` 排除，绝不入库**。
- **file**：导出标准导入文件（`exports/<分组>.json` + 每行一个代码的 `.txt`），在同花顺客户端导入。

> 浏览器登录拿 cookie 的逻辑在系统外完成（你已跑通），本系统只负责"带 cookie 调 API / 导出文件"。

## 新增扩展（零侵入）

- **加数据源**：在 `adapters/datasource/` 加模块，实现 `MarketDataSource`，`@source_registry.register("xxx")`，
  并在 `config.yaml` 的 `plugins.data_sources` 加入 `xxx`。
- **加分析维度**：在 `adapters/dimension/` 加模块，实现 `AnalysisDimension`，`@dimension_registry.register("yyy")`，
  加入 `plugins.dimensions`，并在 `bootstrap.py` import 触发注册。
- **换数据库**：改 `.env` 的 `SR_DB_URL` 为 Postgres 连接串即可。

## Git 管理

仓库已 `git init`，`.gitignore` 排除了 `.env`、数据库、缓存、日志。
敏感信息（cookie/密码）**不要提交**。推送到远程建议用 Personal Access Token（GitHub 已不支持账号密码 HTTPS）：

```bash
git add .
git commit -m "feat: 初始化模块化复盘服务"
git remote add origin git@github.com:<你>/stock-review.git   # SSH 推荐
git push -u origin main
```

## 目录

```
src/stock_review/
├── app/main.py          # FastAPI 入口
├── api/                 # 路由（HTTP 接口）
├── core/                # config / db / logging / registry
├── domain/              # entities + ports（扩展契约）
├── models/              # SQLAlchemy ORM
├── schemas/             # Pydantic DTO
├── adapters/            # datasource / repository / dimension / ths / exporter
├── services/            # 业务用例
└── cli.py               # Typer CLI
```
