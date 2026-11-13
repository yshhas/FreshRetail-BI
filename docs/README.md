# 文档索引

本目录只保留可公开发布的技术文档。内部审计、验收、整改和开发过程记录已移出公开仓库，不在 Git 跟踪范围内。

## 先读

1. [项目全生命周期复盘](engineering-review.md)：项目目标、关键决策、问题与解决过程；
2. [研发指南总入口](development-guide-index.md)：66 个工作单元（W001–W066）的阅读路径；
3. [项目全景与阅读指南](project_development_guide/00_项目全貌与阅读指南.md)：数据、模块、产物与边界。

## 分析报告

| 报告 | 内容 |
|---|---|
| [P1 销量经营](reports/p1-sales.md) | 90 天趋势、星期/小时、门店表现、异常日、持续低销 |
| [P2 商品经营](reports/p2-product.md) | SKU 双榜、帕累托/长尾、类目、风险旗标 |
| [P3A 城市经营](reports/p3a-city.md) | 城市对比、相关性、城市结构 |
| [P3B 门店分层](reports/p3b-store.md) | 规模/效率、稳健回归、四象限 |
| [P3C 商品结构](reports/p3c-structure.md) | HHI/熵、类目渗透、聚类、相似度 |
| [P3D 缺货与风险](reports/p3d-risk.md) | 缺货两口径、R1–R8、精确/至少组合 |
| [P4 经营诊断](reports/p4-diagnosis.md) | 门店档案、诊断规则、SKU–门店覆盖 |
| [数据获取与质量核验](reports/data-quality.md) | 数据来源、许可、文件校验与质量结论 |

## 设计文档

| 文档 | 内容 |
|---|---|
| [BI 产品需求与技术架构](design/bi-architecture.md) | BI 目标、页面、接口与数据边界 |
| [数据契约与只读访问层](design/data-contract.md) | 25 项冻结 manifest、只读视图、契约 |
| [商品 BI 方案](design/product-bi.md) | 商品页面、指标与数据可行性 |
| [跨页面联动与下钻](design/cross-page-navigation.md) | URL 状态、返回栈、组合筛选 |

## 项目复盘与研发纪实

- [项目复盘：01 起源与需求](project-review/01_project_origin_and_requirements.md)
- [项目复盘：02 架构与技术](project-review/02_architecture_and_technology.md)
- [项目复盘：03 核心模块](project-review/03_core_modules.md)
- [项目复盘：04 研发演进](project-review/04_development_evolution.md)
- [项目复盘：05 问题与解决](project-review/05_problems_and_solutions.md)
- [项目复盘：06 技术决策](project-review/06_technical_decisions.md)
- [项目复盘：07 测试与交付](project-review/07_testing_and_delivery.md)
- [研发纪实：01 起源与想法](project-story/01_origin_and_idea.md)
- [研发纪实：02 早期调研与决策](project-story/02_early_research_and_decisions.md)
- [研发纪实：03 基础设施与架构](project-story/03_foundation_and_architecture.md)
- [研发纪实：04 核心开发](project-story/04_core_development.md)
- [研发纪实：05 困难与变化](project-story/05_difficulties_and_changes.md)
- [研发纪实：06 产品演进](project-story/06_product_evolution.md)
- [研发纪实：07 最终交付](project-story/07_final_delivery.md)

## 研发指南分册

| 分册 | 内容 |
|---|---|
| [00 项目全貌与阅读指南](project_development_guide/00_项目全貌与阅读指南.md) | 阅读路径、目录、边界 |
| [01 需求与数据选型](project_development_guide/01_需求与数据选型.md) | 候选数据集、FreshRetailNet、范围裁剪 |
| [02 数据基础设施与清洗](project_development_guide/02_数据基础设施与清洗.md) | 分层、契约、清洗、DuckDB、聚合 |
| [03 P1 销量与 P2 商品分析](project_development_guide/03_P1销量与P2商品分析.md) | 三层口径、稳健 z、SKU 双榜 |
| [04 P3 区域、门店、结构与风险](project_development_guide/04_P3区域门店结构与风险.md) | 城市/门店/结构/风险 |
| [05 P4 诊断与数据冻结](project_development_guide/05_P4诊断与数据冻结.md) | 诊断规则、incidence、冻结 |
| [06 BI 后端与接口](project_development_guide/06_BI后端与接口.md) | 只读视图、API 契约 |
| [07 BI 前端与跨页联动](project_development_guide/07_BI前端与跨页联动.md) | 路由、URL 状态、下钻 |
| [08 测试、验收与交付](project_development_guide/08_测试验收与交付.md) | pytest、Vitest、E2E、冻结核验 |
| [项目完整研发因果链](project_development_guide/项目完整研发因果链.md) | 从需求到交付的因果链 |
| [项目研发工作总索引](project_development_guide/项目研发工作总索引.md) | 工作单元索引 |
| [项目证据与待确认事项](project_development_guide/项目证据与待确认事项.md) | 证据等级与未确认事项 |

## 相关入口

- [项目主页](../README.md)
- [BI 运行说明](../bi/README.md)
- [数据说明](../data/README.md)
