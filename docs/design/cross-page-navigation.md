# BI-2-C 跨页面联动与交互式下钻方案设计报告

- 项目：中国数字零售与本地生活经营增长分析
- 阶段：BI-2-C C-0 方案设计（**只分析，不实施**）
- 日期：2026-11-08
- 当前版本：数据 `p1-p4-freeze-2026-11-08`、契约 `bi0-contract-v2`、BI-2-B 冻结 `bi2b-freeze-2026-11-08`
- 本轮声明：未修改代码、组件、路由、测试、配置、依赖、API、视图或数据；未读取 eval；未执行 Git；未启动 BI-2-C 开发

---

## 一、结论摘要

| 问题 | 结论 |
|---|---|
| 哪些联动可以直接做 | 城市→门店列表、门店列表→门店详情、风险域/多风险/R7/R8→门店列表、SKU→覆盖门店→门店详情（基础跳转） |
| 哪些只需前端改造 | 返回状态恢复、URL 状态模型、组合行点击 UI、小城市/小样本提示 |
| 哪些需要新增后端 | 风险“恰好组合”筛选（`/stores` 加可选参数）、门店→风险 SKU 列表（`GET /stores/{id}/skus`）；“至少组合”筛选为可选项 |
| 哪些不建议做 | 同日销售、购买搭配、客流/用户/库存、综合评分、跨页多条件任意联动 |
| 最大非技术障碍 | BI-1 与 BI-2-B 页面、BI-2-A API 已 Feature Freeze；实现 C1–C5 必须走受控变更授权，不能按“纯新增”处理 |

**推荐架构：URL 作为唯一状态载体 + 显式 `returnTo` 返回上下文，不引入全局状态库或跨页缓存。**

---

## 二、现状证据（基于实际代码）

### 2.1 路由与页面

