import hashlib
import json
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.environ.get("FRESH_RETAIL_RAW_DIR", ROOT / "data" / "raw" / "freshretailnet50k"))
TRAIN = BASE / "train.parquet"
EVAL = BASE / "eval.parquet"
OUT_DIR = ROOT / "data" / "verification"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED = {
    "train.parquet": {
        "size": 106436287,
        "sha256": "6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d",
    },
    "eval.parquet": {
        "size": 8440124,
        "sha256": "1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e",
    },
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def basic(path):
    name = os.path.basename(path)
    size = os.path.getsize(path)
    digest = sha256(path)
    md = pq.ParquetFile(path).metadata
    return {
        "file": name,
        "size_bytes": size,
        "expected_size": EXPECTED[name]["size"],
        "size_match": size == EXPECTED[name]["size"],
        "sha256": digest,
        "expected_sha256": EXPECTED[name]["sha256"],
        "hash_match": digest == EXPECTED[name]["sha256"],
        "rows": md.num_rows,
        "columns": md.num_columns,
        "row_groups": md.num_row_groups,
        "created_by": md.created_by,
    }


def col_stats(df, col):
    s = df[col]
    is_dt = pd.api.types.is_datetime64_any_dtype(s)
    return {
        "dtype": str(s.dtype),
        "null": int(s.isna().sum()),
        "nunique": int(s.nunique(dropna=True)),
        "min": None if s.dropna().empty else (str(s.min().date()) if is_dt else float(s.min())),
        "max": None if s.dropna().empty else (str(s.max().date()) if is_dt else float(s.max())),
        "mean": None if (s.dropna().empty or is_dt) else float(s.mean()),
    }


report = {}

for path in (TRAIN, EVAL):
    info = basic(path)
    report[os.path.basename(path)] = info
    print(f"\n=== {info['file']} ===")
    print(f"size={info['size_bytes']:,} expected={info['expected_size']:,} match={info['size_match']}")
    print(f"sha256={info['sha256']}")
    print(f"hash_match={info['hash_match']}")
    print(f"rows={info['rows']:,} cols={info['columns']} row_groups={info['row_groups']}")
    print(f"created_by={info['created_by']}")

train_schema = pq.ParquetFile(TRAIN).schema_arrow
eval_schema = pq.ParquetFile(EVAL).schema_arrow
print("\ntrain schema:\n", train_schema)
print("\neval schema:\n", eval_schema)

train_cols = set(train_schema.names)
eval_cols = set(eval_schema.names)
print("\ncolumns only in train:", sorted(train_cols - eval_cols))
print("columns only in eval:", sorted(eval_cols - train_cols))
report["schema_diff"] = {
    "only_train": sorted(train_cols - eval_cols),
    "only_eval": sorted(eval_cols - train_cols),
}

# ---- load train ----
print("\nloading train scalar columns ...")
key_cols = [
    "city_id", "store_id", "management_group_id",
    "first_category_id", "second_category_id", "third_category_id",
    "product_id", "dt", "sale_amount", "stock_hour6_22_cnt",
    "discount", "holiday_flag", "activity_flag",
    "precpt", "avg_temperature", "avg_humidity", "avg_wind_level",
]
tr = pq.read_table(TRAIN, columns=key_cols).to_pandas()
tr["dt"] = pd.to_datetime(tr["dt"], errors="coerce")

print("\n--- dtypes / nulls / cardinality ---")
stats = {c: col_stats(tr, c) for c in key_cols}
for c, s in stats.items():
    print(f"{c:24s} dtype={s['dtype']:8s} null={s['null']:>9,} nuniq={s['nunique']:>9,} "
          f"min={s['min']} max={s['max']} mean={None if s['mean'] is None else round(s['mean'], 6)}")
report["train_column_stats"] = stats

print("\n--- date range ---")
tr_dt = tr["dt"].dropna()
print("min dt:", tr_dt.min(), " max dt:", tr_dt.max())
uniq_dates = pd.Series(sorted(tr_dt.dt.normalize().unique()))
print("unique dates:", len(uniq_dates))
full_range = pd.date_range(uniq_dates.min(), uniq_dates.max(), freq="D", normalize=True)
missing = sorted(set(full_range) - set(uniq_dates))
print("calendar days in range:", len(full_range), " missing dates:", len(missing))
print("first 10 dates:", [str(d)[:10] for d in uniq_dates.head(10).tolist()])
print("last 10 dates:", [str(d)[:10] for d in uniq_dates.tail(10).tolist()])
print("missing sample:", [str(d)[:10] for d in missing[:10]])
report["train_dates"] = {
    "min": str(tr_dt.min()), "max": str(tr_dt.max()),
    "unique_dates": int(len(uniq_dates)),
    "calendar_days": int(len(full_range)),
    "missing_days": len(missing),
    "missing_sample": [str(d)[:10] for d in missing[:20]],
    "first_dates": [str(d)[:10] for d in uniq_dates.head(10).tolist()],
    "last_dates": [str(d)[:10] for d in uniq_dates.tail(10).tolist()],
}

print("\n--- duplicates on (dt, store_id, product_id) ---")
dup_mask = tr.duplicated(subset=["dt", "store_id", "product_id"], keep=False)
print("duplicate rows (all occurrences):", int(dup_mask.sum()))
print("duplicate keys:", int(tr[dup_mask][["dt", "store_id", "product_id"]].drop_duplicates().shape[0]))
full_dup = int(tr.duplicated(keep=False).sum())
print("fully duplicated rows:", full_dup)
report["train_duplicates"] = {
    "key_duplicate_rows": int(dup_mask.sum()),
    "key_duplicate_keys": int(tr[dup_mask][["dt", "store_id", "product_id"]].drop_duplicates().shape[0]),
    "full_duplicate_rows": full_dup,
}

print("\n--- sale_amount distribution ---")
sa = tr["sale_amount"].dropna()
qs = sa.quantile([0, 0.001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999, 1]).to_dict()
print(qs)
print("zeros:", int((sa == 0).sum()), f"({(sa == 0).mean():.4%})")
print("negatives:", int((sa < 0).sum()))
print("skew:", round(float(sa.skew()), 4))
report["sale_amount"] = {
    "count": int(sa.size),
    "quantiles": {str(k): float(v) for k, v in qs.items()},
    "zero_count": int((sa == 0).sum()),
    "zero_ratio": float((sa == 0).mean()),
    "negative_count": int((sa < 0).sum()),
    "skew": float(sa.skew()),
}

# store-day totals (for unit plausibility, not for unit determination)
sd = tr.groupby(["dt", "store_id"], observed=True)["sale_amount"].sum()
print("\nstore-day total sale_amount:", sd.describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99]).to_dict())
report["store_day_total"] = {k: float(v) for k, v in sd.describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99]).to_dict().items()}

