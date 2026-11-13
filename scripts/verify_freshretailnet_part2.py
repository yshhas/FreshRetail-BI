import os
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

cols = [
    "city_id", "store_id", "management_group_id",
    "first_category_id", "second_category_id", "third_category_id",
    "product_id", "dt", "sale_amount", "stock_hour6_22_cnt",
    "discount", "holiday_flag", "activity_flag",
    "precpt", "avg_temperature", "avg_humidity", "avg_wind_level",
]
df = pq.read_table(TRAIN, columns=cols).to_pandas()
df["dt"] = pd.to_datetime(df["dt"])

print("=== 1. zero-sale vs stockout ===")
zero = df[df["sale_amount"] == 0]
print("zero rows:", len(zero))
print("zero rows with stock_hour6_22_cnt>0:", int((zero["stock_hour6_22_cnt"] > 0).sum()),
      f"({(zero['stock_hour6_22_cnt'] > 0).mean():.2%})")
print("all rows with stock>0:", int((df["stock_hour6_22_cnt"] > 0).sum()),
      f"({(df['stock_hour6_22_cnt'] > 0).mean():.2%})")
print("zero-sale ratio when stock=0:", float((df.loc[df.stock_hour6_22_cnt == 0, "sale_amount"] == 0).mean()))
print("zero-sale ratio when stock>0:", float((df.loc[df.stock_hour6_22_cnt > 0, "sale_amount"] == 0).mean()))

print("\n=== 2. series-level all-zero ===")
g = df.groupby(["store_id", "product_id"], observed=True)["sale_amount"].agg(["sum", "count"])
print("series:", len(g), "all-zero series:", int((g["sum"] == 0).sum()),
      f"({(g['sum'] == 0).mean():.2%})")
print("series length distribution:", g["count"].value_counts().to_dict())

print("\n=== 3. discount ===")
print("count >1:", int((df["discount"] > 1).sum()), f"({(df['discount'] > 1).mean():.4%})")
print("count ==0:", int((df["discount"] == 0).sum()))
print("count ==1:", int((df["discount"] == 1).sum()))
print("count in (0,1):", int(((df["discount"] > 0) & (df["discount"] < 1)).sum()))
print("top values:", df["discount"].value_counts().head(8).to_dict())

print("\n=== 4. weather consistency per city-day ===")
for c in ["precpt", "avg_temperature", "avg_humidity", "avg_wind_level"]:
    n = df.groupby(["city_id", "dt"], observed=True)[c].nunique()
    print(f"{c}: city-day groups={len(n)}, max distinct={int(n.max())}, groups with >1={int((n > 1).sum())}")

print("\n=== 5. hierarchy consistency ===")
store_city = df.groupby("store_id", observed=True)["city_id"].nunique()
print("stores mapped to >1 city:", int((store_city > 1).sum()))
prod_cat3 = df.groupby("product_id", observed=True)["third_category_id"].nunique()
print("products mapped to >1 third category:", int((prod_cat3 > 1).sum()))
cat3_cat2 = df.groupby("third_category_id", observed=True)["second_category_id"].nunique()
print("third categories mapped to >1 second category:", int((cat3_cat2 > 1).sum()))
cat2_cat1 = df.groupby("second_category_id", observed=True)["first_category_id"].nunique()
print("second categories mapped to >1 first category:", int((cat2_cat1 > 1).sum()))

print("\n=== 6. store/product coverage ===")
print("stores per city:\n", df.groupby("city_id", observed=True)["store_id"].nunique().to_string())
print("products per store describe:", df.groupby("store_id", observed=True)["product_id"].nunique().describe().to_dict())
print("stores per product describe:", df.groupby("product_id", observed=True)["store_id"].nunique().describe().to_dict())

print("\n=== 7. hours_sale sanity ===")
hs = pq.read_table(TRAIN, columns=["hours_sale"])
hs_col = pc.cast(hs.column("hours_sale"), pa.list_(pa.float64()))
flat = np.asarray(pc.list_flatten(hs_col))
print("n values:", flat.size, "negative:", int((flat < 0).sum()), "min:", float(flat.min()), "max:", float(flat.max()))
print("value counts top:", pd.Series(flat).value_counts().head(8).to_dict())

print("\n=== 8. stock status length ===")
ss = pq.read_table(TRAIN, columns=["hours_stock_status"])
ss_col = pc.cast(ss.column("hours_stock_status"), pa.list_(pa.int64()))
parent = np.asarray(pc.list_parent_indices(ss_col))
lens = np.bincount(parent, minlength=len(ss))
print("length distribution:", pd.Series(lens).value_counts().to_dict())
print("distinct values:", pd.Series(np.asarray(pc.list_flatten(ss_col))).value_counts().to_dict())

print("\n=== 9. daily aggregate trend (normalized units) ===")
daily = df.groupby("dt", observed=True)["sale_amount"].sum()
print("first 5:\n", daily.head().to_string())
print("last 5:\n", daily.tail().to_string())
print("daily total describe:", daily.describe().to_dict())

print("\n=== 10. eval completeness ===")
ev = pq.read_table(EVAL, columns=["city_id", "store_id", "product_id", "dt", "sale_amount"]).to_pandas()
ev["dt"] = pd.to_datetime(ev["dt"])
print("eval rows:", len(ev), "series:", ev.groupby(["store_id", "product_id"], observed=True).ngroups)
print("eval days per series:", ev.groupby(["store_id", "product_id"], observed=True).size().value_counts().to_dict())
print("eval zero-sale ratio:", float((ev["sale_amount"] == 0).mean()))
print("eval daily total:\n", ev.groupby("dt", observed=True)["sale_amount"].sum().to_string())
