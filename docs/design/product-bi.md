# BI-2 商品 BI 前期方案设计与数据可行性分析报告

- 项目：中国数字零售与本地生活经营增长分析
- 阶段：BI-2 前期方案设计与数据可行性分析（**只调研、只核验、只设计，不写代码、不建页面、不改数据**）
- 日期：2026-11-08
- 前置状态：P1–P4、BI-0、BI-1 均已正式验收并 Feature Freeze
- 数据边界：仅使用已冻结的 P1–P4 分析结果与 BI-0 只读视图；未读取 eval；未重跑任何正式分析；未创建数据集

---

## 0. 结论摘要

| 问题 | 结论 |
|---|---|
| 现有数据是否足以支撑商品 BI | **是**。865 个 SKU 的基础指标、风险旗标、类别结构、门店覆盖、同店共同出现均有冻结结果 |
| 可直接实施的页面 | 商品总览、SKU 列表、SKU 详情、风险 SKU 视图、一级类别结构、同店共同出现 Top |
| 需新增只读视图 | `v_store_sku`（50,000 行 incidence）为必需；`v_category_l2/l3`、`v_sku_head_tail`、`v_sku_coverage_sensitivity`、`v_category_penetration` 为可选 |
| 需新增 API | 商品汇总、全量 SKU 列表（含搜索/筛选/排序）、SKU 详情扩展、SKU 覆盖门店、SKU 与全局共同出现查询、类别结构 |
| 不建议实施 | 价格/成本/利润、库存/补货、订单/客流、用户行为/复购、SKU 日趋势、全量 865×865 共现矩阵、因果或综合评分 |
| MVP | `/products`（总览 + 全量 SKU 列表 + 风险筛选 + L1 类别 + 共现 Top）+ `/products/:id`（指标 + 覆盖门店 + 共现），新增 1 个视图与 5 个接口 |

**关键前置条件**：`p4_c_store_sku_incidence.csv`（50,000 行）及 `t5/t6/t7/t8`、`c3` **不在 BI-0 冻结清单的 22 个文件内**。商品 BI 要展示 SKU→门店覆盖，必须先通过正式的 BI-0 契约增量修订把这几个文件纳入 SHA-256 登记；本轮不得修改 BI-0 文件。

---

## 一、现有商品数据资产清单

### 1.1 P2 商品经营结果

| 文件 | 形状（行×列） | 内容 | 冻结登记 |
|---|---:|---|---|
| `p2/t1_sku_metrics.csv` | 865×40 | SKU 全量基础指标、贡献、排名、集中度、4 个风险旗标 | 是 |
| `p2/t9_sku_risk_flags.csv` | 117×14 | 命中 ≥1 个风险旗标的 SKU | 是 |
| `p2/t4_category_l1.csv` | 32×19 | 一级类别汇总 | 是 |
| `p2/t5_category_l2.csv` | 84×19 | 二级类别汇总 | 否 |
| `p2/t6_category_l3.csv` | 233×19 | 三级类别汇总 | 否 |
| `p2/t7_coverage_sensitivity.csv` | 8×7 | 覆盖门槛敏感性（1→100 店） | 否 |
| `p2/t8_head_tail.csv` | 2×7 | 头部 Top20% / 长尾 Bottom50% 对比 | 否 |
| `p2/t2_top20_scale.csv`、`t3_top20_efficiency.csv` | 各 20×7 | 规模/效率 Top20 | 否 |
| `p2/map_product.csv` | 865×2 | `raw_id ↔ Pxxxx` 展示编码 | 否 |
| `p2/summary.json` | — | 覆盖、帕累托、风险阈值与计数 | 否 |

### 1.2 P4-C `store×SKU` 关联结果

| 文件 | 形状 | 内容 | 冻结登记 |
|---|---:|---|---|
| `p4/p4_c_store_sku_incidence.csv` | **50,000×17** | 全量 store×SKU 关联：覆盖天数、指数、零销天、缺货天、4 旗标 | **否** |
| `p4/p4_c_store_sku_risk_summary.csv` | 898×17 | 门店级 SKU 风险摘要（store 粒度） | 是 |
| `p4/p4_c_flagged_sku_distribution.csv` | 117×13 | 风险 SKU 覆盖、份额、旗标 | 是 |
| `p4/p4_c_category_risk_profile.csv` | 32×12 | 一级类别风险画像 | 是 |
| `p4/p4_c_sku_pair_cooccurrence.csv` | 1,237×6 | **风险 SKU 之间**观察期内同店共同出现 | 是 |
| `p4/summary.json` | — | 50,000 / 117 / 35 / 1,237 等总量 | 否 |

### 1.3 P3-C 商品结构结果

