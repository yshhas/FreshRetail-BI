# BI 平台：BI-0 / BI-1 / BI-2

本目录是 FreshRetailNet 零售经营 BI 的后端与前端实现，只读查询 P1–P4 冻结结果，不提供写入接口。

| 阶段 | 实际完成内容 |
|---|---|
| BI-0 | 数据契约与只读访问层：25 项冻结 manifest、DuckDB 只读视图、FastAPI 契约、启动校验 |
| BI-1 | 第一批页面：经营总览、城市与门店、经营风险、门店详情；筛选状态写入 URL |
| BI-2 | 商品 BI：商品总览/列表/风险/分类/详情；跨页状态与多级返回；精确/至少组合筛选；小样本抑制 |

## 目录

```text
bi/
├─ data/
│  ├─ freeze_manifest.json       # 25 个冻结文件的 SHA-256 + 字节数
│  ├─ metric_dictionary.csv      # D1–D17 与 P4 指标定义
│  └─ page_table_map.csv         # 页面/组件 -> 源表映射
├─ src/bi_api/
│  ├─ config.py                  # 路径、观察期、数据版本
│  ├─ freeze.py                  # 冻结文件校验
│  ├─ db.py                      # DuckDB 只读视图 + SQL 白名单
│  ├─ catalog.py                 # 指标字典/页面映射
│  ├─ models.py                  # Pydantic 响应模型
│  ├─ service.py                 # 只读查询服务
│  └─ main.py                    # FastAPI 应用
├─ tests/                        # 后端契约/API 测试
├─ benchmarks/                   # 只读性能基准
├─ screenshots/                  # 真实 UI / E2E 截图
└─ web/                          # React + TypeScript + Vite 前端
```

## 运行前提

BI 运行只需仓库内已提交的冻结数据，不需要原始 `data/raw/`：

- `bi/data/freeze_manifest.json`
- `data/derived/agg_daily.parquet`
- `data/derived/agg_hour_profile.parquet`
- `data/derived/agg_hour_weekday.parquet`
- `data/analysis/` 下的 P1–P4 冻结 CSV

共 25 个冻结文件，约 5.34 MB。API 启动时会执行 `freeze.verify_manifest()`，缺失或哈希不一致会拒绝启动。

## 启动后端

在仓库根目录执行：

```powershell
$env:PYTHONPATH = "bi/src"
python -m uvicorn bi_api.main:app --host 127.0.0.1 --port 8000
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- 仅绑定 `127.0.0.1`，不默认暴露公网。

主要接口：

```text
GET /api/v1/health
GET /api/v1/meta/catalog
GET /api/v1/meta/filters
GET /api/v1/overview/kpis
GET /api/v1/overview/trend
GET /api/v1/overview/time-profile
GET /api/v1/cities
GET /api/v1/stores
GET /api/v1/stores/{store_id}
GET /api/v1/stores/{store_id}/skus
GET /api/v1/stores/scatter
GET /api/v1/stores/groups
GET /api/v1/products/overview
GET /api/v1/products
GET /api/v1/products/{product_id}
GET /api/v1/products/{product_id}/stores
GET /api/v1/products/{product_id}/pairs
GET /api/v1/risk/summary
GET /api/v1/risk/combinations
GET /api/v1/export/stores.csv
```

## 启动前端

```powershell
cd bi/web
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173/overview>。Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

生产构建与预览：

```powershell
npm run build
npm run preview
```

预览地址：<http://127.0.0.1:4173/>。

## 测试

```powershell
# 后端（只读契约/API/商品 BI/门店下钻）
python -m pytest bi/tests -q

# 前端单元测试（3 个文件，23 个用例）
cd bi/web
npm test

# 冻结校验
$env:PYTHONPATH = "bi/src"
python -c "from bi_api import freeze; print(freeze.verify_manifest())"
```

E2E 需要同时启动 API（8000）和前端 dev server（5173），并安装 Chrome/Chromium：

```powershell
cd bi/web
node tests/e2e.mjs
node tests/e2e-c1.mjs
node tests/e2e-c2.mjs
node tests/e2e-c3.mjs
node tests/e2e-c4.mjs
node tests/e2e-products.mjs
```

如果 Chrome 不在默认安装位置，设置：

```powershell
$env:CHROME_PATH = "C:\Path\To\chrome.exe"
```

`tests/browser.mjs` 会优先读取 `CHROME_PATH`，其次查找 Windows/macOS/Linux 的常见安装位置。

## 性能基准（可选）

```powershell
python bi/benchmarks/bench_bi0.py
```

基准结果写入 `bi/benchmarks/benchmark_results.json`。前端性能脚本为 `bi/web/tests/perf.mjs`，需要先启动预览服务（4173）。

## 数据契约

- `version = p1-p4-freeze-2026-11-08`：P1–P4 数据版本；
- `contract_version = bi0-contract-v2`：在 v1 的 22 个文件基础上，增量登记 BI-2 商品 BI 所需的 3 个成果：
  - `data/analysis/p4/p4_c_store_sku_incidence.csv`
  - `data/analysis/p2/t8_head_tail.csv`
  - `data/analysis/p3c/c3_category_penetration.csv`
- 原有 22 项路径与 SHA-256 保持不变；启动时校验全部 25 项，并检查重复键、路径合法性、哈希格式与字节数。

## 约束

- 不读取 `eval.parquet`；
- 不修改 P1–P4 冻结结果；
- 不重算 P1–P4 指标；
- 不提供写入接口或任意 SQL；
- KPI 固定 90 天，趋势日期筛选只改变显示窗口；
- 精确组合与至少组合是两套口径，不可相加；
- `n<20` 的统计由后端抑制并标记 `suppressed`；`SKU<10` 的门店不进入风险诊断。
