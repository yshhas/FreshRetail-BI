# 第三章 核心功能模块深度拆解

> 本章按“模块为什么存在 → 输入/输出 → 处理流程 → 关键算法 → 代码位置 → 异常 → 测试 → 优缺点”展开。
> 代码引用格式：`文件:行号`。**A** = 代码/测试直接可见，**B** = 由实现反推。

---

## 3.1 数据基础设施模块（`src/freshretail`）

### 3.1.1 存在原因

在 4.5M 行原始数据上直接写分析代码，会遇到四类问题：

1. 文件可能损坏或版本不对 → 需要哈希校验；
2. 字段类型/顺序/空值可能变化 → 需要契约；
3. 原始列不能被改写 → 需要“只加派生列”的清洗；
4. 每次分析都重复写 SQL → 需要统一指标层。

`src/freshretail` 就是这四类问题的答案（06 §2–§10，A）。

### 3.1.2 模块职责

| 文件 | 职责 | 关键函数 |
|---|---|---|
| `config.py` | 路径、文件契约、字段、口径常量 | `EXPECTED_FILES`、`STOCK_WINDOW_HOURS=16` |
| `contracts.py` | 文件元数据/数据帧/切分校验 | `check_file_metadata`、`check_frame`、`check_split` |
| `cleaning.py` | R001–R012 清洗规则 | `select_clean_sql`、`clean_frame`、`rules_payload` |
| `io.py` | SHA-256、JSON、SQL 路径转义 | `verify_file`、`sql_path` |
| `db.py` | DuckDB 连接/视图/导出 | `connect`、`create_raw_view`、`export_sql` |
| `metrics.py` | 12 个聚合指标 | `daily_summary`、`store_summary`、`product_summary` 等 |
| `pipeline.py` | 流水线编排 | `run()` |
| `logging_utils.py` | JSONL 运行日志 | `RunLogger.log`、`summary` |

### 3.1.3 一条记录如何被清洗

输入（原始 19 列）→ 输出（19 列 + 11 派生列），**不删行、不填补、不覆盖**（06 §6，A）：

| 规则 | 条件 | 派生列 | 说明 |
|---|---|---|---|
| R001 | 总是 | `sales_index = sale_amount` | 归一化销量指数 |
| R002 | `discount=0` | `discount_missing` | 0 与官方“1.0=无折扣”冲突 |
| R003 | `discount>1` | `discount_out_of_range` | 实测 34 行 |
| R004 | `0<d<=1` | `discount_valid` | 有效折扣 |
| R005 | `0<d<1` | `promo_flag` | 1.0 视为无促销 |
| R006 | 总是 | `holiday_proxy` | 仅休息日代理 |
| R007 | 总是 | `stockout_hours_6_22` | 6:00–21:59，16 槽 |
| R008 | `cnt>0` | `stockout_day_flag` | SKU-门店-日缺货 |
| R009 | 总是 | `stockout_rate_6_22 = cnt/16` | 分母 16 已实测确认 |
| R010 | `sale_amount=0` | `sales_zero_flag` | 零销≠零需求 |
| R011/R012 | 总是 | 保留 `activity_flag`/天气 | 语义/单位未知，不解释 |

`DERIVED_SQL` 与 `clean_frame` 是同一套规则的 SQL/pandas 双实现（`cleaning.py:98-133`，A），用于保证“生产流水线”和“单测”口径一致。

### 3.1.4 流水线的 6 个阶段

`pipeline.run()`（`pipeline.py:74-169`，A）：

```
① verify_file（size + sha256）
② check_file_metadata（行/列/字段顺序/Arrow 类型）
③ _raw_checks（主键/空值/负值/日期范围/连续性）
④ build_clean_table（写 clean_train/clean_eval）
⑤ metrics.*（13 张派生表）
⑥ 写规则/指标/质量 JSON + RunLogger
```

任何一步失败都会抛异常并中止，不会“带病产出”。

### 3.1.5 测试与产物