| 文件 | 形状 | 内容 | 冻结登记 |
|---|---:|---|---|
| `p3c/c3_category_penetration.csv` | 32×8 | 一级类别渗透：覆盖门店、平均/中位份额、中位 SKU 数、rare | 否 |
| `p3c/c2_store_category.csv` | 13,040×7 | 门店×一级类别份额 | 否 |
| `p3c/c1_store_structure.csv` | 898×多列 | 门店结构指标（SKU HHI 等，门店维度） | 否（BI-1 未直接读取；门店结构字段已在 P4-A） |

### 1.4 BI-0 现有只读视图（与商品相关）

| 视图 | 源 | 行数 | 现状 |
|---|---|---:|---|
| `v_sku` | P2 `t1` | 865 | 仅被 `/overview/kpis` 用于计数，未用于商品查询 |
| `v_sku_risk` | P2 `t9` | 117 | 已注册，未被 service 使用 |
| `v_flagged_sku` | P4-C flagged distribution | 117 | `/products`、`/products/{id}` 的唯一数据源 |
| `v_sku_pairs` | P4-C pairs | 1,237 | 已注册，无 API 暴露 |
| `v_category_risk` | P4-C category risk | 32 | 已注册，无 API 暴露 |
| `v_category` | P2 `t4` | 32 | 仅用于 `/meta/filters` 的类别下拉 |
| `v_store_sku_summary` | P4-C store summary | 898 | 门店维度，不是 SKU→门店明细 |

**缺口**：没有 `v_store_sku`（incidence）视图，也没有 `t5/t6`、`t7/t8`、`c2/c3` 视图。商品 BI 的"SKU 覆盖哪些门店"目前无法通过 BI 层回答。

