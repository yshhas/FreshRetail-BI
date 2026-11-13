# 项目全生命周期研发指南（总入口）

> 这是一套“研发工作单元”级文档，共 66 个工作单元（W001–W066），每个单元都对应真实代码、数据、接口、页面或测试。
>
> 完整 PDF 已归档，不在公开仓库分发；公开仓库保留 Markdown 分册。

---

## 从哪里开始

1. 先读 [00 项目全貌与阅读指南](project_development_guide/00_项目全貌与阅读指南.md)
2. 再读 [项目完整研发因果链](project_development_guide/项目完整研发因果链.md)
3. 查具体工作单元：[项目研发工作总索引](project_development_guide/项目研发工作总索引.md)
4. 核对证据：[项目证据与待确认事项](project_development_guide/项目证据与待确认事项.md)

---

## 分册

| 文档 | 工作单元 | 内容 |
|---|---|---|
| [01 需求与数据选型](project_development_guide/01_需求与数据选型.md) | W001–W008 | 六模块设想、候选数据集、FreshRetailNet、口径纠正、需求裁剪 |
| [02 数据基础设施与清洗](project_development_guide/02_数据基础设施与清洗.md) | W009–W016 | 分层、契约、清洗规则、DuckDB、聚合、流水线、首轮测试 |
| [03 P1 销量与 P2 商品分析](project_development_guide/03_P1销量与P2商品分析.md) | W017–W024 | 三层口径、稳健 z、持续低销、SKU 双榜、风险旗标、分母修正 |
| [04 P3 区域、门店、结构与风险](project_development_guide/04_P3区域门店结构与风险.md) | W025–W033 | 城市/门店/结构/风险、Huber、HHI、R1–R8、精确/至少 |
| [05 P4 诊断与数据冻结](project_development_guide/05_P4诊断与数据冻结.md) | W034–W040 | 门店档案、诊断规则、incidence、16 格、n<20 整改、25 项冻结 |
| [06 BI 后端与接口](project_development_guide/06_BI后端与接口.md) | W041–W047 | 25 视图、freeze、API 契约、门店/风险/商品接口、只读安全 |
| [07 BI 前端与跨页联动](project_development_guide/07_BI前端与跨页联动.md) | W048–W060 | 路由、URL 状态、页面、共现五态、返回、路径安全 |
| [08 测试、验收与交付](project_development_guide/08_测试验收与交付.md) | W061–W066 | pytest/Vitest、E2E、C-4 回归、构建、冻结、本地运行 |

---

## 关键原则

- 每个工作单元都写清：背景、输入、步骤、原理、产物、实例、问题、验证、下游；
- 有证据的写“直接证据”，推断的标“工程推断”，无法确认的标“无法确认”；
- 不编造开发对话、失败经历或时间线；
- 未读取 `eval.parquet`，未修改业务代码/数据/配置/冻结文件。

---

## 相关文档

- 研发纪实（故事版）：[研发纪实 01 起源与想法](project-story/01_origin_and_idea.md)
- 复盘报告：[工程复盘](engineering-review.md)
- 运行说明：[项目主页](../README.md)、[BI 运行说明](../bi/README.md)