- 测试：`tests/test_contracts.py`（4）、`test_cleaning.py`（4）、`test_metrics.py`（10），共 18（06 §15，A）。
- 产物：`clean_train` 4,500,000 行 / 51.97 MB；`clean_eval` 350,000 行 / 4.43 MB（06 附录 A）。
- 运行日志：`pipeline_20261107T230354-dfc848.jsonl`（15.94s）、`...0ad3fc`（15.38s）。

---

## 3.2 P1：销量经营状况（`analysis/p1.py`）

### 3.2.1 存在原因

回答四个问题：整体销量趋势如何？是否有异常日？门店之间差异多大？哪些门店持续低销？

### 3.2.2 输入/输出

- 输入：`agg_daily`、`agg_hour_profile`、`agg_hour_weekday`、`agg_store_day`、`agg_store_summary`、`agg_product_summary`、`clean_train`（A）。
- 输出：`data/analysis/p1/t1_daily.csv` 等 12 张表 + `summary.json` + 9 张 PNG。

### 3.2.3 关键流程

| 函数 | 作用 |
|---|---|
| `load_inputs` | 读取 7 张派生表 |
| `build_daily` | 7 日均线、日环比、稳健 z |
| `weekday_summary` | 星期效应 |
| `holiday_comparison` | 全样本 vs 仅工作日双口径 |
| `hour_summary` / `period_summary` | 小时份额、时段汇总 |
| `hour_weekday_matrix` | 7×24 矩阵 |
| `store_table` | 门店规模/效率 |
| `store_distribution` | P10/P25/P75/P90、Top10%/20% 份额、Spearman |
| `store_quartile_profile` | 四分位画像 |
| `daily_anomalies` / `store_cross_section_anomalies` / `store_day_anomalies` | 三类异常 |
| `sustained_low` | 连续低销 |

### 3.2.4 两个核心算法

**① 稳健 z（异常日）**（`p1.py`、`metrics.anomaly_days`，A）：

```
med = median(x)
mad = median(|x - med|)
robust_z = (x - med) / (1.4826 * mad)
|robust_z| > 3  → 异常日
```

为什么用中位数/MAD 而不是均值/标准差：销量日度分布长尾、有促销尖峰，均值/标准差会被异常值拉偏（B，属统计常识；文档明确采用了稳健 z，A）。

**② 持续低销**（`p1.py:256`，A）：

```
7 日滚动均值 < 0.7 × 该门店中位
且连续 ≥ 7 天
```

它回答的是“长期偏低”，不是“某天卖得少”。后续 P3-D 的 R3 复用这个规则，但独立复算了真实天数（见 3.7）。

### 3.2.5 测试

`tests/test_metrics.py` 覆盖日/小时/门店聚合；P1 的统计结果被后续测试间接锁定（如总指数 4,493,660.787）。

---

## 3.3 P2：商品经营分析（`analysis/p2.py`）

### 3.3.1 存在原因

回答：哪些 SKU 贡献最大？覆盖广度和单店效率是否矛盾？哪些 SKU 有风险（高波动/高零销/异常日/门店集中）？

### 3.3.2 关键函数

| 函数 | 作用 |
|---|---|
| `load_base` | SQL 计算 SKU 跨门店 HHI、序列内稳健异常、折扣分箱 |
| `add_sku_metrics` | 份额、累计份额、规模/效率排名差 |
| `pareto` | Top10%/20% 贡献 |
| `coverage_sensitivity` | 覆盖门槛 1–100 的排名稳定性 |
| `stability_tiers` | 零销率 × CV 四档 |
| `head_tail` | 头尾 SKU |
| `flag_anomalies` | 四个风险旗标 |
| `category_table` | L1/L2/L3 类别表 |

### 3.3.3 四个风险旗标（P2）

| 旗标 | 阈值 | 说明 |
|---|---|---|
| 高波动 `high_cv` | 序列 CV 中位 > P95（1.060） | 覆盖 ≥5 店 |
| 高零销 `high_zero` | 零销率 > P95（24.44%） | 与描述性 `zero_rate>20%`（65 个）不同 |
| 异常日频繁 `many_anomaly_days` | 异常日占比 >5% | 稳健 z>3.5 |
| 门店集中 `store_concentration` | 覆盖 ≥5 且 HHI > P95（0.184） | 单店 HHI 不误判 |

