﻿﻿﻿﻿﻿﻿﻿# BI-0 数据契约与只读访问层实施报告

**项目**：中国数字零售与本地生活经营增长分析
**阶段**：BI-0（数据契约与只读数据访问层）
**日期**：2026-11-08
**状态**：BI-0 实施完成，等待审查；未启动 BI-1，不自行宣布验收通过

---

## 1. 实施范围与结论

| 项目 | 结果 |
|---|---|
| 新增目录 | `bi/`（独立于 P1–P4 分析代码） |
| 数据访问 | DuckDB 内存只读视图，直接查询 P1–P4 冻结 CSV/Parquet |
| API | FastAPI 只读接口 + Pydantic 模型 |
| 指标字典 | `bi/data/metric_dictionary.csv` |
| 页面映射 | `bi/data/page_table_map.csv` |
| 冻结校验 | 22 个源文件 SHA-256 manifest，启动时校验 |
| 测试 | 全量 **77 passed**（P1–P4 62 + BI-0 15） |
| 性能 | 核心 API P95 均 < 150ms（本地） |
| P1–P4 | 未修改、未重跑、未读取 eval |

**结论**：BI-0 数据层可支撑第一批 BI 页面（总览、城市与门店、风险）；暂未开发 React/ECharts 页面。

---

## 2. 新增文件与目录

```
bi/
  README.md
  requirements.txt
  data/
    freeze_manifest.json          # 22 个源文件 SHA-256（P1–P4 冻结）
    metric_dictionary.csv         # D1–D17 + P4 指标
    page_table_map.csv            # 页面/组件 -> 源表
  src/bi_api/
    __init__.py
    config.py                     # 路径、观察期、版本
    freeze.py                     # manifest 校验
    db.py                         # DuckDB 只读视图 + SQL 白名单
    catalog.py                    # 指标字典/页面映射
    models.py                     # Pydantic 请求/响应模型
    service.py                    # 只读查询服务
    main.py                       # FastAPI 应用
  tests/
    conftest.py
    test_bi0_contracts.py         # 9 项
    test_bi0_api.py               # 6 项
  benchmarks/
    bench_bi0.py
    benchmark_results.json
  scripts/
    build_freeze_manifest.py
```

**未新增**：React 页面、ECharts、Docker Compose、BI mart、数据库服务、AI/RAG 组件。

---

## 3. DuckDB 只读视图与来源

| 视图 | 行数 | 来源 |
|---|---:|---|
| `v_daily` | 90 | `data/derived/agg_daily.parquet` |
| `v_hour` | 24 | `agg_hour_profile.parquet` |
| `v_hour_weekday` | 168 | `agg_hour_weekday.parquet` |
| `v_store_profile` | 898 | P4-A `p4_a_store_profile.csv` |
| `v_store_diagnosis` | 888 | P4-B `p4_b_store_diagnosis.csv` |
| `v_store_not_applicable` | 10 | P4-B `p4_b_not_applicable.csv` |
| `v_store` | 898 | P4-A + P4-B + 不适用表 |
| `v_city` | 18 | P3-A `a1_city_metrics.csv` + P3-D `d5_city_risk.csv` |
| `v_store_sku_summary` | 898 | P4-C `p4_c_store_sku_risk_summary.csv` |
| `v_flagged_sku` | 117 | P4-C `p4_c_flagged_sku_distribution.csv` |
| `v_category_risk` | 32 | P4-C `p4_c_category_risk_profile.csv` |
| `v_sku_pairs` | 1,237 | P4-C `p4_c_sku_pair_cooccurrence.csv` |
| `v_store_groups` | 16 | P4-C `p4_c_quadrant_cluster_cross.csv` |
| `v_risk_domain` | 6 | P3-D `d9_domain_count.csv` |
| `v_risk_exact` | 16 | P4-B `p4_b_exact_combinations.csv` |
| `v_risk_at_least` | 10 | P3-D `d8b_pairwise_combinations.csv` |
| `v_risk_quadrant` | 4 | P3-D `d6_quadrant_risk.csv` |
| `v_risk_cluster` | 4 | P3-D `d7_structure_risk.csv` |
| `v_overall` | 2 | P3-D `d13_overall_rates.csv` |
| `v_sku` | 865 | P2 `t1_sku_metrics.csv` |
| `v_sku_risk` | 117 | P2 `t9_sku_risk_flags.csv` |
| `v_category` | 32 | P2 `t4_category_l1.csv` |

**说明**：