print("\n--- hours_sale vs sale_amount ---")
hs_tbl = pq.read_table(TRAIN, columns=["hours_sale"])
hs_col = pc.cast(hs_tbl.column("hours_sale"), pa.list_(pa.float64()))
hs_flat = np.asarray(pc.list_flatten(hs_col), dtype="float64")
hs_parent = np.asarray(pc.list_parent_indices(hs_col))
hs_sums_np = np.bincount(hs_parent, weights=hs_flat, minlength=len(hs_tbl))
hs_len_np = np.bincount(hs_parent, minlength=len(hs_tbl))
sa_np = tr["sale_amount"].to_numpy(dtype="float64")
diff = hs_sums_np - sa_np
tol = 1e-6 * np.maximum(1.0, np.abs(sa_np))
print("hours_sale lengths:", dict(pd.Series(hs_len_np).value_counts().head(5)))
print("max abs diff (sum(hours_sale) - sale_amount):", float(np.nanmax(np.abs(diff))))
print("rows where |diff|>1e-6*max(1,|sale_amount|):", int(np.nansum(np.abs(diff) > tol)))
print("sample rows:", list(zip(sa_np[:5], hs_sums_np[:5])))
report["hours_sale"] = {
    "lengths": {str(k): int(v) for k, v in pd.Series(hs_len_np).value_counts().head(5).items()},
    "max_abs_diff_vs_sale_amount": float(np.nanmax(np.abs(diff))),
    "rows_diff_gt_tol": int(np.nansum(np.abs(diff) > tol)),
}

print("\n--- stock fields ---")
ss_tbl = pq.read_table(TRAIN, columns=["hours_stock_status"])
ss_col = pc.cast(ss_tbl.column("hours_stock_status"), pa.list_(pa.int64()))
ss_vals = pd.Series(np.asarray(pc.list_flatten(ss_col)))
print("hours_stock_status value counts:", ss_vals.value_counts().to_dict())
ss_flat_np = np.asarray(pc.list_flatten(ss_col), dtype="float64")
ss_parent = np.asarray(pc.list_parent_indices(ss_col))
ss_cnt_np = np.bincount(ss_parent, weights=ss_flat_np, minlength=len(ss_tbl))
print("sum(hours_stock_status) describe:", pd.Series(ss_cnt_np).describe(percentiles=[0.5, 0.9, 0.99]).to_dict())
print("stock_hour6_22_cnt describe:", tr["stock_hour6_22_cnt"].describe(percentiles=[0.5, 0.9, 0.99]).to_dict())
print("corr(sum_status, stock_hour6_22_cnt):", float(np.corrcoef(ss_cnt_np, tr["stock_hour6_22_cnt"].to_numpy(dtype="float64"))[0, 1]))
report["stock"] = {
    "status_values": {str(k): int(v) for k, v in ss_vals.value_counts().to_dict().items()},
    "sum_status_describe": {k: float(v) for k, v in pd.Series(ss_cnt_np).describe(percentiles=[0.5, 0.9, 0.99]).to_dict().items()},
    "stock_hour6_22_describe": {k: float(v) for k, v in tr["stock_hour6_22_cnt"].describe(percentiles=[0.5, 0.9, 0.99]).to_dict().items()},
    "corr": float(np.corrcoef(ss_cnt_np, tr["stock_hour6_22_cnt"].to_numpy(dtype="float64"))[0, 1]),
}