117 个 SKU 至少命中一个，35 个命中 ≥2 个（A：P2 报告、`v_sku_risk`）。

### 3.3.4 一个容易犯的错误：单店日均的分母

P2 审计发现 `per_series_day` 的分母是 **SKU-门店-日**，却被叫作“单店日均”，导致“C22 单店日均最高”在门店-日口径下不成立。修正后拆成两个指标（A：P2 审计/修正）：

- `category_sku_store_day_avg = 指数 / SKU-门店-日数`（原口径，改名）；
- `category_store_day_avg = 指数 / 门店-日数`（新增）。

这是“同名不同义”的典型案例，详见第五章问题 4。

---

## 3.4 P3-A：城市经营对比（`analysis/p3_city.py`）

### 3.4.1 输入/输出

- 输入：`clean_train`、`agg_city_summary`、`agg_store_summary`。
- 输出：`a1_city_metrics.csv`、`a2_city_category.csv`、`a3_city_store_distribution.csv`、`a4_city_category_long.csv` + 6 张图。

### 3.4.2 两个缺货口径

| 口径 | 公式 | 含义 |
|---|---|---|
| SKU-日缺货率 | 有缺货 SKU-日 / 总 SKU-日 | 商品维度 |
| 小时槽位缺货率 | 缺货小时 / (16 × SKU-日) | 时间维度 |

两者不可互换（P3-A 报告、P3-D 报告，A）。P3-A 中 `stockout_sku_day_rate` 是“城市内门店率简单平均”，而 P3-B/C/D 同名指标是“门店内比值”，这是历史遗留的命名冲突（详见第五章问题 8）。

### 3.4.3 小城市与 bootstrap

- 门店数 <10 的城市只展示、不排名（5 个）；
- Spearman 相关用 1,000 次 percentile bootstrap，`seed=42`；
- City 0（290 店）做敏感性对照。

---

## 3.5 P3-B：门店分层与四象限（`analysis/p3b_store.py`）

### 3.5.1 存在原因

门店规模不同，直接比“销量”不公平。需要一个“控制规模后的相对效率”，再做四象限。

### 3.5.2 模型

```
x = log(SKU 覆盖数)
y = log(1 + 单 SKU 日均指数)
拟合：Huber 稳健回归（RLM），M = 1.345
残差 eff_resid = 实际 y - 拟合 y
```

选择 Huber 而不是 OLS 的原因（B，由代码与文档推断）：门店中存在高影响点，OLS 会被拉偏；Huber 对异常值更稳健。代码同时跑了 OLS 与分位数回归做对照（`fit_ols`、`fit_quantreg`，A）。

### 3.5.3 四象限

- 规模轴：门店 `per_day_index` 的 P50；
- 效率轴：`eff_resid` 的 P50；
- 高/低以 `>P50` / `<=P50` 划分，边界并列归“低”；
- 结果：261 / 183 / 183 / 261（A：P3-B 报告）。

### 3.5.4 样本与敏感性

- 主样本 `SKU≥10`，888 家；10 家不参与；
- 门槛敏感性：≥5/≥10/≥20/≥30 → 897/888/808/681；
- 模型状态不是简单“通过/不通过”，而是 hard/soft 规则组合（CI 含 0、R²<0.10、残差分箱、OLS 斜率差、高影响占比、符号稳定性、象限一致率）。

### 3.5.5 一个命名问题

`R²_weighted=0.119...` 实际是“基于 RLM 最终权重的样本内加权拟合指数”，不是标准 R²。审计要求改称“弱拟合、仅探索性”（A：P3-B 审计）。这体现了一个重要原则：**统计量名称必须与定义一致**。

---

## 3.6 P3-C：门店商品结构（`analysis/p3c_structure.py`）

### 3.6.1 存在原因

同样规模的门店，商品结构可能完全不同：有的依赖头部 SKU，有的品类分散。需要量化“集中度”和“结构相似性”。

### 3.6.2 核心指标

