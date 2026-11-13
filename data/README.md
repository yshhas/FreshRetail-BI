# 数据说明

## 1. 数据来源

- 数据集：FreshRetailNet-50K
- 发布方：Dingdong-Inc（叮咚买菜）
- 官方地址：https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K
- 论文：https://arxiv.org/abs/2505.16319
- 许可证：CC BY 4.0（Hugging Face 数据集卡片已核实）

## 2. 原始数据（不随仓库分发）

原始数据体积约 109.55 MB，其中 `train.parquet` 为 106,436,287 字节，超过 GitHub 普通仓库单文件 100 MB 限制，因此**不提交到 Git**。

期望目录：

```text
data/raw/freshretailnet50k/
├─ train.parquet    106,436,287 bytes
└─ eval.parquet       8,440,124 bytes
```

SHA-256：

```text
train.parquet  6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d
eval.parquet   1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e
```

下载：

```powershell
pip install huggingface_hub
hf download Dingdong-Inc/FreshRetailNet-50K --repo-type dataset --local-dir data/raw/freshretailnet50k
```

Hugging Face 会保留 `data/` 子目录。若文件位于 `data/raw/freshretailnet50k/data/`，可以：

```powershell
# 方式一：把 parquet 移到期望目录
Move-Item data/raw/freshretailnet50k/data/*.parquet data/raw/freshretailnet50k/
Remove-Item data/raw/freshretailnet50k/data

# 方式二：通过环境变量指向实际目录
$env:FRESH_RETAIL_RAW_DIR = "data/raw/freshretailnet50k/data"
```

`src/freshretail/config.py` 支持 `FRESH_RETAIL_RAW_DIR` 覆盖默认路径；默认路径为 `data/raw/freshretailnet50k`。

## 3. 仓库内提交的数据

| 路径 | 内容 | 说明 |
|---|---|---|
| `data/analysis/` | P1–P4 分析结果 CSV、summary JSON | BI、测试和报告直接依赖 |
| `data/derived/agg_*.parquet` | 日/门店/商品/城市/时段等聚合表 | BI 运行必需 |
| `data/derived/diag_*.parquet` | 诊断辅助表 | 分析与复现使用 |
| `data/derived/_*.json` | 清洗规则、指标目录、质量报告 | 口径与质量证据 |
| `data/verification/freshretailnet50k_summary.json` | 原始数据核验摘要 | 数据来源与质量证据 |

**不提交**：

- `data/raw/`（原始数据）；
- `data/derived/clean_train.parquet`（可由原始数据重建）；
- `data/derived/clean_eval.parquet`（分析不使用，可重建）。

## 4. 冻结数据契约

BI 启动时校验 `bi/data/freeze_manifest.json` 中的 25 个文件（3 个派生 Parquet + 22 个分析 CSV），共约 5.34 MB。校验内容包括 SHA-256、字节数、重复键、路径合法性。

为了保证跨平台克隆后字节一致：

- `.gitattributes` 对 `data/**`、`bi/data/**`、`*.csv` 设置了 `-text`；
- 禁止 Git 对这些文件做 CRLF/LF 转换；
- 不要用编辑器批量保存冻结 CSV，也不要在 Windows 上让 Git 自动转换换行符。

校验命令：

```powershell
$env:PYTHONPATH = "bi/src"
python -c "from bi_api import freeze; print(freeze.verify_manifest())"
```

预期：`files_total=25`、`checked=25`。

## 5. 重建流程

```powershell
python scripts/build_derived.py     # 校验原始文件并生成 data/derived/
python scripts/run_p1.py
python scripts/run_p2.py
python scripts/run_p3a.py
python scripts/run_p3b.py
python scripts/run_p3c.py
python scripts/run_p3d.py
python scripts/run_p4.py
```

注意：

- 运行上述脚本会重新生成 `data/analysis/` 与 `reports/figures/`，可能覆盖当前冻结结果；
- 如果只是为了运行 BI，不需要重建，直接使用仓库内已提交的冻结结果；
- 如果需要验证复现一致性，建议先复制仓库到临时目录，再在副本中运行，并对比 `freeze_manifest.json` 中的 SHA-256；
- `eval.parquet` 不参与分析和 BI。

## 6. 测试与原始数据

- 干净克隆（无 `data/raw`、无 `clean_train.parquet`）：97 个基础测试通过，4 个集成测试自动跳过（3 个 `requires_raw` + 1 个 `requires_clean`），跳过原因会显示在 pytest 输出中；
- 仅有 `clean_train.parquet`（无原始数据）：98 passed, 3 skipped；
- 下载原始数据并运行 `scripts/build_derived.py` 后：101 个测试全部通过；
- 只跑基础测试：`pytest -m "not requires_raw and not requires_clean"`（97 个）；
- 只跑原始数据契约/抽样测试：`pytest -m requires_raw`（3 个）；
- 只跑清洗表测试：`pytest -m requires_clean`（1 个）。

## 7. 数据许可

原始数据为 CC BY 4.0。本仓库不重新分发原始数据；派生结果的使用需保留 `NOTICE` 中的署名、来源链接与许可声明。
