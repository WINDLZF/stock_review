# stock_review 产品规范（单一事实来源）

> 本仓库是**可迁移、可复用、可不断优化**的复盘产品。
> `D:\zt-review`(workbuddy) 仅用于**快速验证想法**（淘股吧 SOP、开盘啦/短线侠借鉴定源、原型试错）；
> 验证通过的想法，沉淀为这里的可插拔适配器 / 规则 / 维度，长期演进。

## 一、核心原则

| 维度 | zt-review（沙盒） | stock_review（产品） |
|---|---|---|
| 定位 | 想法快速验证 | 可迁移复用产品 |
| 数据源 | 手算/硬编码试错 | 适配器可切换，取源不重算 |
| 规则 | 写死在脚本 | 配置中心，调参不动代码 |
| 演进 | 一次性 | 持续迭代、测试覆盖 |

三条铁律：
1. **取源不重算** —— 指标/情绪/梯队/封板率等平台已算好的，绝不自己算；引擎只做取源聚合 + 规则判定。
2. **适配器可迁移** —— akshare / 通达信 / 开盘啦 / 短线侠 / 同花顺 都是可插拔数据源，换源只改 `config.yaml`。
3. **规则可配置** —— 阈值/铁律/权重集中在 `config.yaml` 的 `rules:` 段，调优不碰代码。

## 二、现有架构（已是六边形 + 端口/适配器）

```
HTTP / CLI ──► API(FastAPI) ──► Service(用例) ──► Domain(实体+端口)
                                         │
                          Adapter(可插拔): datasource / repository / dimension / ths
                                         │
                              Infra: SQLite/PG · Cache · Config
```

四大扩展端口（`src/stock_review/domain/ports.py`）：
1. `MarketDataSource` —— 数据源（akshare/tdx/tushare/platform_api）
2. `MarketDataRepository` —— 离线↔实时（CompositeRepository 实时优先、失败回退）
3. `AnalysisDimension` —— 分析维度（`compute(ctx)` 返回 `DimensionResult`）
4. `GroupSyncPort` —— 分组回写（同花顺 HTTP / 文件导出）

编排核心：`services/review.py::ReviewService.run_review` 按 `config.yaml` 的
`plugins.dimensions` 顺序遍历各维度，注册表自动发现，**零侵入扩展**。

## 三、v2 能力扩展（已落地骨架）

### 3.1 取源不重算 —— 扩展 `MarketDataSource` 端口
新增平台「预计算」可选能力（不支持的源抛 `NotImplementedError`，上层探测回退）：
- `get_precomputed_indicators(code)` —— MA/MACD/RSI/KDJ/BOLL，取自同花顺/通达信/东财
- `get_market_sentiment(trade_date)` —— 封板率/涨停跌停家数/连板梯队，取自开盘啦
- `get_emotion_cycle(trade_date)` —— 情绪周期值 + 昨日涨停溢价率，取自**短线侠**
- `get_limit_up_reason(trade_date)` —— 涨停原因/题材标签/题材强度，取自开盘啦题材库
- `get_dragon_tiger(trade_date)` —— 龙虎榜席位（机构/游资人设），取自开盘啦

`technical` 维度改为：**优先 `get_precomputed_indicators`，本地 pandas 计算降级为离线兜底**。

### 3.2 可不断优化 —— 规则中心 `core/rules.py` + `config.yaml::rules:`
所有可调参数外置：
```yaml
rules:
  inference:                       # 板块推演引擎参数
    emotion_high: 70
    emotion_low: 30
    confuse_band: [40, 60]
    space_watch_boards: 5
    mainline_min_seal_ratio: 0.25
  validator:                       # 淘股吧六大铁律（可单独开关）
    - { id: space_break,  name: 空间板断板,   severity: high,   enabled: true }
    - { id: ladder_gap,   name: 梯队断层,     severity: high,   enabled: true }
    - { id: seal_rate_drop, name: 封板率/溢价下滑, severity: medium, enabled: true }
    - { id: limit_down_cluster, name: 跌停集中, severity: high, enabled: true }
    - { id: inst_retail_resonance, name: 机构游资共振, severity: low, enabled: true }
    - { id: position_converge, name: 仓位收敛, severity: medium, enabled: true }
```
`core/rules.py` 提供 `iron_laws()` / `inference_params()` 类型化读取，调参只改 yaml。

## 四、待实现的两个新维度（下一个迭代）

### 4.1 板块推演维度 `inference`（注册名 `inference`）
纯规则引擎，五步推导（结论可溯源、不臆测）：
1. **情绪定位**：用 `get_emotion_cycle` + `get_market_sentiment` 判定 高潮/分歧/冰点
2. **主线判定**：封板资金占比 ≥ `mainline_min_seal_ratio` 的题材即主线
3. **空间板命运**：连板数 ≥ `space_watch_boards` 时给断板/晋级概率提示
4. **题材推演**：结合 `get_limit_up_reason` 做题材延续/切换预判
5. **次日预案**：输出观察标的 + 仓控建议（受 `position_converge` 铁律约束）

### 4.2 淘股吧校验维度 `validator`（注册名 `validator`）
逐条过 `rules.validator` 六大铁律，输出 `通过/告警/触发` 三态卡，严重度排序。

### 4.3 看板 / 内嵌网页 `web/`
作战室暗色风：状态栏 → 连板天梯(断层检测) → 题材矩阵(角色徽章) → 龙虎榜人设
→ **板块推演时间轴** → **次日预案** → **内嵌网页 Tab**(开盘啦/短线侠/同花顺/东财原始视图 + 自研叠加结论)
→ **淘股吧校验卡**。自包含 HTML，可直接打开。

## 五、可迁移性验证（演进清单）
- [x] 六边形骨架 + 四端口 + 注册表零侵入
- [x] 端口扩展：平台预计算能力
- [x] 规则中心：阈值/铁律外置
- [ ] `platform_api` 数据源实现（开盘啦/短线侠 cookie 适配器）
- [ ] `inference` / `validator` 两个维度
- [ ] 看板 + 内嵌网页层
- [ ] 测试覆盖（端口契约 + 规则判定）

## 六、与 zt-review 的边界
- zt-review 产出的 `复盘预案.md` / `kp_theme_full_mapping.md` 是**需求来源**，不在此维护。
- 本仓库只收"验证过的"能力：以适配器 + 规则 + 维度形态沉淀。
- 原型（prototype/*.html）先在 zt-review 试错，定型后移植为 `web/` 下的正式看板。