| 指标 | 公式 | 含义 |
|---|---|---|
| SKU HHI | Σ(门店内 SKU 份额²) | 商品集中度 |
| 有效 SKU | 1 / HHI | 等效商品数 |
| 类别 HHI | Σ(类别份额²) | 类别集中度 |
| 类别熵 | -Σ p·ln p | 类别分散度 |
| Top1/Top5 份额 | 最大/前五 SKU 份额 | 头部依赖 |

### 3.6.3 十分位与聚类

- **十分位**：按 `sku_count` 排序后用 `np.array_split` 做“确定性等样本量”切分（89×8 + 88×2），避免 `qcut` 把相同 SKU 数的门店切到不同组（A：`p3c_structure.py:137`）。
- **聚类**：门店×类别份额矩阵 → L2 归一化 → Euclidean → Ward → `fcluster(k=4)`，输出 G1–G4；k=4 仅作展示，不是唯一解。
- **稳定性**：剔除稀有类别后计算 ARI 与距离相关；P3-C 报告 ARI=1.000（A）。

### 3.6.4 小样本

- 十分位统计 `n<20` 标“样本不足”；
- 稀有类别定义：覆盖 <10 店；
- 典型店抽样用固定 seed，且按 store_id 排序避免行序依赖。

---

## 3.7 P3-D：缺货与门店风险（`analysis/p3d_risk.py`）

### 3.7.1 存在原因

把“缺货、低销、零销、波动、异常日”统一成可筛选的风险标记，并回答“哪些门店同时命中多个域”。

### 3.7.2 R1–R8 定义（`p3d_risk.py:77-135`，A）

| 标记 | 指标 | 阈值 | 类型 |
|---|---|---|---|
| R1 缺货广度 | `stockout_sku_day_rate` | > 全样本 P90 | 运营域 |
| R2 缺货强度 | `stockout_hour_rate` | > 全样本 P90 | 运营域 |
| R3 持续低销 | `max_low_run_days` | ≥7 天 | 运营域 |
| R4 高零销 | `zero_rate` | > P90 | 运营域 |
| R5 高波动 | `cv` | > P90 | 运营域 |
| R6 高异常日 | `anomaly_rate` | > P90 | 运营域 |
| R7 覆盖偏窄 | `sku_count` | <= P10 | 结构提示 |
| R8 结构集中 | `sku_hhi` | 同 SKU 十分位内 >P90 | 结构提示 |

派生：

```
stockout_domain = R1 | R2
domain_count = 五个运营域求和
multi_risk = domain_count >= 2
```

风险样本 = `SKU≥10` 的 888 家；10 家 SKU<10 不诊断（A）。

### 3.7.3 精确组合与至少组合

**精确组合**（`p4_diagnosis.py:161-167`，A）：

```python
multi = risk[risk["domain_count"] >= 2]
exact = multi.groupby("exact_combo").size()
exact["definition"] = "恰好只命中这些域"
```

- 只统计 ≥2 个运营域的门店；
- `exact_combo` 是命中域标签用 `+` 连接；
- 结果 16 种，“缺货+高零销”38 家；
- 各行不可相加（同一门店只属于一个精确组合）。

**至少组合**（`p3d_risk.py` 共现、P4 `itertools.combinations`，A）：

- 对每家门店的命中域做两两组合；
- 语义“至少同时命中这两个域，允许其他域”；
- P3-D `d8b` 原表 15 行，其中 5 行是同域对角线；BI 视图 `WHERE domain_a <> domain_b` 后保留 10 对；
- “缺货+高零销”56 家。

两者关系：38 家是“只命中缺货和高零销”的门店；56 家是“至少命中这两个域”的门店，包含 38 家以及其他域的门店。**38 ⊂ 56，但不可相减当作“其他组合”**，因为组合维度不同（A/B）。

### 3.7.4 敏感性

P3-D 做了 P85/P90/P95 阈值、minSKU 5/20/30、城市内 P90、剔除 City 0 等敏感性分析（`sensitivity`，A）。这说明阈值不是“拍脑袋”，但也不是唯一正确。

### 3.7.5 两个修正

1. 整体缺货率从“城市加权率再按门店数二次加权”改为池化率：0.442668 / 0.198771（A：P3-D 修正）。
2. `max_low_run_days` 原为 P1 截断字段（1–6 天记 0），P3-D 用 `low_run_table` 独立复算真实最长天数，恢复 54 家（A）。