print("\n--- discount / flags / weather ---")
print("discount describe:", tr["discount"].describe(percentiles=[0.01, 0.5, 0.99]).to_dict())
print("discount value counts (top10):", tr["discount"].value_counts().head(10).to_dict())
for c in ["holiday_flag", "activity_flag"]:
    print(c, tr[c].value_counts(dropna=False).to_dict())
for c in ["precpt", "avg_temperature", "avg_humidity", "avg_wind_level"]:
    print(c, tr[c].describe(percentiles=[0.01, 0.5, 0.99]).to_dict())
report["discount"] = {k: float(v) for k, v in tr["discount"].describe(percentiles=[0.01, 0.5, 0.99]).to_dict().items()}
report["flags"] = {c: {str(k): int(v) for k, v in tr[c].value_counts(dropna=False).to_dict().items()} for c in ["holiday_flag", "activity_flag"]}

print("\n--- entity cardinality ---")
print("cities:", tr["city_id"].nunique(), "stores:", tr["store_id"].nunique(),
      "products:", tr["product_id"].nunique())
print("cat1:", tr["first_category_id"].nunique(), "cat2:", tr["second_category_id"].nunique(),
      "cat3:", tr["third_category_id"].nunique())
print("mgmt groups:", tr["management_group_id"].nunique())
report["cardinality"] = {
    "cities": int(tr["city_id"].nunique()),
    "stores": int(tr["store_id"].nunique()),
    "products": int(tr["product_id"].nunique()),
    "cat1": int(tr["first_category_id"].nunique()),
    "cat2": int(tr["second_category_id"].nunique()),
    "cat3": int(tr["third_category_id"].nunique()),
    "mgmt_groups": int(tr["management_group_id"].nunique()),
}
print("stores per city:", tr.groupby("city_id")["store_id"].nunique().describe().to_dict())
print("series per (store,product):", tr.groupby(["store_id", "product_id"]).size().describe().to_dict())

# ---- eval ----
print("\n--- eval overview ---")
ev = pq.read_table(EVAL).to_pandas()
ev_key_cols = [c for c in ["city_id", "store_id", "product_id", "dt", "sale_amount"] if c in ev.columns]
print("eval shape:", ev.shape)
print(ev[ev_key_cols].head(3).to_string())
ev["dt"] = pd.to_datetime(ev["dt"], errors="coerce")
print("eval date range:", ev["dt"].min(), ev["dt"].max(), "unique dates:", ev["dt"].nunique())
print("eval cities:", ev["city_id"].nunique(), "stores:", ev["store_id"].nunique(), "products:", ev["product_id"].nunique())
print("eval nulls:", ev.isna().sum().to_dict())
print("eval duplicate keys:", int(ev.duplicated(subset=["dt", "store_id", "product_id"], keep=False).sum()))

tr_keys = tr[["dt", "store_id", "product_id"]].drop_duplicates()
ev_keys = ev[["dt", "store_id", "product_id"]].drop_duplicates()
merged = ev_keys.merge(tr_keys, on=["dt", "store_id", "product_id"], how="inner")
print("eval keys:", len(ev_keys), " train keys:", len(tr_keys), " overlap keys:", len(merged))
print("eval dates overlap train dates:", len(set(ev["dt"].dropna()) & set(tr_dt)))
report["eval"] = {
    "rows": int(ev.shape[0]),
    "columns": int(ev.shape[1]),
    "date_min": str(ev["dt"].min()),
    "date_max": str(ev["dt"].max()),
    "unique_dates": int(ev["dt"].nunique()),
    "cities": int(ev["city_id"].nunique()),
    "stores": int(ev["store_id"].nunique()),
    "products": int(ev["product_id"].nunique()),
    "nulls": {k: int(v) for k, v in ev.isna().sum().to_dict().items()},
    "key_overlap_with_train": int(len(merged)),
    "eval_keys": int(len(ev_keys)),
}

# schema detail for data dictionary
schema_detail = []
for f in train_schema:
    schema_detail.append({"column": f.name, "type": str(f.type)})
report["schema"] = schema_detail

with open(os.path.join(OUT_DIR, "freshretailnet50k_summary.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, ensure_ascii=False, indent=2, default=str)

print("\nsummary written to", os.path.join(OUT_DIR, "freshretailnet50k_summary.json"))
