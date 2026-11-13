"""流水线编排：校验 → 清洗 → 聚合 → 落盘 → 日志。"""

from __future__ import annotations

import time

import pandas as pd

from . import config, contracts, db, io, metrics, cleaning
from .logging_utils import RunLogger


def _null_counts_sql(table: str) -> str:
    cols = ",\n           ".join(
        f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS n_{c}" for c in config.COLUMNS
    )
    return f"SELECT {cols} FROM {table}"


def _raw_checks(con, table: str) -> dict:
    rows = db.scalar(con, f"SELECT count(*) FROM {table}")
    uniq = db.scalar(
        con,
        f"SELECT count(*) FROM (SELECT DISTINCT dt, store_id, product_id FROM {table})",
    )
    dates = con.execute(
        f"SELECT min(dt)::DATE, max(dt)::DATE, count(DISTINCT dt::DATE) FROM {table}"
    ).fetchone()
    nulls = con.execute(_null_counts_sql(table)).df().iloc[0].to_dict()
    nulls = {k.replace("n_", ""): int(v) for k, v in nulls.items()}
    neg = con.execute(
        "SELECT "
        + ", ".join(
            f"SUM(CASE WHEN {c} < 0 THEN 1 ELSE 0 END) AS {c}"
            for c in ("sale_amount", "stock_hour6_22_cnt", "holiday_flag",
                      "activity_flag", "precpt", "avg_temperature",
                      "avg_humidity", "avg_wind_level")
        )
        + f" FROM {table}"
    ).df().iloc[0].to_dict()
    return {
        "rows": int(rows),
        "distinct_keys": int(uniq),
        "duplicate_keys": int(rows - uniq),
        "date_min": str(dates[0]),
        "date_max": str(dates[1]),
        "unique_dates": int(dates[2]),
        "nulls": nulls,
        "negatives": {k: int(v) for k, v in neg.items() if int(v) > 0},
    }


def _clean_checks(con, table: str) -> dict:
    row = con.execute(
        f"""
        SELECT COUNT(*) AS rows,
               SUM(CASE WHEN sales_index IS NULL THEN 1 ELSE 0 END) AS null_sales,
               SUM(CASE WHEN discount_missing THEN 1 ELSE 0 END) AS discount_missing,
               SUM(CASE WHEN discount_out_of_range THEN 1 ELSE 0 END) AS discount_out_of_range,
               SUM(CASE WHEN promo_flag THEN 1 ELSE 0 END) AS promo_rows,
               SUM(CASE WHEN stockout_day_flag THEN 1 ELSE 0 END) AS stockout_rows,
               SUM(CASE WHEN sales_zero_flag THEN 1 ELSE 0 END) AS zero_sales_rows,
               MIN(stockout_rate_6_22) AS min_stockout_rate,
               MAX(stockout_rate_6_22) AS max_stockout_rate,
               MIN(sales_index) AS min_sales,
               MAX(sales_index) AS max_sales
        FROM {table}
        """
    ).df().iloc[0].to_dict()
    return {k: (int(v) if isinstance(v, (int,)) or k.endswith("rows") or k.startswith("null") else float(v))
            for k, v in row.items()}