来源：[db.py#L95-L110](../../bi/src/bi_api/db.py#L95-L110)。

### 1.5 现有 API 能力

| 端点 | 当前能力 | 是否满足商品 BI |
|---|---|---|
| `GET /api/v1/products` | 仅 117 个风险 SKU；10 字段；仅按一级类别过滤；固定排序；分页 ≤200 | **不满足**：无法浏览 865 个 SKU、无搜索/覆盖区间/指标排序 |
| `GET /api/v1/products/{id}` | 仅风险 SKU 可查到；10 字段 | **不满足**：非风险 SKU 返回 404，缺规模/效率/零销/CV/HHI/旗标组合 |
| `GET /api/v1/meta/filters` | 城市、象限、结构群、一级类别 | **部分满足**：可复用一级类别下拉 |
| `GET /api/v1/meta/catalog` | 指标字典 + 页面映射 | **部分满足**：字典缺 SKU 级指标，需要扩充 |
| `GET /api/v1/stores/{id}` | 门店详情 | 可复用：SKU 覆盖门店下钻到门店详情 |
| `GET /api/v1/export/stores.csv` | 门店导出 | 与商品无关，不扩展 |

来源：[main.py#L125-L140](../../bi/src/bi_api/main.py#L125-L140)、[service.py#L212-L240](../../bi/src/bi_api/service.py#L212-L240)。

**结论**：商品 BI 目前**没有可直接复用的完整商品 API**，只能复用类别下拉、门店详情跳转与只读数据层。

---

## 二、商品指标及其口径字典

> 统一约束：`sale_amount` 一律称"归一化销量指数"，不得称销售额、GMV、收入；所有比例均给出分母；观察期固定 2024-03-28 至 2024-06-25，共 90 天；样本为全部 898 家门店（商品口径不套用 888 门店风险样本）。

### 2.1 SKU 级基础指标（`t1_sku_metrics.csv`）

| 指标 | 定义 / 公式 | 分母 | 观察期 | 样本 | 备注 |
|---|---|---|---|---|---|
| `total_index` | Σ `sales_index` | — | 90 天 | 865 SKU / 898 店 | 归一化销量指数合计 |
| `store_count` | 去重门店数 | — | 90 天 | — | 覆盖门店数；中位 10、P90 173.6、最大 783 |
| `series_days` | 门店×SKU×日 序列行数 | — | 90 天 | — | 已核验 = `store_count × 90` |
| `per_series_day` | `total_index / series_days` | 序列-日 | 90 天 | — | 单店日均指数（效率口径） |
| `active_day_rate` | 有销量行 / `series_days` | 序列-日 | 90 天 | — | 与 `zero_rate` 互补 |
| `zero_rate` | 零销 SKU-日 / `series_days` | 序列-日 | 90 天 | — | 已核验 = 1 − `active_day_rate` |
| `stockout_day_rate` | 缺货 SKU-日 / `series_days` | 序列-日 | 90 天 | — | 商品侧缺货广度 |
| `promo_rate` | 促销行 / `series_days` | 序列-日 | 90 天 | — | 促销覆盖比例，不等于价格 |
| `cv_series_median` | 各门店序列 CV 的中位数 | 序列 | 90 天 | — | 避免跨店结构影响 |
| `hhi` | Σ(门店销量份额²) | — | 90 天 | 覆盖≥5 才有意义 | `effective_stores = 1/hhi` |
| `anomaly_rate` | 异常日数 / `n_days` | SKU 观察行 | 90 天 | — | 异常日：序列内稳健 z>3.5 |
| `total_share_pct` | SKU 指数 / 全链指数 | 865 SKU 合计 | 90 天 | — | 贡献份额 |
| `cum_share_pct` | 按规模降序累计份额 | 同上 | 90 天 | — | 帕累托 |
| `rank_scale` | 规模排名 | 865 | 90 天 | — | P2 冻结排名 |
| `rank_eff_all` | 效率排名（全量） | 865 | 90 天 | — | 全量榜 |
| `rank_eff_cov5` | 效率排名（覆盖≥5） | 540 | 90 天 | — | 325 个 SKU 为空 |
| `stability_tier` | 零销×CV 四档 | — | 90 天 | — | 343 / 342 / 90 / 90 |

### 2.2 SKU 风险旗标（`t9_sku_risk_flags.csv`）

| 旗标 | 阈值 | 计算范围 | 命中数 |
|---|---|---|---:|
| `flag_high_cv` | `cv_series_median > 1.060`（P95） | 全部 865 | 44 |
| `flag_high_zero` | `zero_rate > 24.44%`（P95） | 全部 865 | 43 |
| `flag_many_anomaly_days` | `anomaly_rate > 5%` | 全部 865 | 50 |
| `flag_store_concentration` | 覆盖≥5 且 `hhi > 0.184`（P95） | 覆盖≥5 | 27 |
| `risk_flag_count` | 上述命中数 | — | 117 个 ≥1；82×1、23×2、12×3 |
| 多风险 SKU | `risk_flag_count ≥ 2` | — | **35** |

> **口径更正（2026-11-08）**：`flag_high_zero` 是 P2/P4-C 冻结风险旗标，阈值为 `zero_rate > P95 = 24.44%`，命中 **43** 个 SKU；此前表格误写为 65。65 对应另一个描述性口径 `zero_rate > 20%`（不属于风险旗标），两者不可互相替代。以 `t9_sku_risk_flags.csv` 与 `/api/v1/products?risk=high_zero` 实际返回的 43 为准。

**旗标组合分布（117 个，展示层直接拼接，不新增统计量）**：

| 组合 | SKU 数 |
|---|---:|
| 异常日频繁 | 27 |
| 门店集中 | 27 |
| 高零销 | 19 |
| 高波动+高零销+异常日频繁 | 12 |
| 高波动+高零销 | 12 |
| 高波动+异常日频繁 | 11 |
| 高波动 | 9 |

> 术语提醒：此处的"多风险 SKU（35）"是**商品四旗标 ≥2**，与 BI-1 的"多风险门店（132）"（运营风险域 ≥2）不是同一概念，页面必须分别命名。

### 2.3 SKU×门店指标（`p4_c_store_sku_incidence.csv`）

| 字段 | 定义 | 备注 |
|---|---|---|
| `store_id` / `product_id` | 门店 / SKU | 50,000 个唯一组合 |
| `days_present` | 该组合出现天数 | 实测全部 = 90 |
| `observed_rows` | 观察行数 | 实测全部 = 90 |
| `total_index` | 该店该 SKU 的指数合计 | 按 SKU 汇总与 `t1.total_index` 完全一致 |
| `zero_days` | 零销天数 | 按 SKU 汇总后与 `t1.zero_rate` 完全一致 |
| `stockout_days` | 缺货天数 | 商品-门店缺货广度 |
| `is_flagged` / `is_multi_flag` | SKU 旗标透传 | 不重新判定 |

**一致性核验（本轮实测）**：`store_count` 不一致 0 个；`total_index` 最大差 0.0；`zero_rate` 最大差 0.0；`series_days = store_count×90` 不一致 0 个。

### 2.4 同店共同出现（`p4_c_sku_pair_cooccurrence.csv`）

| 字段 | 定义 |
|---|---|
| `product_a` / `product_b`、`sku_a` / `sku_b` | SKU 对 |
| `stores_both` | 观察期内同时上架该两个 SKU 的门店数 |
| `share_stores_both` | `stores_both / 898` |

- 范围：**仅 117 个风险 SKU 之间**，共 1,237 对；
- 统一定义：**两个均为 P2 flagged SKU，且在观察期内同时进入同一门店的商品集合**（简称"观察期内同店共同出现"）；
- 不代表：同日销售、同日缺货、同时缺货、消费者购买搭配关系、商品间因果关系；
- 分布：`stores_both ≥20` 仅 118 对，`≥10` 193 对，`≥5` 360 对；Top 对为 P0005+P0601（440 店，49.0%）。

### 2.5 类别指标

| 层级 | 指标 | 来源 |
|---|---|---|
| L1/L2/L3 | `sku_count`、`store_count`、`total_index`、`share_pct`、`category_store_day_avg`、`category_sku_store_day_avg`、`sku_store_day_zero_rate`、`sku_cv_median`、三个冻结排名 | `t4/t5/t6` |
| L1 渗透 | `stores`、`avg_share`、`median_share`、`median_sku`、`coverage`（stores/898）、`rare` | `c3` |
| L1 风险 | `n_flagged_skus`、`n_multi_flag_skus`、`flagged_sku_share`、`flagged_total_index_share`、`flagged_store_coverage` | `p4_c_category_risk_profile` |

**类别规模约束**：L2 有 72/84 个类别 `sku_count<20`；L3 有 231/233 个 `sku_count<20`、75 个 `store_count<20`。因此 **L2/L3 只适合做"该类包含哪些 SKU"的浏览，不适合做类间平均比较**。

---

## 三、商品 BI 页面结构与功能设计

### 3.1 信息架构

```
导航：商品 BI
  /products        商品经营总览 + SKU 列表 + 类别结构 + 同店共同出现
  /products/:id    SKU 详情（指标、旗标、覆盖门店、共同出现）
```

不单独新建"商品风险页"：117 个风险 SKU 是 865 个 SKU 的子集，独立成页会与 SKU 列表重复。风险分析以**筛选 + 风险概览带 + 旗标组合卡**的形式内嵌在 `/products`。

### 3.2 `/products` 区块设计

| 区块 | 内容 | 图表/组件 | 交互 | 数据 |
|---|---|---|---|---|
| A 商品概览 | 865 SKU；50,000 store×SKU；覆盖中位 10；Top10% 贡献 72.30%；122 SKU 贡献 80%；117 风险 SKU（13.5%）；35 多风险 SKU（4.0%） | 7 个 KPI 卡 | 点击风险卡→筛选风险 SKU | `t1/t9/summary` |
| B 贡献与长尾 | 帕累托曲线（排名 vs 累计份额）+ 头部/长尾对比表 | 折线 + 2 行表 | 点击曲线点→SKU 详情 | `t1`、`t8` |
| C 覆盖分布 | 7 个覆盖区间柱状图 + 中位/P90/最大；标注 150 个单店 SKU、509 个 <20 店 SKU | 柱状图 | 点击柱→覆盖区间筛选 | `t1` |
| D SKU 列表 | 865 个 SKU，分页 50；列：编号/一级类别/覆盖/累计指数/贡献/单店日均/零销/CV/HHI/风险旗标/规模排名 | 表格 + 搜索 + 排序 | 搜索、筛选、排序、行点击→详情 | `t1/t9` |
| E 风险商品带 | 117/35/12 计数；7 种旗标组合分布；多风险 SKU 表 | 小卡 + 表 | 旗标组合点击→筛选 | `t9` |
| F 类别结构 | L1 32 行：SKU 数、覆盖、份额、零销、CV、风险 SKU 数、风险份额、渗透率 | 表格 | 行点击→按类别筛选；L2/L3 二期 | `t4`、`p4_c_category_risk_profile`、`c3` |
| G 同店共同出现 | 默认 `stores_both ≥20` 的 118 对，Top 20；可切换全量 1,237 | 表格 | 点击 SKU→详情；切换阈值 | `p4_c_sku_pair_cooccurrence` |

页面固定提示："共现指两个均为 P2 flagged SKU，且在观察期内同时进入同一门店的商品集合；不代表同日销售、同日缺货、同时缺货、购买搭配或因果关系。"

### 3.3 `/products/:id` 区块设计

| 区块 | 内容 | 数据 |
|---|---|---|
| 头部 | Pxxxx、一级/二级/三级类别、4 个风险旗标 | `t1/t9` + 类别映射 |
| 核心指标 | 累计指数、贡献份额、覆盖门店（n/898）、单店日均、零销率、CV、HHI/有效门店数、异常率、缺货率、促销率、规模/效率排名 | `t1` |
| 贡献位置 | 规模排名、效率排名（覆盖<5 时效率排名显示"—"）、头部/长尾归属 | `t1` |
| 覆盖门店分布 | 按城市 18 行汇总（覆盖门店数、指数合计、零值门店数）；按四象限/结构群汇总仅限 888 风险样本并标注 | `incidence + v_store`（派生汇总） |
| 覆盖门店列表 | 分页 50：门店、城市、象限、结构群、该店指数、零销天、缺货天、是否带风险旗标；点击→门店详情 | `incidence` |
| 同店共同出现 | 若为风险 SKU：Top 20 对；否则显示"共同出现分析仅覆盖 117 个风险 SKU" | `pairs` |

### 3.4 不建议采用的页面方向

| 方向 | 原因 |
|---|---|
| 独立"商品风险 BI"页 | 与 SKU 列表重叠，117 行无需独立路由 |
| 商品价格带/毛利分析页 | 无价格、成本、利润数据 |
| 商品库存/补货页 | 只有缺货标记，无库存量、在架、补货记录 |
| 商品用户/复购页 | 无用户、订单、交易数据 |
| 商品销售趋势页 | 冻结结果无 SKU×日序列；需从原始行级数据重新聚合，超出 BI 复用边界 |
| 865×865 全量共现网络 | 现有 pairs 仅覆盖 117 个风险 SKU；全量需新增 O(n²) 计算 |

---

## 四、页面组件与现有数据源映射

| 页面 | 组件 | 数据源 | 现有/新增 | 说明 |
|---|---|---|---|---|
| `/products` | 概览 KPI | `v_sku`、`v_flagged_sku` | 现有视图 + 新汇总 API | 服务端一次聚合，不传 865 行 |
| `/products` | 帕累托曲线 | `v_sku`（`rank_scale`、`total_share_pct`、`cum_share_pct`） | 新 API | 865 点，一次返回 |
| `/products` | 头部长尾表 | `t8` | 需新视图 `v_sku_head_tail` 或 API 内置常量查询 | 2 行 |
| `/products` | 覆盖分布 | `v_sku.store_count` | 新汇总 API | 服务端分桶 |
| `/products` | SKU 列表 | `v_sku` + `v_sku_risk` | 新 API（扩展 `/products`） | 分页 50 |
| `/products` | 风险商品带 | `v_sku_risk` | 新 API | 117 行 |
| `/products` | L1 类别结构 | `v_category` + `v_category_risk` + `v_category_penetration` | 现有 2 个 + 新 1 个视图 | 32 行 |
| `/products` | 共同出现 Top | `v_sku_pairs` | 新 API | 1,237 行，分页/阈值 |
| `/products/:id` | 指标卡 | `v_sku` | 新 API（扩展详情） | 1 行 |
| `/products/:id` | 风险旗标 | `v_sku_risk` | 新 API | 1 行 |
| `/products/:id` | 覆盖门店列表 | `v_store_sku` + `v_store` | **新视图 + 新 API** | 50,000 行 |
| `/products/:id` | 城市分布 | `v_store_sku` + `v_store.city_id` | 新视图 + 新 API | 18 行 |
| 全部 | 类别下拉 | `v_category`（经 `/meta/filters`） | 现有 API 复用 | 一级类别 |

与 BI-0 `page_table_map.csv` 的对应关系：`sku_pareto`、`hhi_distribution`、`category_structure`、`risk_sku_table`、`sku_pairs` 五项已在冻结映射中登记（[page_table_map.csv](../../bi/data/page_table_map.csv#L13-L17)），本方案与其一致，仅把 `hhi_distribution` 调整为"SKU 集中度"口径并在 SKU 详情呈现。

---

## 五、现有 API 复用情况及新增接口建议

### 5.1 复用

| 能力 | 复用方式 |
|---|---|
| 类别下拉 | `/api/v1/meta/filters` 已返回一级类别 32 个 |
| 指标字典/页面映射 | `/api/v1/meta/catalog`，需扩充 SKU 指标条目 |
| 门店详情 | 覆盖门店列表行点击跳转 `/stores/{store_id}` |
| 只读数据层 | 继续使用 `ReadOnlyDB`，不引入新数据库或外部访问 |

### 5.2 新增/扩展（设计建议，不在本轮实施）

| # | 端点 | 类型 | 参数 | 返回 | 说明 |
|---|---|---|---|---|---|
| A1 | `GET /api/v1/products/summary` | 新增 | — | 7 个 KPI + 覆盖分桶 + 旗标计数 | 服务端聚合，避免传输 865 行 |
| A2 | `GET /api/v1/products` | **扩展** | `scope=flagged|all`、`q`、`category_l1`、`risk`、`coverage_min/max`、`sort`、`page`、`page_size` | 12–15 字段/行 | **默认保持 `scope=flagged`（117）以兼容 BI-1 测试**，页面显式传 `scope=all` |
| A3 | `GET /api/v1/products/{id}` | **扩展** | — | `t1` 全字段 + 类别 + 旗标组合 | 非风险 SKU 不再 404 |
| A4 | `GET /api/v1/products/{id}/stores` | 新增 | `page`、`page_size`、`sort=total_index|zero_days` | 门店覆盖分页 | 依赖 `v_store_sku` |
| A5 | `GET /api/v1/products/{id}/pairs` | 新增 | `limit` | 该 SKU 的共现对 | 仅风险 SKU 有数据 |
| A6 | `GET /api/v1/products/pairs` | 新增 | `min_stores_both`、`product_id`、`page` | 共现对分页 | 默认 `min_stores_both=20` |
| A7 | `GET /api/v1/categories` | 新增 | `level=1|2|3` | 类别指标 + 风险 + 渗透 | L2/L3 需新视图 |

**路由顺序**：`/products/summary`、`/products/pairs` 必须在 `/products/{product_id}` 之前注册，否则会被路径参数捕获。

### 5.3 需新增的只读视图

| 视图 | 源 | 必要性 |
|---|---|---|
| `v_store_sku` | `p4_c_store_sku_incidence.csv` | **必需**（SKU→门店覆盖） |
| `v_category_l2` | `t5_category_l2.csv` | 可选（L2 下钻） |
| `v_category_l3` | `t6_category_l3.csv` | 可选（L3 下钻） |
| `v_sku_head_tail` | `t8_head_tail.csv` | 可选（可改为 API 常量） |
| `v_sku_coverage_sensitivity` | `t7_coverage_sensitivity.csv` | 可选（覆盖门槛说明） |
| `v_category_penetration` | `p3c/c3_category_penetration.csv` | 可选（类别渗透） |

不新增任何派生数据集文件；全部通过 DuckDB 只读视图查询冻结 CSV。

---

## 六、筛选、排序、搜索与下钻交互可行性

| 交互 | 可行性 | 实现方式 | 性能证据 | 备注 |
|---|---|---|---|---|
| SKU 编码搜索（Pxxxx） | 可 | `LIKE '%q%'` + 865 行 | 47.6 / 52.3 ms | 不支持模糊语义搜索 |
| 一级类别筛选 | 可 | `first_category_id` 关联 `v_category` | 60.7 / 68.0 ms | 类别下拉复用现有 API |
| 二级/三级类别筛选 | 需新增视图 | `v_category_l2/l3` | 未测（84/233 行，预计 <60ms） | 二期 |
| 风险类型筛选 | 可 | 4 个布尔旗标 + `risk_flag_count` | 13 ms（117 行） | 多选组合 |
| 覆盖门店区间 | 可 | `store_count BETWEEN` | 51.8 / 47.5 ms | 区间为左闭右闭，需在页面标注 |
| 按贡献/零销/CV 排序 | 可 | 白名单列 SQL 排序 | 45–58 ms | 禁止任意列名拼接 |
| SKU 详情 | 可 | 扩展 `/products/{id}` | 现有查询 <15 ms | 非风险 SKU 需解除 404 |
| SKU→覆盖门店 | 可，需新视图 | `v_store_sku` + 分页 | 单 SKU 过滤 77 ms（warm） | 最大 783 行，必须分页 |
| SKU→城市覆盖汇总 | 可，需新视图 + Join | `v_store_sku` × `v_store` | 105.8 / 113.8 ms | 派生汇总，需在字典登记 |
| 同店共同出现查询 | 可（有限范围） | `v_sku_pairs` + 过滤 | 18.5–20.8 ms | 仅 117 个风险 SKU，1,237 对 |
| 共同出现阈值切换 | 可 | `stores_both >= N` | 同上 | 默认 ≥20（118 对） |
| 点击类目→筛选 SKU | 可 | 前端写 URL 参数 | 同类别筛选 | 复用 URL 状态模式 |
| SKU→门店详情 | 可 | 复用 `/stores/{id}` | — | 已验收页面 |
| SKU 日趋势 | **不可** | — | — | 无冻结 SKU×日表 |
| 商品价格/毛利下钻 | **不可** | — | — | 无数据 |

---

## 七、小样本抑制与数据安全设计

### 7.1 小样本规则（沿用 n<20）

| 对象 | 规则 |
|---|---|
| SKU 行本身 | 不隐藏、不抑制；865 个 SKU 均可见（SKU 是总体成员，不是组估计） |
| 覆盖 <5 店的 SKU（325 个） | 效率排名 `rank_eff_cov5` 显示"—"；不显示"效率领先"等标签；保留 P2 全量排名作参考 |
| 覆盖 <20 店的 SKU（509 个） | 展示"覆盖 n<20，比例类指标不稳定"徽标；不参与任何跨 SKU 分位/对比；排序仅按冻结指标，不生成新分位 |
| 单店 SKU（150 个） | 明确标注"仅 1 家门店，HHI=1 无意义"，不展示集中度结论 |
| 同店共同出现 | `stores_both <20` 默认不进入主表；切换全量时标注"n<20 仅计数，不作比较" |
| 类别 L2/L3 | `sku_count<20` 时标注"该类 SKU 不足 20，仅浏览、不比较" |
| 类别 L1 中 `sku_count=1` 的类别 | 单独标注"仅 1 个 SKU" |
| 门店/城市组对比 | 继续执行 BI-1 的 n<20 抑制，不在商品页重复实现组统计 |

### 7.2 数据安全

| 项 | 设计 |
|---|---|
| 查询层 | 继续 `ReadOnlyDB`：仅 SELECT/CTE、禁多语句、禁写/DDL、禁文件函数、`enable_external_access=false` |
| 排序注入 | 排序列白名单：`total_index`、`store_count`、`zero_rate`、`cv_series_median`、`hhi`、`risk_flag_count`、`rank_scale`、`rank_eff_all` |
| 分页 | `page_size ≤200`；列表默认 50；共现默认 50；覆盖门店默认 50 |
| 导出 | MVP 不提供 SKU 级 CSV 导出，避免明细外流与口径误用 |
| 展示 | 只用 Pxxxx/Cxx/Sxxxx 编码，不虚构商品名、品牌、条码、价格 |
| 缓存 | 不落盘、不新建派生数据；如需缓存仅在进程内且只读 |

### 7.3 数据契约前置条件（重要）

BI-0 冻结清单共 22 个文件，商品相关仅登记 7 个（`t1`、`t9`、`t4`、store summary、flagged distribution、category risk、pairs）。以下文件**未登记 SHA-256**：

- `p4_c_store_sku_incidence.csv`（SKU→门店必需）
- `t5_category_l2.csv`、`t6_category_l3.csv`、`t7_coverage_sensitivity.csv`、`t8_head_tail.csv`
- `p3c/c3_category_penetration.csv`、`c2_store_category.csv`

**建议**：BI-2 启动时先执行一次 **BI-0 契约增量修订（v2）**，只追加文件与哈希，不改动现有 22 项；否则商品 BI 会直接读取未受冻结保护的文件，无法通过验收。该修订属于 BI-0 变更，需要单独授权，本轮不执行。

---

## 八、性能风险与优化建议

### 8.1 实测数据（本机，只读）

| 查询 | 行数 | 冷启动 | 热查询 |
|---|---:|---:|---:|
| `v_sku` 全量（40 列） | 865 | 51.8 ms | 51.0 ms |
| SKU Top50（按指数） | 50 | 57.6 ms | 49.3 ms |
| SKU 过滤 + 排序 | 50 | 45.3 ms | 47.0 ms |
| SKU 编码搜索 `LIKE` | 19 | 47.6 ms | 52.3 ms |
| 覆盖区间筛选 | 50 | 51.8 ms | 47.5 ms |
| L1 类别聚合（`v_sku` JOIN `v_category`） | 32 | 60.7 ms | 68.0 ms |
| `v_flagged_sku` 全量 | 117 | 13.3 ms | 12.9 ms |
| `v_sku_pairs` Top50 | 50 | 18.5 ms | 20.8 ms |
| 单 SKU 共现过滤 | 110 | 20.8 ms | 19.2 ms |
| incidence 单 SKU 过滤（DuckDB CSV） | 783 | 3439.8 ms（首次嗅探） | **77.0 ms** |
| incidence 按 SKU 聚合 | 865 | 64.6 ms | 68.5 ms |
| incidence 关联门店城市 | 18 | 105.8 ms | 113.8 ms |
| pandas 读取 incidence + groupby（参考） | 50,000 | 68.5 ms + 5.7 ms | — |

### 8.2 传输体积

| 场景 | JSON 体积 |
|---|---:|
| SKU 列表 50 行（11 字段） | 12.5 KB |
| 全量 865 行（11 字段） | 208.7 KB |
| 共现全量 1,237 行 | 138.6 KB |
| 单 SKU 覆盖门店 783 行 | 84.0 KB |

### 8.3 结论与建议

1. **50,000 行完全够用**：它是全量 store×SKU 组合（865 个 SKU 的 `store_count` 之和恰为 50,000），不是抽样；单 SKU 过滤热查询 77 ms。
2. **不需要新增派生数据集或预聚合**。现有 CSV + DuckDB 只读视图满足交互延迟；仅在 p95 超过 300 ms 时才考虑进程内缓存（无落盘）。
3. **必须分页**：SKU 列表、共现、覆盖门店均分页 50；禁止一次返回 865 行（209 KB）或 783 行（84 KB）。
4. **汇总放服务端**：概览 KPI、覆盖分桶、旗标计数由 SQL 聚合返回，避免前端拉全表。
5. **首查开销**：incidence 首次扫描约 3.4 s（CSV 嗅探），建议在应用启动时创建视图并预热一次；之后稳定在 70–115 ms。
6. **字段裁剪**：`t1` 有 40 列，列表只取 12–15 列，详情再返回全量。
7. **不引入缓存层**：BI-1 性能基线（页面 <1.1 s、API <315 ms）已达标，商品页预计同量级。

---

## 九、无法实现的功能及数据原因

| 功能 | 是否可做 | 原因 |
|---|---|---|
| 商品销售额 / GMV / 收入 | 否 | 只有归一化销量指数，无金额 |
| 价格带、折扣金额、毛利、利润 | 否 | 无价格、成本、利润字段；`avg_valid_discount` 是促销折扣属性，不是价格 |
| 库存量、在架率、补货建议 | 否 | 仅有缺货标记，无库存与补货记录 |
| 订单数、客单价、客流、转化率 | 否 | 无订单/交易/客流数据 |
| 用户购买行为、复购率、用户价值 | 否 | 无用户标识与购买链路 |
| 同日关联销售 / 购物篮分析 | 否 | 共同出现仅按"同店、90 天"计算，无同日订单 |
| SKU 日/周销售趋势 | 否 | 冻结结果无 SKU×日序列表；需重新聚合原始行级数据，超出 BI 复用边界 |
| 全量 865×865 共现矩阵 | 否 | 现仅 117 个风险 SKU 的 1,237 对；全量属新增 O(n²) 分析 |
| 商品综合评分 / 排名 | 否 | 违反"不生成未经定义排名"；只复用 P2 冻结排名 |
| 因果结论（如"缺货导致销量下降"） | 否 | 无实验/因果识别设计 |
| 商品-城市销量拆分 | 有限可做 | 可由 incidence 按城市汇总，但属**派生汇总**，需新增字典定义并标注，不参与 P2 排名；建议二期 |
| 商品-门店四象限/结构群分布 | 有限可做 | 同上，仅限 888 风险样本并标注 |

---

## 十、BI-2 推荐实施范围、开发顺序与验收标准

### 10.1 推荐范围

**MVP（建议本轮之后的第一批实施）**

1. `/products`：概览 KPI、帕累托、覆盖分布、SKU 列表（搜索/类别/风险/覆盖区间/排序/分页）、L1 类别结构、共现 Top（默认 ≥20 店）。
2. `/products/:id`：核心指标、风险旗标与组合、覆盖门店列表（分页）、共现 Top（仅风险 SKU）。
3. 新增视图：`v_store_sku`。
4. 新增/扩展 API：A1、A2（默认兼容 117）、A3、A4、A5、A6。
5. 指标字典补充 SKU 级条目；页面映射补充商品页。

**二期（不在 MVP）**

- L2/L3 类别下钻；
- 覆盖门槛敏感性图（t7）；
- 城市/象限维度的 SKU 覆盖汇总；
- 商品页导出；
- 任意 SKU 对的共现查询（需新增计算）。

### 10.2 开发顺序

| 步骤 | 内容 | 依赖 |
|---|---|---|
| B0 | BI-0 契约增量修订（manifest v2，追加 incidence/t5/t6/t7/t8/c3）+ 指标字典扩充 | 需正式授权 |
| B1 | 新增 `v_store_sku` 等只读视图；新增/扩展 API；后端测试 | B0 |
| B2 | `/products` 页面（概览、帕累托、覆盖、列表、类别、共现） | B1 |
| B3 | `/products/:id` 页面（指标、旗标、覆盖门店、共现） | B1 |
| B4 | 小样本/空/错误/加载状态；E2E、性能、截图 | B2/B3 |
| B5 | BI-2 验收与冻结 | B0–B4 |

### 10.3 验收标准

| 类别 | 标准 |
|---|---|
| 数据一致 | 865 SKU、50,000 store×SKU、117 风险、35 多风险、12 三重旗标、1,237 对、32 个 L1 类别与冻结值一致；incidence 与 t1 的覆盖/指数/零销差异为 0 |
| 口径 | 全部使用"归一化销量指数"；共同出现写明"观察期内同店共同出现"；不得出现销售额/GMV/利润/库存/复购等词 |
| 小样本 | 覆盖<5 隐藏效率排名；<20 显示不稳定徽标；共现 <20 标注仅计数；L2/L3 sku_count<20 标注 |
| 交互 | 搜索、四类筛选、三种排序、分页、SKU→门店、SKU→共现、门店→门店详情均可用 |
| 性能 | 本地 API p95 <300 ms；首屏 <1.5 s；分页请求 <50 KB |
| 状态 | 正常、无搜索结果、空数据、加载中、加载失败、低覆盖 SKU 六类状态均有截图 |
| 安全 | 只读 DuckDB、排序白名单、无任意 SQL、无 SKU 明细导出 |
| 回归 | BI-1 的 77 项后端测试、前端单测、9 条 E2E 全部保持通过；P1–P4 哈希不变 |
| 契约 | 新增文件已登记 SHA-256；页面数据全部来自 API，无静态假数据 |

---

## 十一、明确结论

1. **现有数据足以支撑商品 BI。** 865 个 SKU 的规模、效率、覆盖、零销、波动、集中度、风险旗标、类别结构、门店覆盖与同店共同出现均有冻结结果，且 incidence 与 `t1` 的覆盖/指数/零销完全一致（差异 0）。
2. **可直接实施**：商品总览（KPI + 帕累托 + 覆盖分布）、全量 SKU 列表与详情、风险 SKU 筛选、一级类别结构、同店共同出现 Top。
3. **需要新增只读视图/API**：`v_store_sku`（必需）；SKU 汇总、全量列表、详情扩展、覆盖门店、共现查询（5 个接口）；L2/L3、覆盖敏感性、类别渗透（二期）。
4. **不建议实施**：价格/成本/利润、库存/补货、订单/客流、用户行为/复购、SKU 日趋势、全量共现矩阵、综合评分与因果结论。
5. **推荐 MVP**：`/products` + `/products/:id`，新增 1 个视图与 5 个接口；先完成 BI-0 契约增量修订，再进入编码。
6. **最大风险不是性能，而是契约**：incidence 是商品 BI 的核心数据，但尚未纳入冻结哈希清单；未完成增量登记前，不应进入正式实施。

本轮仅完成调研、核验与方案设计，未修改任何代码、数据、API、页面、配置或依赖，未读取 eval，未重跑 P1–P4，未执行 Git 操作。等待审查与下一步授权。