- 所有视图只读；不创建表、不写 Parquet/CSV；
- `v_risk_exact` 使用 P4-B 完整 16 组合，而不是 P3-D `d10` 的 Top 11；
- `v_store` 将 10 家 SKU<10 的 `diagnosis_status` 置为“不适用”，风险字段为 null；
- 不查询 `clean_train.parquet` 行级数据，不需要 4.5m 行扫描。

---

## 4. 指标字典与数据契约

### 4.1 指标字典

`bi/data/metric_dictionary.csv` 覆盖：

- 样本：`SAMPLE-ALL` 898、`SAMPLE-RISK` 888；
- P1：`P1-TOTAL`、`P1-PER-DAY`；
- 缺货：D1 城市池化、D2 城市门店率均值、D3 门店率、D4 门店中位、D5 P90 尾部、D6/D7 小时率；
- 零销：D8/D9；
- CV：D10 城市门店离散度、D11 门店销量 CV；
- 低销：D12 R3 二元、D13 真实天数；
- 结构：D14 HHI、D15 structure_valid、D16 G1–G4；
- 风险：D17 运营域；
- P2/P4：`P2-SKU`、`P2-RISK`、`P4C-FLAGGED`、`P4C-PAIRS`、`P4-C-GROUP`。

每条包含层级、分子、分母、观察期、样本范围、缺失/小样本规则、源表和备注。

### 4.2 数据契约测试

- 898 / 888 / 10 样本；
- 总指数 4,493,660.787；
- 风险域 581/175/101/25/4/2；多风险 132；
- 117 flagged / 35 multi；1,237 对；
- 16 组四象限×结构群，合计 888，5 个 n<20；
- P4-C 报表与 P3-D/P4-B 冻结值一致。

---

## 5. 只读保护与数据版本

| 机制 | 实现 |
|---|---|
| 源文件只读 | DuckDB 仅 `read_csv_auto`/`read_parquet`；无 `INSERT/COPY/ATTACH` |
| SQL 白名单 | 仅允许 `SELECT/WITH`；拒绝写入/DDL/外部读取函数/多语句 |
| 外部访问限制 | `enable_external_access=false`；`allowed_directories` 仅限 `data/`；禁用扩展自动安装/加载；`lock_configuration=true` |
| 无持久库 | 内存 DuckDB + 视图；不新建数据库文件 |
| 启动校验 | `freeze.verify_manifest()` 校验 22 个源文件 SHA-256 |
| 版本 | `p1-p4-freeze-2026-11-08`，所有响应 `meta.data_version` |
| 数据边界 | 不读取 eval；不查询 `clean_train` 行级；不重算 P1–P4 指标 |

**测试结果**：`DELETE`、多语句、`read_csv_auto` 外部路径均被拒绝；DuckDB 直接外部文件访问返回 `PermissionException`。

---

## 6. FastAPI 接口与 Pydantic 模型

### 6.1 已实现接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/health` | 状态、版本、视图行数 |
| GET | `/api/v1/meta/catalog` | 指标字典/页面映射 |
| GET | `/api/v1/meta/filters` | 城市、象限、G1–G4、类别、风险域 |
| GET | `/api/v1/overview/kpis` | 总览 KPI |
| GET | `/api/v1/overview/trend` | 日趋势（日期仅显示窗口） |
| GET | `/api/v1/overview/time-profile` | 小时、星期、星期×小时 |
| GET | `/api/v1/cities` | 城市对比 |
| GET | `/api/v1/stores/scatter` | 门店四象限散点（888） |
| GET | `/api/v1/stores` | 门店筛选/分页 |
| GET | `/api/v1/stores/groups` | 四象限×结构群，n<20 抑制 |
| GET | `/api/v1/stores/{store_id}` | 门店详情 |
| GET | `/api/v1/products` | 风险 SKU 列表 |
| GET | `/api/v1/products/{product_id}` | SKU 详情 |
| GET | `/api/v1/risk/summary` | 风险域汇总 |
| GET | `/api/v1/risk/combinations` | 至少/恰好组合 |
| GET | `/api/v1/export/stores.csv` | 聚合门店 CSV |

### 6.2 Pydantic 模型

- `Meta`：`n`、`period`、`data_version`、`sample_scope`、`suppressed`、`definitions`、`display_window`；
- `Envelope[T]`：`data`、`meta`、`warnings`；
- `Kpi`、`TrendPoint`、`CityRow`、`StoreRow`、`StoreGroupRow`、`ProductRow`、`RiskDomainRow`、`RiskComboRow`、`FilterOptions`、`CatalogOut`、`Health`。