---

## 3.8 P4：经营诊断与决策支持（`analysis/p4_diagnosis.py`）

### 3.8.1 存在原因

P1–P3 是“分组分析”，P4 要把它们串成“门店档案 + 诊断 + 联动”三层，供 BI 直接消费。

### 3.8.2 P4-A 门店档案

`build_profile`（`p4_diagnosis.py:51-72`，A）：

- 以 P3-C `c1_store_structure.csv` 为主表；
- 合并 P3-D 的 R1–R8/domain_count/multi_risk；
- 合并 P3-C 的 G1–G4；
- 生成 `profile_status`：888 完整档案 / 10 基础档案（SKU<10）；
- 输出 42 个字段、898 行。

### 3.8.3 P4-B 门店诊断

`build_diagnosis`（`p4_diagnosis.py:118-176`，A）：

- 只对 888 风险样本生成诊断；
- `domain_labels`、`exact_combo`、`structural_notes`；
- 10 家不适用门店单独输出 `p4_b_not_applicable.csv`；
- 生成 `pairs`（至少组合）、`rulebook`（B0–S8）、`exact`（16 种）、`domain summary`；
- 规则手册明确禁止解释：`domain_count` 不是严重度评分，R7/R8 不进入运营域。

### 3.8.4 P4-C 联动

`build_linkage`（`p4_diagnosis.py:181-316`，A）：

| 输出 | 内容 | 行数 |
|---|---|---:|
| `p4_c_store_sku_incidence` | 门店×SKU 观察期内是否出现 | 50,000 |
| `p4_c_store_sku_risk_summary` | 门店风险 SKU 汇总 | 898 |
| `p4_c_flagged_sku_distribution` | 风险 SKU 覆盖分布 | 117 |
| `p4_c_category_risk_profile` | 类别风险画像 | 32 |
| `p4_c_sku_pair_cooccurrence` | 同店共同出现 | 1,237 |
| `p4_c_quadrant_cluster_cross` | 四象限×结构群 16 格 | 16 |

`sample_insufficient = stores < 20` 是 P4-C 的小样本标记（A）。

### 3.8.5 一个实现细节

`build_linkage` 内部用了 `inc.loc[s.index]` 的 lambda 做分组聚合（A）。它可读性较差、对索引对齐敏感，是潜在维护风险（B；第五章会作为设计风险列出）。

---

## 3.9 BI 后端（`bi/src/bi_api`）

### 3.9.1 冻结校验（`freeze.py`）

启动时 `verify_manifest()`：

1. 严格 JSON（重复 key 抛错）；
2. 拒绝绝对路径与 `..`；
3. 校验 SHA-256 格式（64 位十六进制）；
4. 校验文件存在、SHA 一致、bytes 一致；
5. 校验 amendment 的 `files_added` 与实际增量数一致。

结果：25/25 通过，`contract_version=bi0-contract-v2`（A：本轮实测）。

### 3.9.2 只读数据库（`db.py`）

```python
duckdb.connect(":memory:")
SET autoinstall_known_extensions=false
SET autoload_known_extensions=false
SET allowed_directories=['<data_root>']
SET enable_external_access=false
... 创建 25 个视图 ...
SET lock_configuration=true
```

`query_df` 额外守卫（`db.py:117-129`，A）：

- 空 SQL 拒绝；
- 多语句拒绝；
- 非 `SELECT/WITH` 拒绝；
- 写/DDL/文件函数正则拒绝（insert/update/drop/copy/read_csv/read_parquet/glob/httpfs 等）；
- `RLock` 串行化。

### 3.9.3 服务层（`service.py`）

关键逻辑：

