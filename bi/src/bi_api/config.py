"""BI-0 路径与版本配置。"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BI_ROOT = PROJECT_ROOT / "bi"
DATA_ROOT = Path(os.environ.get("BI_DATA_ROOT", PROJECT_ROOT / "data"))
MANIFEST_PATH = BI_ROOT / "data" / "freeze_manifest.json"
METRIC_DICTIONARY = BI_ROOT / "data" / "metric_dictionary.csv"
PAGE_TABLE_MAP = BI_ROOT / "data" / "page_table_map.csv"

PERIOD_START = "2024-03-28"
PERIOD_END = "2024-06-25"
PERIOD_LABEL = f"{PERIOD_START}/{PERIOD_END}"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def data_version() -> str:
    try:
        return str(load_manifest().get("version", "unknown"))
    except FileNotFoundError:
        return "unknown"
