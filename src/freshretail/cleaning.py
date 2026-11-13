"""清洗规则：只新增派生列，不覆盖任何原始列。"""

from __future__ import annotations

import pandas as pd

from . import config

# 规则清单：每条规则可追溯到字段、条件、动作
RULES = [
    {
        "id": "R001",
        "field": "sale_amount",
        "condition": "always",
        "action": "新增 sales_index = sale_amount（仅复制，不改原值）",
        "note": config.SALES_INDEX_NOTE,
    },
    {
        "id": "R002",
        "field": "discount",
        "condition": "discount = 0",
        "action": "新增 discount_missing = TRUE；原始值保留",
        "note": "0 与官方定义（1.0=无折扣）冲突，视为缺失，不修改原字段",
    },
    {
        "id": "R003",
        "field": "discount",
        "condition": "discount > 1",
        "action": "新增 discount_out_of_range = TRUE；原始值保留",
        "note": "实测 34 行，最大 1.088，促销分析时排除",
    },
    {
        "id": "R004",
        "field": "discount",
        "condition": "0 < discount <= 1",
        "action": "新增 discount_valid = TRUE",
        "note": "有效折扣区间",
    },
    {
        "id": "R005",
        "field": "discount",
        "condition": "0 < discount < 1",
        "action": "新增 promo_flag = TRUE",
        "note": "1.0 视为无促销",
    },
    {
        "id": "R006",
        "field": "holiday_flag",
        "condition": "always",
        "action": "新增 holiday_proxy = holiday_flag",
        "note": "仅作休息日代理，不解释为法定节假日",
    },
    {
        "id": "R007",
        "field": "stock_hour6_22_cnt",
        "condition": "always",
        "action": "新增 stockout_hours_6_22 = stock_hour6_22_cnt",
        "note": "6:00-21:59 共 16 个槽位；实测与 hours_stock_status[6:22] 之和完全一致",
    },
    {
        "id": "R008",
        "field": "stock_hour6_22_cnt",
        "condition": "stock_hour6_22_cnt > 0",
        "action": "新增 stockout_day_flag = TRUE",
        "note": "日级缺货标记",
    },
    {
        "id": "R009",
        "field": "stock_hour6_22_cnt",
        "condition": "always",
        "action": "新增 stockout_rate_6_22 = stock_hour6_22_cnt / 16",
        "note": "分母 16 已由实测确认",
    },
    {
        "id": "R010",
        "field": "sale_amount",
        "condition": "sale_amount = 0",
        "action": "新增 sales_zero_flag = TRUE",
        "note": "零销量不等于零需求，可能受缺货约束",
    },
    {
        "id": "R011",
        "field": "activity_flag",
        "condition": "always",
        "action": "保留原值，不生成结论性派生列",
        "note": "业务含义未说明，仅作辅助变量",
    },
    {
        "id": "R012",
        "field": "precpt / avg_temperature / avg_humidity / avg_wind_level",
        "condition": "always",
        "action": "保留原值，不做单位换算",
        "note": "单位未标注",
    },
]

# DuckDB 派生列表达式（保持原始列不变）
DERIVED_SQL = {
    "sales_index": "sale_amount",
    "discount_raw": "discount",
    "discount_missing": "(discount = 0)",
    "discount_out_of_range": "(discount > 1)",
    "discount_valid": "(discount > 0 AND discount <= 1)",
    "promo_flag": "(discount > 0 AND discount < 1)",
    "holiday_proxy": "holiday_flag",
    "stockout_hours_6_22": "stock_hour6_22_cnt",
    "stockout_day_flag": "(stock_hour6_22_cnt > 0)",
    "stockout_rate_6_22": "(stock_hour6_22_cnt / 16.0)",
    "sales_zero_flag": "(sale_amount = 0)",
}


def select_clean_sql(table: str) -> str:
    """生成 SELECT：原始 19 列 + 派生列。"""
    derived = ",\n       ".join(f"{expr} AS {name}" for name, expr in DERIVED_SQL.items())
    return f"SELECT *,\n       {derived}\nFROM {table}"


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """pandas 版清洗（用于单元测试与小样本）。不修改入参。"""
    out = df.copy()
    out["sales_index"] = out["sale_amount"]
    out["discount_raw"] = out["discount"]
    out["discount_missing"] = out["discount"] == 0
    out["discount_out_of_range"] = out["discount"] > 1
    out["discount_valid"] = (out["discount"] > 0) & (out["discount"] <= 1)
    out["promo_flag"] = (out["discount"] > 0) & (out["discount"] < 1)
    out["holiday_proxy"] = out["holiday_flag"]
    out["stockout_hours_6_22"] = out["stock_hour6_22_cnt"]
    out["stockout_day_flag"] = out["stock_hour6_22_cnt"] > 0
    out["stockout_rate_6_22"] = out["stock_hour6_22_cnt"] / config.STOCK_WINDOW_HOURS
    out["sales_zero_flag"] = out["sale_amount"] == 0
    return out


def rules_payload() -> dict:
    return {"rule_version": config.RULE_VERSION, "rules": RULES}