| 函数 | 关键点 |
|---|---|
| `_store_where` | 城市/象限/结构群/风险域/精确组合/至少组合/样本范围 |
| `stores` | 排序白名单，非法回退 `store_id`；分页 |
| `store_groups` | n<20 时三个统计字段置 None + `suppressed=true` |
| `store_skus` | `COUNT(*) OVER()` 一次查询取总数 |
| `products` / `_product_where` | 搜索长度 ≤40、类别/头尾/风险白名单、覆盖区间 |
| `product_stores` | `total<20` → `suppressed=true` |
| `product_pairs` | 共现定义 + “非风险 SKU 无记录”警告 |
| `risk_summary` | n 固定 888 |
| `risk_combinations` | exact 用冻结 rank；at_least 服务端赋 rank |
| `export_stores_csv` | 4 行注释 + 23 列，内部 page_size=2000 |

### 3.9.4 路由层（`main.py`）

- `Literal` 限定排序、方向、风险域、组合定义；
- `page>=1`、`page_size<=200`；
- `ValueError → 400`，缺失 → 404；
- CORS 仅两个本地源、仅 GET；
- 导出设置 `Content-Disposition`。

### 3.9.5 已知缺口（A/B）

- 无鉴权、无限流；
- 单连接 + RLock，查询串行；
- `trend` 单侧日期参数会被静默忽略；
- CSV 导出不支持 `exact_combo/domains`，与页面筛选不完全对齐；
- CSV 未做公式注入转义（`=`/`+` 开头）；
- `/products` 默认 `scope=flagged` 依赖前端固定传参。

---

## 3.10 BI 前端（`bi/web/src`）

### 3.10.1 路由

`App.tsx` 实际 9 个业务路由 + 1 个 404 兜底（A）：

```
/ → /overview
/overview
/cities-stores
/products
/products/list
/products/risk
/products/categories
/products/:productId
/risk
/stores/:storeId
* → 页面不存在
```

与设计方案的 9 页相比：新增 3 个商品二级页，未建 `/explore`、`/methodology`。

### 3.10.2 URL 状态（`useUrlFilters.ts`）

```ts
get(key, fallback)
set(key, value)      // replace
patch(obj)           // 批量；任一非 page 键变化 → 删除 page
```

为什么用 URL 而不是全局 store（A：代码 + 09 §4.2）：

- 刷新可恢复；
- 可分享；
- 浏览器前进/后退天然可用；
- 不需要额外状态库。

### 3.10.3 返回状态（`navigation.ts` + `BackLink.tsx`）

`safeReturnTo` 的防线（`navigation.ts:37-62`，A）：

1. 长度 ≤500；
2. 必须以单个 `/` 开头，拒绝 `//`；
3. 拒绝反斜杠；
4. 路径穿越检测：原始 `..`、最多 5 次解码后的 `..`、残留 `%2e/%2f/%5c`；
5. `new URL` origin 校验；
6. 拒绝用户名/密码；
7. 白名单前缀 `/cities-stores`、`/risk`、`/products`、`/stores`；
8. 删除嵌套 `returnTo`，避免循环。

`BackLink`：

```tsx
const useHistory = Boolean(returnTo) && location.key !== 'default'
if (useHistory) { event.preventDefault(); nav(-1) }
```

- 有站内历史：后退，保留完整的“城市→门店→SKU”链路；
- 刷新/直达：跳到 `returnTo`；
- 两者都非法：默认页。

### 3.10.4 组件

| 组件 | 职责 |
|---|---|
| `DataTable` | 泛型表格、行点击、`rowClassName`、空态 |
| `Section` | 卡片标题/副标题/右侧操作 |
| `FilterSelect` | 下拉筛选 |
| `KpiCard` | KPI 卡 |
| `Badge` | 标签 |
| `Chart` | ECharts 封装（`animation:false`、`notMerge`） |
| `States` | Loading / ErrorBox / Empty / Suppressed |
| `ProductTable` / `ProductTabs` | 商品专用表格/页签 |
| `BackLink` | 多级返回 |

### 3.10.5 页面

