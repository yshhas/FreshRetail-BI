"""P3-A：城市经营对比（仅 train）。"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
DERIVED = ROOT / "data" / "derived"
CLEAN = DERIVED / "clean_train.parquet"
CITY_BASE = DERIVED / "agg_city_summary.parquet"
STORE_BASE = DERIVED / "agg_store_summary.parquet"
MAP_L1 = ROOT / "data" / "analysis" / "p2" / "map_l1.csv"
OUT_TABLES = ROOT / "data" / "analysis" / "p3"
OUT_FIGS = ROOT / "reports" / "figures" / "p3"

SMALL_CITY_THRESHOLD = 10
TOP_STORE_FRAC = 0.10
BOOT_N = 1000
SEED = 42


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW clean AS SELECT * FROM read_parquet('{CLEAN.as_posix()}')")
    return con


def city_core(con) -> pd.DataFrame:
    """城市基础指标：去重门店/门店-日/SKU、总量、零销、缺货。

    注意两个缺货口径：
    - stockout_day_rate：有至少 1 个缺货小时的 SKU-门店-日 / 全部 SKU-门店-日
    - stockout_hour_rate：缺货小时槽位总数 /（16 × SKU-门店-日）
    """
    core = con.execute("""
        SELECT city_id,
               COUNT(DISTINCT store_id) AS store_count,
               COUNT(DISTINCT product_id) AS sku_union,
               COUNT(DISTINCT dt) AS observed_days,
               SUM(sales_index) AS total_index,
               COUNT(*) AS sku_store_days,
               SUM(CASE WHEN sales_index = 0 THEN 1 ELSE 0 END) AS zero_rows,
               SUM(CASE WHEN stockout_day_flag THEN 1 ELSE 0 END) AS stockout_rows,
               SUM(stockout_hours_6_22) AS stockout_hours_total
        FROM clean GROUP BY 1
    """).df()
    store_days = con.execute("""
        SELECT city_id, COUNT(*) AS store_days
        FROM (SELECT DISTINCT city_id, store_id, dt FROM clean)
        GROUP BY 1
    """).df()
    out = core.merge(store_days, on="city_id", how="left")
    out["city_store_day_avg"] = out["total_index"] / out["store_days"]
    out["zero_rate"] = out["zero_rows"] / out["sku_store_days"]
    out["stockout_day_rate"] = out["stockout_rows"] / out["sku_store_days"]
    out["stockout_hour_rate"] = out["stockout_hours_total"] / (16 * out["sku_store_days"])
    return out


def city_sku_store_stats(con) -> pd.DataFrame:
    """每个门店在 90 天内出现过的去重 SKU 数；不是每日在售 SKU 均值。"""
    return con.execute("""
        WITH s AS (
            SELECT city_id, store_id, COUNT(DISTINCT product_id) AS skus
            FROM clean GROUP BY 1, 2
        )
        SELECT city_id,
               AVG(skus) AS sku_per_store_mean,
               MEDIAN(skus) AS sku_per_store_median,
               MIN(skus) AS sku_per_store_min,
               MAX(skus) AS sku_per_store_max
        FROM s GROUP BY 1
    """).df()


def city_category_stats(con) -> pd.DataFrame:
    return con.execute("""
        WITH c AS (
            SELECT city_id, first_category_id, SUM(sales_index) AS idx
            FROM clean GROUP BY 1, 2
        ),
        t AS (
            SELECT city_id, first_category_id, idx,
                   SUM(idx) OVER (PARTITION BY city_id) AS tot
            FROM c
        )
        SELECT city_id,
               SUM(POWER(idx / NULLIF(tot, 0), 2)) AS category_hhi,
               COUNT(*) AS category_count,
               MAX(idx / NULLIF(tot, 0)) AS top_category_share,
               -SUM(CASE WHEN idx > 0 THEN (idx / NULLIF(tot, 0)) * LN(idx / NULLIF(tot, 0)) ELSE 0 END)
                   AS category_entropy
        FROM t GROUP BY 1
    """).df()


def city_category_long(con) -> pd.DataFrame:
    d = con.execute("""
        SELECT city_id, first_category_id AS raw_id, SUM(sales_index) AS sales_index
        FROM clean GROUP BY 1, 2
    """).df()
    d["share"] = d["sales_index"] / d.groupby("city_id")["sales_index"].transform("sum")
    mapping = pd.read_csv(MAP_L1)
    return d.merge(mapping, on="raw_id", how="left")


def _top_share(g: pd.DataFrame, frac: float = TOP_STORE_FRAC) -> float:
    n = max(1, int(np.ceil(len(g) * frac)))
    return float(g.nlargest(n, "total_index")["total_index"].sum() / g["total_index"].sum())


def store_distribution(store: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cid, g in store.groupby("city_id"):
        x = g["per_day_index"]
        rows.append({
            "city_id": int(cid),
            "store_day_mean": float(x.mean()),
            "store_day_p10": float(x.quantile(0.1)),
            "store_day_median": float(x.median()),
            "store_day_p90": float(x.quantile(0.9)),
            "store_day_min": float(x.min()),
            "store_day_max": float(x.max()),
            "store_dispersion_cv": float(x.std(ddof=0) / x.mean()) if x.mean() > 0 else np.nan,
            "top10pct_store_share": _top_share(g),
            "top1_store_share": float(g["total_index"].max() / g["total_index"].sum()),
        })
    return pd.DataFrame(rows)


def store_stockout_distribution(store: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cid, g in store.groupby("city_id"):
        x = g["stockout_sku_day_rate"]
        rows.append({
            "city_id": int(cid),
            "store_stockout_day_mean": float(x.mean()),
            "store_stockout_day_p10": float(x.quantile(0.1)),
            "store_stockout_day_median": float(x.median()),
            "store_stockout_day_p90": float(x.quantile(0.9)),
        })
    return pd.DataFrame(rows)


def finalize_city_table(base: pd.DataFrame, core: pd.DataFrame, sku: pd.DataFrame,
                        cat: pd.DataFrame, dist: pd.DataFrame,
                        stock: pd.DataFrame) -> pd.DataFrame:
    """合并现有城市表与新增指标，并校验与现有表一致。"""
    b = base.copy()
    b = b.rename(columns={"total_index": "city_total_index",
                          "per_store_day_mean": "city_store_day_avg"})
    m = b.merge(core, on="city_id", how="left", suffixes=("", "_new"))
    # 契约校验：复用表与新算值必须一致
    checks = {
        "store_count": np.allclose(m["store_count"], m["store_count_new"]),
        "store_days": np.allclose(m["store_days"], m["store_days"]),
        "total_index": np.allclose(m["city_total_index"], m["total_index"], rtol=1e-9, atol=1e-6),
        "store_day_avg": np.allclose(m["city_store_day_avg"], m["city_store_day_avg_new"], rtol=1e-9, atol=1e-9),
    }
    if not all(checks.values()):
        raise AssertionError(f"城市表与复算不一致：{checks}")
    m = m.drop(columns=["store_count_new", "total_index", "city_store_day_avg_new",
                        "store_days_new"], errors="ignore")
    m = (m.merge(sku, on="city_id", how="left")
           .merge(cat, on="city_id", how="left")
           .merge(dist, on="city_id", how="left")
           .merge(stock, on="city_id", how="left"))
    m["share_pct"] = m["share"] * 100
    m["sku_coverage_rate"] = m["sku_union"] / 865
    m["small_city"] = m["store_count"] < SMALL_CITY_THRESHOLD
    m["rank_total"] = m["city_total_index"].rank(ascending=False, method="min").astype(int)
    m["rank_store_day"] = m["city_store_day_avg"].rank(ascending=False, method="min").astype(int)
    eligible = m.loc[~m["small_city"], "city_store_day_avg"]
    m["rank_store_day_eligible"] = np.nan
    if len(eligible):
        m.loc[~m["small_city"], "rank_store_day_eligible"] = eligible.rank(ascending=False, method="min").astype(int)
    cols = ["city_id", "city_total_index", "share_pct", "store_count", "store_days",
            "observed_days", "city_store_day_avg", "per_store_day_median",
            "stockout_day_rate", "stockout_hour_rate", "stockout_sku_day_rate",
            "store_day_any_stockout_rate", "promo_rate", "sku_union", "sku_coverage_rate",
            "sku_per_store_mean", "sku_per_store_median", "sku_per_store_min", "sku_per_store_max",
            "zero_rate", "category_hhi", "category_entropy", "category_count", "top_category_share",
            "store_day_mean", "store_day_p10", "store_day_median", "store_day_p90",
            "store_day_min", "store_day_max", "store_dispersion_cv", "store_cv",
            "top10pct_store_share", "top1_store_share", "store_stockout_day_mean",
            "store_stockout_day_p10", "store_stockout_day_median", "store_stockout_day_p90",
            "small_city", "rank_total", "rank_store_day", "rank_store_day_eligible"]
    return m[cols].sort_values("city_store_day_avg", ascending=False).reset_index(drop=True)


def _spearman_ci(x, y, n_boot: int = BOOT_N, seed: int = SEED):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 4:
        return np.nan, np.nan, np.nan
    rho = float(pd.Series(x).corr(pd.Series(y), method="spearman"))
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(idx)) < 3:
            continue
        r = pd.Series(x[idx]).corr(pd.Series(y[idx]), method="spearman")
        if not np.isnan(r):
            vals.append(r)
    if not vals:
        return rho, np.nan, np.nan
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return rho, float(lo), float(hi)


def correlation_table(city: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("total_vs_store_count", "city_total_index", "store_count"),
        ("store_day_vs_store_count", "city_store_day_avg", "store_count"),
        ("store_day_vs_sku_union", "city_store_day_avg", "sku_union"),
        ("store_day_vs_sku_per_store", "city_store_day_avg", "sku_per_store_mean"),
        ("store_day_vs_stockout_day", "city_store_day_avg", "stockout_day_rate"),
        ("store_day_vs_stockout_hour", "city_store_day_avg", "stockout_hour_rate"),
        ("zero_vs_stockout_day", "zero_rate", "stockout_day_rate"),
        ("zero_vs_stockout_hour", "zero_rate", "stockout_hour_rate"),
        ("store_day_vs_store_cv", "city_store_day_avg", "store_dispersion_cv"),
        ("total_vs_sku_union", "city_total_index", "sku_union"),
    ]
    rows = []
    rest = city[city["city_id"] != 0]
    for name, a, b in pairs:
        r, lo, hi = _spearman_ci(city[a], city[b])
        r0, lo0, hi0 = _spearman_ci(rest[a], rest[b])
        rows.append({
            "relation": name, "x": a, "y": b,
            "n_all": int(city[[a, b]].dropna().shape[0]),
            "spearman_all": r, "ci_low_all": lo, "ci_high_all": hi,
            "n_excl_city0": int(rest[[a, b]].dropna().shape[0]),
            "spearman_excl_city0": r0, "ci_low_excl_city0": lo0, "ci_high_excl_city0": hi0,
        })
    return pd.DataFrame(rows)


def city0_sensitivity(city: pd.DataFrame, corr: pd.DataFrame) -> pd.DataFrame:
    c0 = city[city["city_id"] == 0].iloc[0]
    rest = city[city["city_id"] != 0]
    rows = [
        {"metric": "store_share", "city0": c0["store_count"] / city["store_count"].sum(),
         "rest_median": np.nan},
        {"metric": "total_share", "city0": c0["share_pct"] / 100,
         "rest_median": np.nan},
        {"metric": "store_day_avg", "city0": c0["city_store_day_avg"],
         "rest_median": float(rest["city_store_day_avg"].median())},
        {"metric": "sku_per_store_mean", "city0": c0["sku_per_store_mean"],
         "rest_median": float(rest["sku_per_store_mean"].median())},
        {"metric": "zero_rate", "city0": c0["zero_rate"],
         "rest_median": float(rest["zero_rate"].median())},
        {"metric": "stockout_day_rate", "city0": c0["stockout_day_rate"],
         "rest_median": float(rest["stockout_day_rate"].median())},
        {"metric": "stockout_hour_rate", "city0": c0["stockout_hour_rate"],
         "rest_median": float(rest["stockout_hour_rate"].median())},
    ]
    out = pd.DataFrame(rows)
    out["note"] = out["metric"].map({
        "store_share": "city0 门店数 / 全部门店数",
        "total_share": "city0 总指数 / 样本总指数",
        "store_day_avg": "city0 vs 其他城市中位",
        "sku_per_store_mean": "city0 vs 其他城市中位",
        "zero_rate": "city0 vs 其他城市中位",
        "stockout_day_rate": "city0 vs 其他城市中位",
        "stockout_hour_rate": "city0 vs 其他城市中位",
    })
    return out


# ---------------- 图表 ----------------

def _save(fig, name: str) -> None:
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_total_vs_stores(city: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    sc = ax.scatter(city["store_count"], city["city_total_index"],
                    s=20 + city["sku_union"] * 1.2,
                    c=city["city_store_day_avg"], cmap="viridis", alpha=0.85,
                    edgecolors="white", linewidths=0.4)
    for _, r in city.iterrows():
        ax.annotate(str(int(r["city_id"])), (r["store_count"], r["city_total_index"]),
                    textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xscale("log")
    ax.set_title("城市累计销量指数与门店数（气泡=SKU 并集数，颜色=单店日均）")
    ax.set_xlabel("城市门店数（对数）")
    ax.set_ylabel("城市累计归一化销量指数")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("城市单店日均")
    ax.grid(alpha=0.25)
    _save(fig, "f1_city_total_vs_stores.png")


def fig_store_day_rank(city: pd.DataFrame) -> None:
    d = city.sort_values("city_store_day_avg", ascending=True)
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    colors = ["#bdbdbd" if s else "#08519c" for s in d["small_city"]]
    bars = ax.barh([f"C{int(c):02d}" for c in d["city_id"]], d["city_store_day_avg"], color=colors)
    for b, (_, r) in zip(bars, d.iterrows()):
        ax.text(r["city_store_day_avg"], b.get_y() + b.get_height() / 2,
                f"  n={int(r['store_count'])}", va="center", fontsize=8)
    ax.set_title("城市单店日均销量指数（灰色=门店数<10，仅展示不参与强排名）")
    ax.set_xlabel("城市单店日均归一化销量指数")
    ax.set_ylabel("城市（匿名编码）")
    ax.set_xlim(0, d["city_store_day_avg"].max() * 1.15)
    ax.grid(axis="x", alpha=0.25)
    _save(fig, "f2_city_store_day_rank.png")


def fig_city_store_distribution(city: pd.DataFrame, store: pd.DataFrame) -> None:
    order = city.sort_values("per_store_day_median")["city_id"].tolist()
    data = [store.loc[store["city_id"] == c, "per_day_index"].values for c in order]
    fig, ax = plt.subplots(figsize=(12, 5))
    bp = ax.boxplot(data, labels=[f"C{int(c):02d}" for c in order], showfliers=False, patch_artist=True)
    for patch, c in zip(bp["boxes"], order):
        patch.set_facecolor("#bdbdbd" if c in set(city.loc[city["small_city"], "city_id"]) else "#9ecae1")
    ax.set_title("城市内门店单店日均分布（箱线，去除离群点）")
    ax.set_xlabel("城市（按中位数排序）")
    ax.set_ylabel("门店单店日均归一化销量指数")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f3_city_store_distribution.png")


def fig_sku_vs_store_day(city: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    sc = ax.scatter(city["sku_per_store_mean"], city["city_store_day_avg"],
                    s=20 + city["store_count"] * 2.0,
                    c=city["zero_rate"] * 100, cmap="YlOrRd", alpha=0.85,
                    edgecolors="white", linewidths=0.4)
    for _, r in city.iterrows():
        ax.annotate(str(int(r["city_id"])), (r["sku_per_store_mean"], r["city_store_day_avg"]),
                    textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_title("城市单店90天 SKU 覆盖均值与单店日均（气泡=门店数，颜色=零销率%）")
    ax.set_xlabel("单店90天 SKU 覆盖均值（门店算术平均）")
    ax.set_ylabel("城市单店日均归一化销量指数")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("零销率（%）")
    ax.grid(alpha=0.25)
    _save(fig, "f4_city_sku_vs_store_day.png")


def fig_city_stockout(city: pd.DataFrame, store: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    d = city.sort_values("stockout_day_rate", ascending=True)
    y = np.arange(len(d))
    axes[0].barh(y - 0.2, d["stockout_day_rate"] * 100, height=0.38,
                 color="#fd8d3c", label="SKU-日缺货率")
    axes[0].barh(y + 0.2, d["stockout_hour_rate"] * 100, height=0.38,
                 color="#6baed6", label="小时槽位缺货率")
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([f"C{int(c):02d}" for c in d["city_id"]], fontsize=8)
    axes[0].set_title("城市整体缺货率：SKU-日口径 vs 小时槽位口径")
    axes[0].set_xlabel("缺货率（%）")
    axes[0].set_ylabel("城市")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].grid(axis="x", alpha=0.25)

    order = city.sort_values("store_stockout_day_median")["city_id"].tolist()
    data = [store.loc[store["city_id"] == c, "stockout_sku_day_rate"].values * 100 for c in order]
    bp = axes[1].boxplot(data, labels=[f"C{int(c):02d}" for c in order], showfliers=False, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#fdae6b")
    axes[1].set_title("城市内门店 SKU-日缺货率分布（门店等权）")
    axes[1].set_xlabel("城市（按中位数排序）")
    axes[1].set_ylabel("门店 SKU-日缺货率（%）")
    axes[1].tick_params(axis="x", rotation=45, labelsize=7)
    axes[1].grid(axis="y", alpha=0.25)
    _save(fig, "f5_city_stockout.png")


def fig_category_structure(city: pd.DataFrame, cat_long: pd.DataFrame) -> None:
    top_cats = (cat_long.groupby("display_code")["sales_index"].sum()
                .nlargest(8).index.tolist())
    d = cat_long.copy()
    d["cat"] = np.where(d["display_code"].isin(top_cats), d["display_code"], "其他")
    p = d.pivot_table(index="city_id", columns="cat", values="share", aggfunc="sum")
    order = city.sort_values("city_total_index", ascending=False)["city_id"].tolist()
    cols = top_cats + ["其他"]
    p = p.reindex(index=order, columns=cols).fillna(0)
    fig, ax = plt.subplots(figsize=(12, 5))
    bottom = np.zeros(len(p))
    cmap = plt.get_cmap("tab20")
    for i, c in enumerate(cols):
        ax.bar([f"C{int(x):02d}" for x in p.index], p[c] * 100, bottom=bottom,
               label=c, color=cmap(i % 20))
        bottom += p[c].values * 100
    ax.set_title("城市一级类别销量结构（前 8 类 + 其他）")
    ax.set_xlabel("城市（按总指数排序）")
    ax.set_ylabel("销量份额（%）")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(ncol=3, fontsize=7, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f6_city_category_structure.png")


def run() -> dict:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    con = _con()
    base = pd.read_parquet(CITY_BASE)
    store = pd.read_parquet(STORE_BASE)

    core = city_core(con)
    sku = city_sku_store_stats(con)
    cat = city_category_stats(con)
    cat_long = city_category_long(con)
    dist = store_distribution(store)
    stock = store_stockout_distribution(store)
    city = finalize_city_table(base, core, sku, cat, dist, stock)
    corr = correlation_table(city)
    sens = city0_sensitivity(city, corr)

    city.to_csv(OUT_TABLES / "a1_city_metrics.csv", index=False, encoding="utf-8-sig")
    corr.to_csv(OUT_TABLES / "a2_city_correlations.csv", index=False, encoding="utf-8-sig")
    sens.to_csv(OUT_TABLES / "a3_city0_sensitivity.csv", index=False, encoding="utf-8-sig")
    cat_long.to_csv(OUT_TABLES / "a4_city_category_long.csv", index=False, encoding="utf-8-sig")

    summary = {
        "city_count": int(len(city)),
        "bootstrap": {"n_boot": BOOT_N, "seed": SEED, "unit": "city",
                      "n_cities": int(len(city)), "method": "percentile 2.5/97.5"},
        "sku_definition": "每个门店在 90 天内出现过的去重 SKU 数；城市单店 SKU 均值为门店算术平均",
        "small_cities": city.loc[city["small_city"], ["city_id", "store_count"]].to_dict("records"),
        "total_index": float(city["city_total_index"].sum()),
        "correlations": corr.to_dict("records"),
        "city0_sensitivity": sens.to_dict("records"),
        "top3_store_day": city.nsmallest(3, "rank_store_day")[
            ["city_id", "city_store_day_avg", "store_count"]
        ].to_dict("records"),
        "top3_store_day_eligible": city.dropna(subset=["rank_store_day_eligible"]).nsmallest(
            3, "rank_store_day_eligible"
        )[["city_id", "city_store_day_avg", "store_count"]].to_dict("records"),
    }
    with open(OUT_TABLES / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    fig_total_vs_stores(city)
    fig_store_day_rank(city)
    fig_city_store_distribution(city, store)
    fig_sku_vs_store_day(city)
    fig_city_stockout(city, store)
    fig_category_structure(city, cat_long)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