| 路由 | 页面 | 现状 |
|---|---|---|
| `/overview` | 经营总览 | 城市表行点击进入 `/cities-stores?city=N`（[OverviewPage.tsx#L125](../../bi/web/src/pages/OverviewPage.tsx#L125)） |
| `/cities-stores` | 城市与门店 | 城市表点击只写 `city` 筛选；散点点击进入 `/stores/{id}`；门店行进入详情（[CityStorePage.tsx#L161](../../bi/web/src/pages/CityStorePage.tsx#L161)、[#L172](../../bi/web/src/pages/CityStorePage.tsx#L172)、[#L190](../../bi/web/src/pages/CityStorePage.tsx#L190)） |
| `/risk` | 经营风险 | 风险域卡片写 `domain`；风险组合表为展示表，行不可点击（[RiskPage.tsx#L93](../../bi/web/src/pages/RiskPage.tsx#L93)、[#L138-L143](../../bi/web/src/pages/RiskPage.tsx#L138-L143)） |
| `/stores/:id` | 门店详情 | 返回链接固定 `/cities-stores`，不带来源状态（[StoreDetailPage.tsx#L52](../../bi/web/src/pages/StoreDetailPage.tsx#L52)）；无门店→SKU 列表 |
| `/products` 等 | 商品 BI | SKU 详情覆盖门店行可点击到 `/stores/{id}`（[ProductDetailPage.tsx#L175](../../bi/web/src/pages/ProductDetailPage.tsx#L175)）；返回列表链接固定 `/products/list` |

### 2.2 URL 状态

- 统一 hook：[useUrlFilters.ts#L7-L13](../../bi/web/src/lib/useUrlFilters.ts#L7-L13)；
- 任一非 `page` 参数变化会删除 `page`（自动回第 1 页）；
- 没有统一参数命名空间、冲突处理或 `returnTo`；
- 城市/商品页使用不同键名（`cat`、`ht`、`cov`、`ssort` 等），直接跨页复制会带入无效参数。

### 2.3 API 与视图

| 能力 | 现状 |
|---|---|
| `/cities` | 18 城；只读 |
| `/stores` | 支持 `city_id`、`quadrant`、`cluster`、`risk_domain`、`sample_scope`、分页、排序；`risk_domain` 白名单含 R1–R8、`stockout_domain`、`multi_risk`（[service.py#L147-L166](../../bi/src/bi_api/service.py#L147-L166)） |
| `/stores` 返回 | 含 `exact_combo`、`domain_labels`、`structural_notes`（[service.py#L177-L184](../../bi/src/bi_api/service.py#L177-L184)） |
| `/stores/{id}` | 返回门店完整档案与 P4-B 标签；无 SKU 列表 |
| `/risk/summary`、`/risk/combinations` | 全样本统计；exact 16、at_least 10；无门店筛选参数 |
| `/products/{id}`、`/products/{id}/stores`、`/products/{id}/pairs` | SKU→门店、SKU→共现；无门店→SKU |
| `v_store` | 已含 `exact_combo`、R1–R8、domain_count、structural_notes |
| `v_store_sku` | 50,000 行 store×SKU incidence，已存在（BI-2-A） |
| `v_sku` / `v_category` | 865 SKU / 32 L1 类别 |

### 2.4 数据事实

- 风险组合：exact 16 种、at_least 10 个跨域两两组合；`exact_combo` 字段直接可筛选；
- 门店风险：多风险 132；R7 93 / R8 90 为结构提示，不计入运营域；
- store×SKU：每店 SKU 数中位 50、最大 164；单店风险 SKU 数示例 7/6/0/4；
- 小城市标记 `small_city = store_count < 10`（P3-A），与 n<20 抑制不是同一规则。

---

## 三、推荐整体交互架构

### 3.1 原则

1. **URL 是唯一状态源**：刷新、浏览器返回、复制链接均可恢复；
2. **页面只解释自己认识的参数**：不做“全参数透传”；
3. **跨页跳转显式构造目标 URL**，附带 `returnTo` 返回上下文；
4. **不引入全局 store/Provider/缓存**，避免与 URL 双写；
5. **小样本规则由后端执行**，前端只展示 `suppressed` 与警告；
6. **不跨页携带无关筛选**（类别不带到门店页、风险域不带到商品页）。

### 3.2 导航约定

```
列表页 ──(行点击)──> 详情页?returnTo=<encoded 当前列表URL>
详情页 ──(返回)────> returnTo（白名单校验）或默认列表页
```

- `returnTo` 只接受站内白名单路径：`/cities-stores`、`/risk`、`/products/list`、`/products/:id`、`/stores/:id`；
- 拒绝 `http://`、`//`、`..`、未知路径；
- 浏览器 Back 仍由 history 保证，`returnTo` 仅用于页面内“返回”按钮。

---

## 四、跨页面筛选状态模型

### 4.1 参数表

| 参数 | 适用页面 | 取值 | 说明 |
|---|---|---|---|
| `city` | 城市页 | 0–17 | 现有键，保持兼容 |
| `store` | 门店详情 | 0–897 | 路由参数 `/stores/:id`，不重复写入 query |
| `sku` | SKU 详情 | 0–864 | 路由参数 `/products/:id` |
| `risk` | 城市页/风险页 | `stockout_domain/R3–R8/multi_risk` | 现有键；R7/R8 仅结构提示 |
| `combo` | 风险页 | exact 组合字符串 | 新增；与 `risk` 互斥 |
| `combo_mode` | 风险页 | `exact/at_least` | 新增；默认 `exact` |
| `quadrant` | 门店列表/详情 | 四象限字符串 | 现有 |
| `cluster` | 门店列表/详情 | G1–G4 | 现有 |
| `category` | 商品列表 | C01–C32 | 现有 `cat` 可保留，新增统一别名不强制 |
| `q` | 商品列表 | ≤40 字符 | 现有 |
| `scope` | 门店列表 | `all/risk` | 现有；商品页固定 `all` |
| `page` | 各列表 | ≥1 | 任一筛选变化清空 |
| `sort`/`order` | 各列表 | 白名单 | 现有 |
| `returnTo` | 详情页 | 站内 URL | 新增；白名单校验 |

### 4.2 冲突与优先级

| 冲突 | 处理 |
|---|---|
| `city` + 门店详情 | 门店详情只认路由 `store`；`city` 忽略 |
| `risk` + `combo` | 互斥；设置 combo 时清空 risk，反之亦然 |
| `combo_mode` 切换 | 清空 `combo` 与 `page` |
| `scope=risk` 与 `risk=R7/R8` | 允许，但标签必须写“结构提示”，不得计入多风险 |
| 商品页收到 `risk/scope` | 忽略，不传播 |
| 城市页收到 `category` | 忽略 |
| 页面越界 `page` | 返回空列表，`meta.n` 仍为总数；前端可自动回落 |
| 未知参数 | 忽略；`returnTo` 除外（需校验） |

### 4.3 保留/清空矩阵

| 跳转 | 保留 | 清空 |
|---|---|---|
| 城市→门店列表 | `city`、`scope=risk` | `page`、`quadrant/cluster/risk` |
| 风险→门店列表（域卡片） | `risk`、`quadrant/cluster` | `page`、`city` |
| 风险组合→门店列表 | `combo`、`combo_mode`、`quadrant/cluster` | `risk`、`page`、`city` |
| 门店→门店详情 | `store` + `returnTo` | 列表筛选不进入详情 query |
| 门店详情→SKU 详情 | `sku` + `returnTo`（门店 URL） | 商品筛选 |
| SKU→覆盖门店 | `sku`、`city/quadrant/cluster/ssort/page` 保留在原页 | 门店详情不接收这些 |
| 商品列表→SKU 详情 | `sku` + `returnTo` | 门店筛选 |

---

## 五、五个场景分析

### C1 城市 → 门店 → 门店详情

| 项 | 现状 | 结论 |
|---|---|---|
| 城市对比点击 | 总览城市表已跳 `/cities-stores?city=N`；城市页城市表点击设置 `city` | 可直接用 |
| 自动传递 city | 是，URL 参数 | 可直接用 |
| 门店列表→详情 | 已有 | 可直接用 |
| 保留筛选/分页/返回 | 浏览器 Back 可恢复；页面内返回链接丢失 city | **需前端改造**：`returnTo` |
| 小城市 / n<20 | `small_city` = 门店数 <10；筛选后列表可能 <20 | **需前端提示**：小城市标签与“不生成组统计”说明；后端不返回组统计 |

**缺口**：仅返回状态；无 API 缺口。

### C2 经营风险 → 风险门店 → 门店详情

| 项 | 现状 | 结论 |
|---|---|---|
| 风险域卡片 | 已写 `domain`，列表按 `risk_domain` 过滤 | 可直接用 |
| 多风险 | `risk_domain=multi_risk` 可用 | 可直接用 |
| R7/R8 | 可筛选，但属于结构提示 | 可直接用，必须保留“结构提示”标签，不得计入运营域 |
| 恰好组合点击 | 组合表无行点击；`/stores` 无 `exact_combo` 参数 | **需新增后端可选参数 + 前端行点击** |
| 至少组合点击 | 无参数；需把两个域名映射到 R 旗标做 AND | **可选项**，建议二期；需新增 `domains` 参数 |
| 全样本 vs 筛选列表 | 现有页面已标注；跳转后应保留“组合口径”标签 | 需前端新增筛选 chip 与说明 |
| 口径丢失 | 风险组合表有 16 exact / 10 at_least；若只带一个字符串，必须带 `combo_mode` | 需状态模型明确 |

**关键口径**：exact = 域集合完全相等（如“缺货+高零销”38）；at_least = 至少同时命中两个域（56）。跳转后列表计数必须标明当前口径，不能把 38 与 56 混用。

### C3 风险门店 → 商品 BI → SKU 详情

| 项 | 现状 | 结论 |
|---|---|---|
| 门店风险详情定位 SKU | 门店详情无 SKU 列表 | **需新增 API + 前端区块** |
| 可用数据 | `v_store_sku` 50,000 行；含 `is_flagged/is_multi_flag`、指数、零销天、缺货天 | 数据足够，无需新视图 |
| 门店→SKU 筛选 API | 无；现有只有 SKU→门店 | 新增 `GET /stores/{id}/skus` |
| 共同出现语义 | 该接口只列“该店观察期内出现的 SKU/风险 SKU”，不涉及商品对 | 不解释购买搭配、同日销售 |
| 小样本 | 单店 SKU 数中位 50、最少 1；10 家 SKU<10 门店 | 门店详情已有“基础档案/不诊断”提示；SKU 列表为明细，不做客户端组统计 |

**建议**：门店详情新增“该店风险 SKU（观察期内）”区块；默认仅 `is_flagged=true`，可切换全部 SKU；行点击进入 SKU 详情，`returnTo` 回门店。

### C4 SKU 详情 → 覆盖门店 → 门店详情

| 项 | 现状 | 结论 |
|---|---|---|
| SKU 覆盖门店列表 | 已有 `/products/{id}/stores` | 可直接用 |
| 跳门店详情 | 已有行点击 | 可直接用 |
| 传递 SKU/城市/象限/结构群 | 这些是 SKU 详情页本页筛选，门店详情不需要 | 只传 `store` + `returnTo` |
| 返回恢复 SKU 状态 | 无；返回链接固定 `/products/list` | **需前端改造** |
| 明细 vs 组统计 | 已分层；`suppressed` 有警告 | 保持 |

**缺口**：仅前端返回状态；无 API 缺口。

### C5 跨页面筛选状态

- 现状：`useUrlFilters` 可读写，但无统一模型、无 returnTo、无冲突规则、无参数白名单；
- 推荐：保留现有键名，新增 `combo/combo_mode/returnTo`；建立 `lib/navigation.ts`（纯函数）统一构造与校验；
- 不引入全局状态库；URL 刷新可恢复，Back 由 history 保证。

---

## 六、API 复用与新增清单

### 6.1 直接复用

| 能力 | 端点 |
|---|---|
| 城市列表/城市筛选 | `/cities`、`/stores?city_id=` |
| 门店列表/详情 | `/stores`、`/stores/{id}` |
| 风险域/多风险/R7/R8 | `/stores?risk_domain=` |
| 风险统计/组合 | `/risk/summary`、`/risk/combinations` |
| SKU 详情/覆盖门店/共现 | `/products/{id}`、`/products/{id}/stores`、`/products/{id}/pairs` |
| 筛选下拉 | `/meta/filters` |

### 6.2 需要新增（建议）

| # | 接口/参数 | 用途 | 数据依赖 | 成本 | 优先级 |
|---|---|---|---|---|---|
| A1 | `GET /stores` 增加可选 `exact_combo` | 风险组合“恰好”点击筛选 | `v_store.exact_combo` | S | P1 |
| A2 | `GET /stores/{id}/skus` | 门店→SKU/风险 SKU 列表 | `v_store_sku` + `v_sku` | M | P1 |
| A3 | `GET /stores` 增加可选 `domains`（两个运营域） | “至少组合”点击筛选 | `v_store` R1–R6 | S–M | P2（可选） |

无新增视图、无派生数据集、无数据版本变化。A1/A2/A3 均为可选参数/新端点，理论上向后兼容，但会修改已冻结的 BI-2-A 代码，需受控变更授权。

---

## 七、小样本与数据安全方案

| 场景 | 规则 |
|---|---|
| 城市筛选后门店数 <20 | 只展示门店明细；不计算组均值/比例；显示“样本不足（n<20）” |
| 小城市（<10 店） | 复用 `small_city` 标签，说明“城市规模小，横向比较需谨慎” |
| 风险组合筛选 | 列表计数是筛选后门店数；组合表计数仍是全样本，页面必须同时标注“全样本组合数”与“当前筛选 N 家” |
| R7/R8 | 始终标注“结构提示”，不纳入运营域、多风险与组合筛选 |
| 门店→SKU 列表 | 是明细，不是组统计；若展示“风险 SKU 数/占比”，必须用后端字段，不在前端计算 |
| SKU→覆盖门店 | 已是明细；`suppressed` 继续显示警告 |
| 共现 | 保持“观察期内同店共同出现”定义；不得写成同日销售/购买搭配/因果 |
| 通用 | 排序/筛选白名单、参数化、无任意 SQL；`returnTo` 白名单防开放重定向 |

---

## 八、性能评估

| 场景 | 预计成本 | 依据 |
|---|---|---|
| 城市/风险筛选（现有） | 与 BI-1 持平（约 160–200 ms） | 现有 `/stores` 实测 |
| exact_combo 筛选 | 898 行表过滤，预计 <150 ms | 与现有 risk_domain 过滤同量级 |
| 门店→SKU（A2） | 50,000 行 incidence 按 store 过滤 + 865 SKU Join，预计 100–200 ms | 与 `/products/{id}/stores` 同量级（P95 216 ms） |
| SKU→门店（现有） | P95 约 216 ms | BI-2-A 实测 |
| 跨页 URL 跳转 | 无额外后端成本 | 纯前端 |
| 风险组合切换 | 组合表 + 门店列表两次请求 | 可并行；无需缓存 |

建议：不引入预聚合或缓存；若 A2 上线后 P95 >300 ms，再评估进程内只读缓存；不做客户端缓存拼接。

---

## 九、风险与决策点

| # | 风险/决策 | 影响 | 建议 |
|---|---|---|---|
| R1 | 修改 BI-1/BI-2-B 冻结页面 | 违反 Feature Freeze 若无授权 | 先提交 BI-2-C 变更申请，限定文件（CityStorePage、RiskPage、StoreDetailPage、ProductDetailPage）与“仅加链接/状态”范围 |
| R2 | 修改 BI-2-A `service/main` | 已冻结 | A1/A2/A3 作为独立变更批次，附回归测试；不改数据契约 |
| R3 | 风险组合口径混淆 | 38 vs 56 误用 | 跳转必须携带 `combo_mode`；页面显示口径与定义 |
| R4 | 返回状态丢失 | 用户重复筛选 | 统一 `returnTo` + URL 状态 |
| R5 | 小样本绕过 | 客户端聚合 | 禁止前端组统计；仅消费后端抑制结果 |
| R6 | 开放式 returnTo | 安全风险 | 仅允许白名单站内路径 |

---

## 十、实施分类结论

### 可以直接实施（无需改后端）

- C1 城市→门店列表、门店列表→门店详情；
- C2 风险域卡、多风险、R7/R8 筛选；
- C4 SKU→覆盖门店、门店行→门店详情；
- 现有商品/门店页的普通筛选与分页。

### 需要先修改前端（含冻结页面变更授权）

- C1/C2/C4 的 `returnTo` 返回状态；
- C2 组合行点击 UI 与口径标签（依赖 A1/A3）；
- C5 统一 URL 状态模型与参数校验；
- 小城市/筛选后 n<20 提示。

### 需要新增后端 API/参数

- A1 `exact_combo`（P1）；
- A2 `GET /stores/{id}/skus`（P1）；
- A3 `domains` 至少组合筛选（P2，可选）。

### 当前数据不支持 / 不建议实施

- 同日销售、购买搭配、购物篮、客流、用户复购、库存/补货；
- 综合评分、门店排名、商品推荐；
- 任意多条件跨页联动网络；
- SKU×日趋势下钻（无冻结 SKU×日表）；
- 全量 865×865 共现矩阵。

---

## 十一、推荐方案总结

1. **架构**：URL 状态 + 显式 `returnTo`，不引入全局状态库；
2. **优先级**：先做 C1/C4 返回状态与 C2 域筛选（P0/P1），再做 A1+A2（P1），A3 视需求（P2）；
3. **最小 API 集**：`exact_combo` 参数、`/stores/{id}/skus`，均基于现有视图，无需新数据；
4. **先决条件**：BI-1/BI-2-B/BI-2-A 冻结文件的受控变更授权；
5. **不建议**为追求完整而增加跨页缓存、全局筛选中心或全量共现。

详细矩阵见《BI-2-C API 与数据可行性矩阵》，分阶段计划见《BI-2-C 分阶段实施计划》。

本轮仅完成方案设计，未修改任何文件，等待审阅与下一阶段授权。