**小样本规则**：`StoreGroupRow` 对 n<20 返回 `suppressed=true`，统计字段 null；Q2-G1 仍返回 `stores=0`。

**CSV 导出**：仅聚合门店字段；不含 `store×SKU` 明细、原始 train 或 SKU 粒度明细；首行包含 `data_version`、`period`、`filters`、边界说明。

---

## 7. 查询性能（本地只读）

环境：Windows 11、Python 3.13.9；20 次迭代；数据版本 `p1-p4-freeze-2026-11-08`。

| 操作 | 行数 | P50 | P95 |
|---|---:|---:|---:|
| 视图初始化（一次性） | 22 views | 277.1 ms | — |
| 总览 KPI | 898 | 90.6 ms | 98.8 ms |
| 90 天趋势 | 90 | 3.0 ms | 4.5 ms |
| 城市列表 | 18 | 12.3 ms | 14.4 ms |
| 门店分页 50 | 888（meta n） | 123.4 ms | 126.7 ms |
| 门店详情 | 1 | 64.0 ms | 68.0 ms |
| 四象限×结构群 | 16 | 5.0 ms | 6.2 ms |
| 风险 SKU 50 | 117（meta n） | 12.0 ms | 14.1 ms |
| 精确组合 | 16 | 4.0 ms | 5.4 ms |
| 至少组合 | 10 | 4.1 ms | 6.1 ms |
| 聚合门店导出 | 893 行 | 138.8 ms | 142.5 ms |
| 健康检查（全部视图计数） | 22 | 247.0 ms | 262.0 ms |

**结论**：当前数据规模下，核心查询 P95 均低于 150ms；无需 BI mart。后续数据量增大或增加复杂下钻时再评估只读 mart。

---

## 8. 测试结果

```text
python -m pytest bi/tests -q
15 passed

python -m pytest tests bi/tests -q
77 passed
```

覆盖：

- manifest 22 文件校验；
- 22 视图行数与核心总量；
- 898/888/10；
- 581/175/101/25/4/2、132；
- 117/35、1,237、16/10；
- 小样本抑制 5 个、Q2-G1=0；
- 10 家 SKU<10 门店详情 `不适用`、风险字段 null；
- 只读 SQL 拒绝写入/多语句；
- API 健康、KPI、趋势日期窗口、门店筛选、组合、导出；
- 无 eval 引用。

**发现并已修复的工程问题**：10 家 SKU<10 门店详情的 `domain_count` 为 NaN，导致 Pydantic `finite_number` 校验失败；已统一将 NaN 转 None，并新增 API 测试。未改任何 P1–P4 数据。

---

## 9. 问题与限制

1. **日期筛选**：KPI 固定 90 天；日期只改变趋势显示窗口。API 与 UI 必须显著说明。
2. **API 仅本机**：`__main__` 绑定 `127.0.0.1`；未实现登录/权限；未来开放内网前必须补认证。
3. **无 BI mart**：当前直接读 CSV/Parquet；视图初始化约 264ms，核心查询可接受。若增加复杂下钻，再评估只读 mart。
4. **未实现 React/ECharts/Docker**：按 BI-0 范围仅完成数据层与 API 草案。
5. **风险组合完整性**：`v_risk_exact` 使用 P4-B 16 组合；`v_risk_at_least` 10 对；与冻结结果一致。
6. **小样本**：API 已抑制 n<20；前端仍必须使用统一 `SuppressedValue` 组件，防止绕过。
7. **数据版本**：manifest 只覆盖 BI 使用的 22 个源文件，不覆盖全部 P1–P4 文件；后续可扩展为全量 manifest。
8. **FastAPI TestClient 警告**：`httpx` 与 Starlette TestClient 的弃用提示，不影响运行；升级依赖时处理。

---

## 10. 是否建议进入 BI-1

**建议进入 BI-1**，但先确认：

- BI-0 的 22 个视图/API 契约是否满足第一批页面；
- 是否接受“KPI 固定 90 天、日期只影响趋势”的交互；
- 是否接受 CSV 导出仅含聚合门店字段；
- 前端是否先只做本机只读（无登录）。

**BI-1 建议范围**：应用壳、总览页、城市与门店页、风险页；商品/联动下钻留到后续批次。

---

> 本轮仅新增 `bi/` 代码、数据契约、测试与基准；未修改 P1–P4 任何文件；未读取 eval；未运行 P1–P4 分析入口；未执行 Git commit/push。

