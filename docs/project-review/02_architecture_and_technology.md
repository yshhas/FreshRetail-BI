# 第二章 架构设计与技术选型

> 本章以实际代码与文档为依据。**A** = 直接证据（代码/文档原文），**B** = 由实现反推的合理设计原因，**C** = 无法证实。

---

## 2.1 最初的架构思路

项目不是一开始就设计成“前后端分离”。它的架构是随着数据阶段推进逐层长出来的：

1. **数据层**（04–06）：原始 Parquet → 清洗 Parquet → 派生 Parquet → 分析 CSV；
2. **分析层**（07–08）：P1–P4 脚本读取派生数据，输出 CSV + PNG；
3. **接口层**（09 BI-0）：DuckDB 只读视图 → FastAPI；
4. **展示层**（09 BI-1/2）：React + ECharts。

这条演化路径在 09 §0.1 有直接记录：BI 阶段开始时“Web/API/容器当前不存在”，需要新增独立 `bi/` 层，且不改动分析代码（A）。

> **复盘判断（B）**：这是一种“先把数据做对，再考虑展示”的架构。优点是口径稳定、返工少；缺点是在 BI 之前没有任何服务化设计，导致 BI-0 需要重新搭一层接口。

---

## 2.2 完整系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│ 浏览器（Chrome / Edge）                                       │
│  React 18 + TypeScript + React Router + ECharts              │
│  URL search params = 筛选状态真源                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP GET /api/v1/*
                           │ （Vite dev proxy 5173 → 8000）
┌──────────────────────────▼──────────────────────────────────┐
│ FastAPI（bi_api.main:app）                                    │
│  - Pydantic v2 响应模型                                       │
│  - 参数白名单 / Literal / Query 边界                          │
│  - ValueError → 400，缺失 → 404                               │
│  - CORS: localhost:5173 / 127.0.0.1:5173，仅 GET              │
└──────────────────────────┬──────────────────────────────────┘
                           │ service.py 参数化 SQL
┌──────────────────────────▼──────────────────────────────────┐
│ DuckDB（内存连接，25 个只读视图）                              │
│  - enable_external_access=false                              │
│  - allowed_directories=[data/]                               │
│  - autoinstall/autoload extensions=false                     │
│  - lock_configuration=true                                   │
│  - query_df 仅允许 SELECT/WITH，禁多语句/DDL/文件函数          │
└──────────────────────────┬──────────────────────────────────┘
                           │ read_parquet / read_csv_auto
┌──────────────────────────▼──────────────────────────────────┐
│ 冻结数据层                                                     │
│  data/derived/*.parquet（P1 聚合）                             │
│  data/analysis/p2|p3|p3d|p4/*.csv（P2–P4 结果）                │
│  bi/data/freeze_manifest.json（25 项 SHA-256 + bytes）         │
└─────────────────────────────────────────────────────────────┘
```

启动时 `lifespan` 先执行 `freeze.verify_manifest()`，再初始化 `ReadOnlyDB`；任一失败则拒绝启动（`main.py:20-27`，A）。

---

## 2.3 目录结构与职责

```
中国数字零售与本地生活经营增长分析/
├── data/
│   ├── raw/freshretailnet50k/     # 官方原始 Parquet，只读
│   ├── derived/                   # 清洗与聚合 Parquet（可重建）
│   ├── analysis/p1–p4/            # P1–P4 分析结果 CSV
│   └── verification/              # 第四阶段核验产物
├── src/freshretail/
│   ├── config.py                  # 路径/契约/口径常量
│   ├── contracts.py               # 文件与数据帧契约
│   ├── cleaning.py                # R001–R012 清洗规则
│   ├── io.py                      # SHA-256、JSON、路径转义
│   ├── db.py                      # DuckDB 连接/视图/COPY
│   ├── metrics.py                 # 12 个聚合指标
│   ├── pipeline.py                # 流水线编排
│   ├── logging_utils.py           # JSONL 运行日志
│   └── analysis/p1–p4.py          # 四阶段分析
├── scripts/                       # 一键入口（build_derived、run_p1…）
├── tests/                         # 数据管道与分析单测
├── bi/
│   ├── data/                      # freeze_manifest、指标字典、页面映射
│   ├── src/bi_api/                # FastAPI + DuckDB + freeze
│   ├── tests/                     # BI 契约/API 测试
│   ├── web/src/                   # React 前端
│   ├── web/tests/                 # vitest + Playwright
│   └── README.md
├── reports/figures/p1–p4/         # 静态分析图
├── logs/                          # 流水线 JSONL
└── 01–09_*.md                     # 阶段报告、审计、验收
```

关键边界（A）：

- `data/raw` 只读；`data/derived` 可重建；`logs` 可追溯（06 §2）；
- BI 不修改 P1–P4 代码与结果（09 §0.2）；
- 前端不做业务聚合（09 §8.1 风险 2；`service.py` 承担全部统计）。

---

## 2.4 各服务/模块职责

| 模块 | 职责 | 不负责 |
|---|---|---|
| `src/freshretail` | 校验、清洗、聚合、分析、出图 | 页面、API、数据库 |
| `bi_api.freeze` | 25 项 SHA/bytes 校验、路径与重复键检查 | 数据计算 |
| `bi_api.db` | DuckDB 只读视图与 SQL 守卫 | 业务逻辑 |
| `bi_api.service` | 查询编排、筛选、分页、抑制、导出 | HTTP 细节 |
| `bi_api.main` | 路由、参数边界、CORS、异常映射 | SQL 拼接 |
| `bi/web` | 展示、筛选、下钻、状态管理 | 指标计算、阈值判断 |

---

## 2.5 核心模块依赖关系

```
main.py
  ├── models.py（响应契约）
  ├── service.py
  │     ├── db.py（ReadOnlyDB）
  │     ├── config.py（路径/版本）
  │     └── models.py（Meta/Envelope）
  └── freeze.py → config.py

frontend
  ├── api/client.ts → api/types.ts
  ├── pages/* → components/*、lib/*
  └── lib/navigation.ts、useUrlFilters.ts、useApi.ts、product.ts、format.ts
```

`service.py` 是唯一同时接触 SQL 与业务规则的层（A）。这种“薄路由 + 厚服务 + 纯数据层”的划分，使参数校验（`main.py`）与 SQL 安全（`db.py`）可以分别测试。

---

## 2.6 数据流转图

```
train.parquet
  │ ① verify_file（size + sha256）
  │ ② check_file_metadata（行/列/类型）
  │ ③ _raw_checks（主键/空值/负值/日期）
  ▼
clean_train.parquet（19 原始列 + 11 派生列）
  │ metrics.py 12 个聚合
  ▼
agg_daily / agg_store_day / agg_store_summary / agg_product_summary /
agg_city_summary / agg_category_day / agg_hour_profile / agg_hour_weekday /
diag_stockout_gradient / diag_promo_paired / diag_weather_bins /
diag_anomaly_days / agg_store_health
  │ analysis/p1–p4.py
  ▼
data/analysis/p1–p4/*.csv + reports/figures/*.png
  │ freeze_manifest.json（25 项）
  ▼
DuckDB 25 个只读视图
  │ service.py 参数化查询
  ▼
FastAPI JSON（data + meta + warnings）
  │
  ▼
React 页面
```

---

## 2.7 一次完整请求的执行过程

以“风险页选择精确组合”为例（A）：

1. 用户点击“缺货+高零销”组合行；
2. `RiskPage.tsx` 的 `patch({ exact_combo: '缺货+高零销', domains: '', domain: '', combo: 'exact' })` 更新 URL；
3. `useUrlFilters` 使用 `replace` 写 search params，并删除 `page`；
4. `useApi` 依赖变化触发 `api.getStores({ exact_combo, sample_scope: 'risk', page, page_size: 20, sort: 'store_id' })`；
5. `client.ts` 拼接 `/api/v1/stores?...`；
6. FastAPI `stores()` 读取 `exact_combo` 参数；
7. `service._store_where()` 校验组合是否在 `v_risk_exact` 全集内，追加 `exact_combo = ?`；
8. `ReadOnlyDB.query_df()` 做 SQL 守卫，执行参数化查询；
9. 返回 `{data, meta:{n, period, data_version, ...}, warnings}`；
10. 页面渲染门店表；副标题显示“当前筛选 38 家 · 精确组合：缺货+高零销”；
11. 点击门店行，`detailHref('/stores/70', buildReturnTo(...))` 带上 `returnTo`；
12. 返回时 `BackLink` 优先 `nav(-1)`，保留完整历史 URL。

这条链路在 C-2 E2E“精确组合→详情→返回 38 家”中被实际验证（A）。

---

## 2.8 异常发生后的处理过程

| 层 | 异常 | 处理 |
|---|---|---|
| 数据流水线 | 哈希/契约/空值/重复/负值 | 抛 `DataContractError` / `ValueError`，中止运行 |
| 冻结校验 | manifest 缺失/篡改/路径非法/重复键 | 抛 `FreezeError`，API 拒绝启动 |
| SQL 守卫 | 空 SQL、多语句、非 SELECT、写关键字 | 抛 `ReadOnlyError` |
| 业务参数 | 非法 `risk_domain`/`exact_combo`/`domains` | `ValueError` → HTTP 400 |
| 资源不存在 | 门店/商品 ID 不存在 | HTTP 404 |
| 前端请求 | 非 2xx/网络错误 | `useApi` 捕获 `Error`，页面显示 `ErrorBox` + 重试 |
| 小样本 | n<20 | 后端 `suppressed=true`、字段 null；前端 `—` |
| 空结果 | 筛选无匹配 | `DataTable` 渲染 `empty-state` |
| 前端参数冲突 | `exact_combo` 与 `domains` 同时存在 | 以 `domains` 为准 + 警告，不发错误请求 |
| 返回地址非法 | 外链/穿越/超长 | `safeReturnTo` 返回 null，回退默认页 |

---

## 2.9 系统启动过程

### 后端

```
uvicorn bi_api.main:app
  → FastAPI lifespan
    → freeze.verify_manifest()       # 25 项 SHA/bytes
    → service.get_db()               # ReadOnlyDB
      → duckdb.connect(":memory:")
      → 禁用扩展/外部访问/限定目录
      → 创建 25 个视图
      → SET lock_configuration=true
  → 开始接收请求
```

### 前端

```
npm run dev
  → Vite 启动 127.0.0.1:5173
  → /api 代理到 127.0.0.1:8000
  → 浏览器加载 index.html → main.tsx → App.tsx 路由
```

---

## 2.10 技术选型逐项分析

### 2.10.1 Python（3.13）

- **是什么**：通用编程语言，项目所有数据处理、分析、后端均使用。
- **解决什么问题**：数据分析生态（pandas/DuckDB/pyarrow）与 Web 框架（FastAPI）都在 Python。
- **职责**：流水线、统计计算、API。
- **替代方案**：R（统计分析强但 Web 弱）、Julia（生态小）、Java/Scala（重）。
- **为什么没选**：项目是“分析 + 展示”一体，Python 能同时覆盖两端（B，文档未显式比较）。
- **成本**：GIL 限制并发；类型系统弱于 TS；依赖体积大。
- **是否合理**：合理。对 4.5M 行单机分析，Python + DuckDB 足够。
- **重新设计**：仍会选 Python；若要做高并发 API，会把计算层换成 DuckDB 原生或独立服务（B）。

### 2.10.2 pandas

- **是什么**：表格数据处理库。
- **解决什么问题**：分析阶段需要对聚合结果做排序、分组、分位、合并、导出。
- **职责**：P1–P4 的后处理与报告表格。
- **替代方案**：Polars（更快、API 不同）、PySpark（重）、纯 SQL。
- **为什么没选 Polars**：文档未比较；项目开发时 pandas 更熟悉、生态更稳（B）。
- **成本**：大数据集内存占用高；本项目靠 DuckDB 先聚合，规避了主要问题。
- **是否合理**：合理，属于“够用且熟悉”的选择。

### 2.10.3 DuckDB + Parquet

- **是什么**：嵌入式分析型数据库，可直接查询 Parquet/CSV。
- **解决什么问题**：4.5M 行明细、1.08 亿行小时展开，需要快速聚合；但不想部署数据库服务。
- **职责**：数据管道聚合 + BI 只读视图。
- **替代方案**：
  - PostgreSQL/MySQL：需要部署、建表、导数、版本管理；
  - SQLite：单机可用，但列式分析性能弱；
  - Spark：过重；
  - 纯 pandas：小时展开内存压力大。
- **为什么选它**（06 §4，A）：
  - 直接查 Parquet，数秒级；
  - 无独立数据库部署成本；
  - 结果仍是 Parquet，pandas/BI 都能读；
  - 支持窗口函数、`unnest`、`generate_subscripts`，适合小时展开。
- **成本**：单机、单进程；并发写不支持；SQL 方言与 PostgreSQL 有差异。
- **是否合理**：非常合理。数据规模在单机可承受范围，BI 只读场景不需要服务型数据库。
- **重新设计**：仍会选 DuckDB；若数据增长 10–100 倍，会考虑 Parquet 分区 + DuckDB 多进程或 ClickHouse（B）。

### 2.10.4 FastAPI + Pydantic v2

- **是什么**：Python Web 框架 + 数据校验库。
- **解决什么问题**：把冻结数据暴露为只读 JSON API，并保证响应结构稳定。
- **职责**：路由、参数校验、响应模型、CORS、异常映射。
- **替代方案**：Flask（轻但需自己校验）、Django（重）、Node/Express（需重写数据层）。
- **为什么选它**（09 §4.3，A）：Pydantic 模型天然适合“契约先行”，自动生成 `/docs`，与 Python 数据层同语言。
- **成本**：同步阻塞；单 worker 时并发有限；Pydantic v2 与 v1 生态兼容问题。
- **是否合理**：合理。只读、低并发、本地演示，FastAPI 足够。
- **重新设计**：仍会选；若要多用户并发，会加 Gunicorn/Uvicorn workers，并把 DuckDB 连接改为每 worker 一个（B）。

### 2.10.5 React 18 + TypeScript + Vite

- **是什么**：前端框架、类型系统、构建工具。
- **解决什么问题**：多页面、复杂筛选、图表交互、URL 状态。
- **职责**：页面渲染、路由、状态、请求。
- **替代方案**：Vue（同样合适）、Next.js（SSR 对本项目无收益）、Svelte（生态小）。
- **为什么选它**（09 §4.2，A）：React 生态成熟、ECharts 集成简单、TypeScript 能在编译期发现类型错误。
- **成本**：包体积大（JS 1.29 MB）；需要自己搭状态方案；无 SSR。
- **是否合理**：合理。内部只读 BI 不需要 SEO/SSR。
- **重新设计**：仍会选 React；但会引入路由级代码分割降低首包（B）。

### 2.10.6 ECharts 5 + echarts-for-react

- **是什么**：图表库及 React 封装。
- **解决什么问题**：趋势、柱状、散点、热力图。
- **职责**：所有可视化。
- **替代方案**：Recharts（简单但热力图弱）、D3（灵活但开发慢）、Plotly（体积大）。
- **为什么选它**：中文生态好、图表类型全、热力图/散点开箱即用（B；文档只写“ECharts”）。
- **成本**：包体积大；需要手动处理 `animation:false`、`notMerge` 等细节（代码中已处理）。
- **是否合理**：合理。

### 2.10.7 React Router 6

- **是什么**：前端路由。
- **解决什么问题**：10 个页面的 URL 映射与返回。
- **职责**：路由、`useNavigate`、`useLocation`、`Link`。
- **替代方案**：TanStack Router（类型更强但生态新）、手写 history。
- **为什么选它**：成熟、与 URL 状态方案契合（A：`package.json`）。
- **成本**：无数据加载器；返回状态需自己实现（`BackLink`）。
- **是否合理**：合理。

### 2.10.8 自研 `useApi` 而非 React Query

- **是什么**：约 40 行的请求 Hook（loading/error/reload）。
- **解决什么问题**：页面请求与卸载保护。
- **职责**：`useEffect` + `alive` 标志。
- **替代方案**：React Query（缓存、重试、失效）、SWR。
- **为什么没引入**：项目只读、请求简单、避免新增依赖（B；09 设计曾建议 React Query，但实际未用，属规划与交付差异，A）。
- **成本**：无缓存、无请求去重、无后台刷新；每次筛选都重新请求。
- **是否合理**：在当前规模下合理；若页面变多、请求变复杂，应引入 React Query（B）。

### 2.10.9 Playwright（playwright-core + 本机 Chrome）

- **是什么**：浏览器自动化。
- **解决什么问题**：验证真实页面行为（筛选、下钻、返回、空态）。
- **职责**：6 个 E2E 脚本，56 个校验点。
- **替代方案**：Cypress（隔离性好但多 tab/下载弱）、Selenium（慢）。
- **为什么选它**：可直接驱动本机 Chrome，无需下载浏览器（`executablePath`）。
- **成本**：依赖本机 Chrome 路径；非标准 `@playwright/test` 断言库，脚本是手写 `ok()`。
- **是否合理**：对作品集项目合理；生产项目应使用 `@playwright/test` + CI。

### 2.10.10 Vitest + jsdom

- **是什么**：前端单测框架。
- **解决什么问题**：纯函数测试（格式化、导航安全、商品逻辑）。
- **职责**：23 个测试。
- **替代方案**：Jest（配置重）。
- **为什么选它**：与 Vite 同生态，零额外构建配置（B）。
- **成本**：jsdom 与真实浏览器有差异；无组件渲染测试。
- **是否合理**：合理，但覆盖面有限。

### 2.10.11 pytest

- **是什么**：Python 测试框架。
- **解决什么问题**：数据契约、清洗、指标、API。
- **职责**：101 个测试。
- **替代方案**：unittest（啰嗦）。
- **为什么选它**：生态标准，fixture 适合真实数据测试（B）。
- **成本**：测试直接依赖真实冻结数据，数据变更会导致大面积失败（这既是保护也是耦合）。

### 2.10.12 Docker Compose（规划但未实施）

- **设计方案** §4.5 规划 `web`（Nginx）+ `api`（FastAPI + DuckDB），数据卷只读。
- **实际**：仓库无 Dockerfile / compose 文件（运行说明 §4，A）。
- **为什么没做**：项目在“本地展示”阶段停止，Docker 不是验收必需（B）。
- **代价**：交付可移植性弱；换机器需要 Node/Python 环境。
- **重新设计**：若要做演示交付，Docker Compose 是性价比最高的下一步（B）。

---

## 2.11 为什么没有选择其他技术

| 技术 | 为什么不需要 |
|---|---|
| PostgreSQL/MySQL | 只读分析、无并发写、无事务需求；DuckDB 直查 Parquet 更轻 |
| Redis | 无缓存/队列/会话需求；单机只读 |
| 消息队列（Kafka/RabbitMQ） | 无实时数据流 |
| 微服务 | 单体足够；拆分会增加部署与联调成本 |
| Next.js/SSR | 内部 BI 不需要 SEO/首屏服务端渲染 |
| Redux/Zustand | 筛选状态放 URL，UI 状态很少；引入全局 store 反而增加复杂度 |
| React Query | 当前请求简单；但这是可改进项 |
| ORM（SQLAlchemy） | 只读视图 + 手写参数化 SQL 更直接、更可控 |
| AI Agent/RAG | 明确非目标（09 §8.3） |
| 预测模型 | 数据只有 90 天，06 仅预留边界，未启动 |

---

## 2.12 前后端职责划分

| 关注点 | 前端 | 后端 |
|---|---|---|
| 筛选参数 | 生成/保存到 URL | 校验/白名单 |
| 指标计算 | 不做 | 全部在 SQL/服务层 |
| 小样本抑制 | 只负责显示 `—` | 判断 n<20 并置空 |
| 分页 | 传 page/page_size | LIMIT/OFFSET + 总数 |
| 排序 | 传白名单字段 | 白名单校验，非法回退 |
| 错误展示 | ErrorBox/重试 | HTTP 状态码 + detail |
| 返回状态 | `returnTo`/`BackLink` | 不参与 |
| 安全 | `safeReturnTo` | SQL 守卫、CORS、只读 |

这条边界的关键原则是：**统计与口径必须在后端，前端只做展示**。它避免了“前端自行聚合绕过 n<20”的风险（09 §8.1 风险 2，A）。

---

## 2.13 数据库设计（视图关系）

项目没有传统数据库表，而是 25 个 DuckDB 视图（A）：

| 视图 | 来源 | 行数 |
|---|---|---:|
| `v_daily` / `v_hour` / `v_hour_weekday` | `data/derived/*.parquet` | 90 / 24 / 168 |
| `v_store_profile` / `v_store_diagnosis` / `v_store_not_applicable` | P4-A/P4-B | 898 / 888 / 10 |
| `v_store` | 上述三者 LEFT JOIN | 898 |
| `v_city` | P3-A `a1` + P3-D `d5` | 18 |
| `v_risk_domain` / `v_risk_exact` / `v_risk_at_least` | P3-D/P4-B | 6 / 16 / 10 |
| `v_risk_quadrant` / `v_risk_cluster` / `v_overall` | P3-D | 4 / 4 / 2 |
| `v_sku` / `v_sku_risk` / `v_category` | P2 | 865 / 117 / 32 |
| `v_store_sku` / `v_store_sku_summary` / `v_flagged_sku` | P4-C | 50,000 / 898 / 117 |
| `v_category_risk` / `v_sku_pairs` / `v_store_groups` | P4-C | 32 / 1,237 / 16 |
| `v_sku_head_tail` / `v_category_penetration` | P2/P3-C | 2 / 32 |

`v_store` 的 `COALESCE(b.diagnosis_status, n.diagnosis_status, '不适用')` 是“10 家低 SKU 门店不诊断”的数据库级保证（A）。

---

## 2.14 扩展性与可维护性

### 优点（A）

- 数据契约与解析分离，新增字段需改 `contracts.py`；
- 视图集中在 `db.py`，新增页面只需加视图 + 服务函数 + 路由；
- 前端组件化（Section/DataTable/FilterSelect/States），页面复用度高；
- 测试直接断言冻结数字，回归保护强。

### 风险（A/B）

- **硬编码数字多**：898、888、865、117、35、43、16、10、38、56 散落在前端文案与测试中；数据重冻结时会静默漂移（A：`product.ts`、`ProductRiskPage.tsx`、E2E）。
- **单连接 + RLock**：所有查询串行；当前数据量可接受，多用户会排队（A：`db.py:41,128`）。
- **无缓存**：每次筛选都重新查 DuckDB；页面切换重复请求（B）。
- **无版本化 API**：只有 `/api/v1` 前缀，无兼容层；字段变更会影响前端（B）。
- **无 CI**：依赖本地手动跑测试（A：无 `.github/workflows`）。

---

## 2.15 本章证据等级

| 结论 | 等级 |
|---|---|
| 分层架构与目录职责 | A（代码/06 报告） |
| DuckDB 选型理由 | A（06 §4） |
| FastAPI/React/ECharts 选型 | A（09 §4、package.json） |
| 替代方案对比细节 | B（文档只列结论，未逐项比较） |
| “先数据后展示”的演化判断 | B |
| React Query 规划未落地 | A（09 §4.2 vs 实际 `useApi`） |
| 扩展性风险 | A（代码常量/无 CI） |
