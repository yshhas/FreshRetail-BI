"""项目级配置：路径、数据集契约、口径常量。"""

import os
from pathlib import Path

# ---- 路径 ----
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
# 原始数据不随仓库分发；可通过 FRESH_RETAIL_RAW_DIR 指向本机下载目录。
RAW_DIR = Path(os.environ.get("FRESH_RETAIL_RAW_DIR", DATA_DIR / "raw" / "freshretailnet50k"))
DERIVED_DIR = DATA_DIR / "derived"
LOG_DIR = PROJECT_ROOT / "logs"

TRAIN_PATH = RAW_DIR / "train.parquet"
EVAL_PATH = RAW_DIR / "eval.parquet"

DATASET_NAME = "FreshRetailNet-50K"
RULE_VERSION = "1.0.0"

# ---- 官方文件契约（来自 Hugging Face LFS manifest）----
EXPECTED_FILES = {
    "train.parquet": {
        "size": 106436287,
        "sha256": "6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d",
        "rows": 4500000,
        "columns": 19,
    },
    "eval.parquet": {
        "size": 8440124,
        "sha256": "1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e",
        "rows": 350000,
        "columns": 19,
    },
}

# ---- 字段与主键 ----
COLUMNS = [
    "city_id",
    "store_id",
    "management_group_id",
    "first_category_id",
    "second_category_id",
    "third_category_id",
    "product_id",
    "dt",
    "sale_amount",
    "hours_sale",
    "stock_hour6_22_cnt",
    "hours_stock_status",
    "discount",
    "holiday_flag",
    "activity_flag",
    "precpt",
    "avg_temperature",
    "avg_humidity",
    "avg_wind_level",
]
KEY_COLUMNS = ("dt", "store_id", "product_id")

# ---- 时间范围（第四阶段实测）----
TRAIN_START = "2024-03-28"
TRAIN_END = "2024-06-25"
EVAL_START = "2024-06-26"
EVAL_END = "2024-07-02"

# ---- 业务口径常量 ----
# 官方说明为 6:00-22:00；实测 stock_hour6_22_cnt 恰好等于 hours_stock_status[6:22] 之和，
# 即索引 6..21，共 16 个小时槽位，因此分母固定为 16。
STOCK_WINDOW_START = 6
STOCK_WINDOW_END = 22  # 不含 22 点
STOCK_WINDOW_HOURS = 16

# sale_amount 的官方定义是"全局归一化销售数量"，禁止按金额解释。
SALES_INDEX_NOTE = "全局归一化销售数量（归一化销量指数），非金额、非件数"