| 页面 | 关键行为 |
|---|---|
| `OverviewPage` | 4 张图；KPI 固定 90 天，不随日期重算 |
| `CityStorePage` | 城市表全样本、散点受筛选、门店列表服务端分页 20 |
| `RiskPage` | 五域卡、精确/至少切换、冲突处理、选中行高亮、门店分页 |
| `StoreDetailPage` | 档案、R1–R8、SKU 列表、同类比较、复核清单 |
| `ProductOverviewPage` | 865/117/35、覆盖分布、头尾、类别 |
| `ProductListPage` | 全量列表、9 个筛选、搜索 |
| `ProductRiskPage` | 6 个 tab、43 vs 65 口径提示 |
| `ProductCategoryPage` | 32 类、SKU<20 标签 |
| `ProductDetailPage` | 覆盖门店、风险旗标、共现五态 |

---

## 3.11 端到端示例：从点击到 SQL

**场景**：在风险页选择“至少组合：缺货 + 高零销”。

1. 点击“至少同时命中”表格中的该行；
2. `RiskPage` 写入 `domains=stockout_domain,R4&combo=at_least`，清空 `exact_combo/domain`；
3. API 请求 `/api/v1/stores?domains=stockout_domain%2CR4&sample_scope=risk&page=1&page_size=20&sort=store_id`；
4. `service._store_where`：
   - 校验 `domains` 与 `risk_domain`/`exact_combo` 互斥；
   - 拆分两个码，确认都在 `{stockout_domain,R3,R4,R5,R6}`；
   - 追加 `stockout_domain IS TRUE AND R4 IS TRUE`；
   - 再追加 `in_risk_sample IS TRUE`；
5. DuckDB 在 `v_store` 上执行，返回 56 条中的第一页；
6. 页面副标题显示“当前筛选 56 家 · 至少组合：缺货 + 高零销”；
7. 点击门店行 → `/stores/<id>?returnTo=...`；
8. 返回时 `BackLink` 回退，56 家与组合保留。

对照：精确组合的 SQL 是 `exact_combo = ?`，返回 38 家。两条路径共用同一门店表，但筛选条件完全不同（A：`service.py:162-185`、C-2/C-3 E2E）。

---

## 3.12 异常与边界处理汇总

| 场景 | 实现 |
|---|---|
| 数据文件哈希不符 | 流水线中止 |
| manifest 被篡改 | API 拒绝启动 |
| 非法排序字段 | 回退默认排序，不报错 |
| 非法风险域/组合 | 400 |
| 单域/重复域/R7R8 进 domains | 400 |
| 空 domains | 400（C-4 收紧） |
| 门店/商品不存在 | 404 |
| n<20 | `suppressed=true`，前端 `—` |
| SKU<10 | 不诊断，风险字段 `—` |
| 共现全部低于 20 店 | 显示“共 5 对，均低于门槛”，不伪装成 0 |
| API 元数据缺失 | 显示“不可用”，不估算 |
| returnTo 非法 | 回退默认页 |

---

## 3.13 设计优点与不足

### 优点（A）

1. **契约先行**：数据、响应、冻结三层契约都有测试。
2. **口径显式**：精确/至少、池化/均值、SKU-日/小时槽位都在 UI 与文档中区分。
3. **可追溯**：每个数字能追到表/字段/规则。
4. **抑制而非补零**：小样本显示 `—`，不制造假精度。
5. **测试锁数字**：冻结数字被断言，回归时能立刻发现漂移。

### 不足（A/B）

1. **硬编码常量多**：898/888/865/117/35/43/16/10/38/56 散落前后端。
2. **前端无组件测试**：复杂交互主要靠 E2E。
3. **单连接串行**：多用户会排队。
4. **无缓存层**：重复请求多。
5. **部分历史口径残留**：P3-A 与 P3-B/C/D 的同名缺货率不同义。
6. **CSV 导出与页面筛选不完全对齐**。
7. **`build_linkage` 的索引 lambda 可读性差**。
8. **无 CI、无 Docker、无鉴权**。

---

## 3.14 本章证据等级

| 内容 | 等级 |
|---|---|
| 模块职责、函数名、行号 | A（源码） |
| 阈值与组合数字 | A（源码 + 冻结 CSV + 测试） |
| 为什么选 Huber/稳健 z | B（统计原理 + 代码使用） |
| 架构/模块划分动机 | B（文档有目标，未逐项比较） |
| 性能与扩展性判断 | B（代码结构 + 实测） |
| 未实现功能 | A（路由/目录/运行说明） |
