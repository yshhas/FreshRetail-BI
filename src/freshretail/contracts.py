"""数据契约：字段、类型、行数、主键唯一性、日期连续性。"""

from __future__ import annotations

import pyarrow.parquet as pq
import pandas as pd

from . import config


class DataContractError(AssertionError):
    """数据契约不满足时抛出。"""


EXPECTED_SCHEMA = {
    "city_id": "int64",
    "store_id": "int64",
    "management_group_id": "int64",
    "first_category_id": "int64",
    "second_category_id": "int64",
    "third_category_id": "int64",
    "product_id": "int64",
    "dt": "string",
    "sale_amount": "double",
    "hours_sale": "list<element: double>",
    "stock_hour6_22_cnt": "int32",
    "hours_stock_status": "list<element: int64>",
    "discount": "double",
    "holiday_flag": "int32",
    "activity_flag": "int32",
    "precpt": "double",
    "avg_temperature": "double",
    "avg_humidity": "double",
    "avg_wind_level": "double",
}


def check_file_metadata(path, expected: dict) -> dict:
    """核对文件行数、列数、字段名与类型。"""
    pf = pq.ParquetFile(path)
    schema = pf.schema_arrow
    actual = {"rows": pf.metadata.num_rows, "columns": pf.metadata.num_columns,
              "names": schema.names}
    problems = []
    if actual["rows"] != expected["rows"]:
        problems.append(f"行数不符：{actual['rows']} != {expected['rows']}")
    if actual["columns"] != expected["columns"]:
        problems.append(f"列数不符：{actual['columns']} != {expected['columns']}")
    if schema.names != config.COLUMNS:
        problems.append(f"字段顺序/名称不符：{schema.names}")
    for i, field in enumerate(schema):
        exp = EXPECTED_SCHEMA.get(field.name)
        if exp is None:
            continue
        if str(field.type) != exp:
            problems.append(f"字段 {field.name} 类型不符：{field.type} != {exp}")
    if problems:
        raise DataContractError("；".join(problems))
    return actual


def check_frame(df: pd.DataFrame, name: str, require_continuous_dates: bool = True) -> dict:
    """对已加载的数据做完整性检查，返回质量报告。"""
    report = {"name": name, "rows": int(len(df))}

    nulls = {c: int(df[c].isna().sum()) for c in df.columns}
    report["nulls"] = nulls
    bad_nulls = {k: v for k, v in nulls.items() if v}
    if bad_nulls:
        raise DataContractError(f"{name} 存在空值：{bad_nulls}")

    dup = int(df.duplicated(subset=list(config.KEY_COLUMNS)).sum())
    report["duplicate_keys"] = dup
    if dup:
        raise DataContractError(f"{name} 主键重复 {dup} 条")

    report["duplicate_rows"] = int(df.duplicated().sum())

    dt = pd.to_datetime(df["dt"], errors="coerce")
    if dt.isna().any():
        raise DataContractError(f"{name} 存在无法解析的日期")
    report["date_min"] = str(dt.min().date())
    report["date_max"] = str(dt.max().date())
    report["unique_dates"] = int(dt.nunique())

    if require_continuous_dates:
        expected_days = (dt.max() - dt.min()).days + 1
        report["expected_days"] = int(expected_days)
        if report["unique_dates"] != expected_days:
            raise DataContractError(
                f"{name} 日期不连续：唯一日期 {report['unique_dates']} != 区间天数 {expected_days}"
            )

    neg = {c: int((df[c] < 0).sum()) for c in df.columns
           if pd.api.types.is_numeric_dtype(df[c]) and c not in ("discount",)}
    report["negative_counts"] = {k: v for k, v in neg.items() if v}
    if report["negative_counts"]:
        raise DataContractError(f"{name} 存在负值：{report['negative_counts']}")

    return report


def check_split(train_dates, eval_dates) -> dict:
    """train 与 eval 必须时间不重叠，且 eval 紧接 train。"""
    tr = pd.to_datetime(pd.Series(train_dates))
    ev = pd.to_datetime(pd.Series(eval_dates))
    overlap = set(tr.dt.normalize()) & set(ev.dt.normalize())
    if overlap:
        raise DataContractError(f"train 与 eval 日期重叠：{sorted(overlap)[:5]}")
    gap = (ev.min() - tr.max()).days
    if gap != 1:
        raise DataContractError(f"eval 未紧接 train：间隔 {gap} 天")
    return {
        "train_min": str(tr.min().date()),
        "train_max": str(tr.max().date()),
        "eval_min": str(ev.min().date()),
        "eval_max": str(ev.max().date()),
        "gap_days": int(gap),
        "overlap": 0,
    }