def run(skip_hash: bool = False) -> dict:
    t0 = time.time()
    io.ensure_dirs()
    log = RunLogger("pipeline")
    log.log("start", dataset=config.DATASET_NAME, rule_version=config.RULE_VERSION)

    report: dict = {"dataset": config.DATASET_NAME, "rule_version": config.RULE_VERSION}

    # 1) 文件校验
    if skip_hash:
        files = {"train.parquet": "skipped", "eval.parquet": "skipped"}
        log.log("file_verify_skipped")
    else:
        files = {
            "train.parquet": io.verify_file(config.TRAIN_PATH, config.EXPECTED_FILES["train.parquet"]),
            "eval.parquet": io.verify_file(config.EVAL_PATH, config.EXPECTED_FILES["eval.parquet"]),
        }
        log.log("file_verified", train_hash=files["train.parquet"]["sha256"][:12],
                eval_hash=files["eval.parquet"]["sha256"][:12])
    report["files"] = files

    # 2) 元数据契约
    meta = {
        "train": contracts.check_file_metadata(config.TRAIN_PATH, config.EXPECTED_FILES["train.parquet"]),
        "eval": contracts.check_file_metadata(config.EVAL_PATH, config.EXPECTED_FILES["eval.parquet"]),
    }
    report["metadata"] = meta
    log.log("metadata_ok", train_rows=meta["train"]["rows"], eval_rows=meta["eval"]["rows"])

    con = db.connect()

    # 3) 原始视图 + 质量检查
    db.create_raw_view(con, "raw_train", config.TRAIN_PATH)
    db.create_raw_view(con, "raw_eval", config.EVAL_PATH)
    raw = {"train": _raw_checks(con, "raw_train"), "eval": _raw_checks(con, "raw_eval")}
    report["raw_checks"] = raw
    for name, r in raw.items():
        if r["duplicate_keys"]:
            raise contracts.DataContractError(f"{name} 主键重复 {r['duplicate_keys']}")
        if any(v for v in r["nulls"].values()):
            raise contracts.DataContractError(f"{name} 存在空值：{r['nulls']}")
        if r["negatives"]:
            raise contracts.DataContractError(f"{name} 存在负值：{r['negatives']}")
    split = contracts.check_split(
        pd.Series([raw["train"]["date_min"], raw["train"]["date_max"]]),
        pd.Series([raw["eval"]["date_min"], raw["eval"]["date_max"]]),
    )
    report["split"] = split
    log.log("raw_checks_ok", train_rows=raw["train"]["rows"], eval_rows=raw["eval"]["rows"],
            split=split)

    # 4) 清洗表
    n_train = db.build_clean_table(con, "raw_train", config.DERIVED_DIR / "clean_train.parquet")
    n_eval = db.build_clean_table(con, "raw_eval", config.DERIVED_DIR / "clean_eval.parquet")
    log.log("clean_tables_written", train_rows=n_train, eval_rows=n_eval)

    db.create_raw_view(con, "clean_train", config.DERIVED_DIR / "clean_train.parquet")
    db.create_raw_view(con, "clean_eval", config.DERIVED_DIR / "clean_eval.parquet")

    clean = {"train": _clean_checks(con, "clean_train"), "eval": _clean_checks(con, "clean_eval")}
    report["clean_checks"] = clean
    log.log("clean_checks_ok", train=clean["train"], eval=clean["eval"])

    # 5) 指标与派生表
    outputs = {
        "agg_daily.parquet": metrics.daily_summary(con, "clean_train"),
        "agg_store_day.parquet": metrics.store_day(con, "clean_train"),
        "agg_store_summary.parquet": metrics.store_summary(con, "clean_train"),
        "agg_product_summary.parquet": metrics.product_summary(con, "clean_train"),
        "agg_city_summary.parquet": metrics.city_summary(con, "clean_train"),
        "agg_category_day.parquet": metrics.category_day(con, "clean_train"),
        "agg_hour_profile.parquet": metrics.hour_profile(con, "clean_train"),
        "agg_hour_weekday.parquet": metrics.hour_weekday(con, "clean_train"),
        "diag_stockout_gradient.parquet": metrics.stockout_gradient(con, "clean_train"),
        "diag_promo_paired.parquet": metrics.promo_paired(con, "clean_train"),
        "diag_weather_bins.parquet": metrics.weather_bins(con, "clean_train"),
    }
    outputs["diag_anomaly_days.parquet"] = metrics.anomaly_days(outputs["agg_daily.parquet"])
    outputs["agg_store_health.parquet"] = metrics.health_score(outputs["agg_store_summary.parquet"])

    written = {}
    for name, df in outputs.items():
        path = config.DERIVED_DIR / name
        df.to_parquet(path, index=False)
        written[name] = int(len(df))
    report["derived_tables"] = written
    log.log("derived_written", tables=written)

    # 6) 元数据与日志
    io.write_json(config.DERIVED_DIR / "_cleaning_rules.json", cleaning.rules_payload())
    io.write_json(config.DERIVED_DIR / "_metric_catalog.json", {"metrics": metrics.metric_catalog()})
    report["run"] = {"elapsed_seconds": round(time.time() - t0, 2), "log_file": str(log.path)}
    io.write_json(config.DERIVED_DIR / "_quality_report.json", report)
    log.log("done", elapsed=report["run"]["elapsed_seconds"])
    report["logger_summary"] = log.summary()
    return report


if __name__ == "__main__":
    run()
