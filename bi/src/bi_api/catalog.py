"""BI 指标字典与页面映射（静态只读）。"""

from __future__ import annotations

import pandas as pd

from . import config


def load_metrics() -> list[dict]:
    return pd.read_csv(config.METRIC_DICTIONARY).fillna("").to_dict("records")


def load_page_map() -> list[dict]:
    return pd.read_csv(config.PAGE_TABLE_MAP).fillna("").to_dict("records")


def metric_index() -> dict[str, dict]:
    return {str(r["metric_id"]): r for r in load_metrics()}
