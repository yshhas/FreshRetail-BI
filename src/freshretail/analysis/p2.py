"""P2：模块四 商品经营分析（仅 train 90 天）。"""

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
OUT_TABLES = ROOT / "data" / "analysis" / "p2"
OUT_FIGS = ROOT / "reports" / "figures" / "p2"

THRESHOLDS = [1, 2, 3, 5, 10, 20, 50, 100]
DEFAULT_MIN_COVERAGE = 5
ANOMALY_Z = 3.5
FLAG_Q = 0.95
BAND_ORDER = ["无促销(1.0)", "9-10折", "8-9折", "7-8折", "<=7折", "缺失(0)", "异常(>1)"]


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW clean AS SELECT * FROM read_parquet('{str(CLEAN).replace(chr(92), '/')}')")
    return con


def load_base(con) -> tuple[pd.DataFrame, dict]:
    p = pd.read_parquet(DERIVED / "agg_product_summary.parquet")

    extra = con.execute("""
        SELECT product_id,
               COUNT(DISTINCT store_id) AS store_count,
               COUNT(*) AS series_days,
               SUM(CASE WHEN sales_index > 0 THEN 1 ELSE 0 END) AS active_days,
               SUM(CASE WHEN promo_flag THEN 1 ELSE 0 END) AS promo_rows,
               AVG(CASE WHEN discount_valid THEN discount END) AS avg_valid_discount,
               AVG(CASE WHEN discount_missing THEN 1.0 ELSE 0 END) AS discount_missing_rate,
               MIN(discount) AS min_discount,
               MAX(discount) AS max_discount
        FROM clean GROUP BY 1
    """).df()
    extra = extra.drop(columns=["store_count", "series_days"])

    hhi = con.execute("""
        WITH s AS (
            SELECT product_id, store_id, SUM(sales_index) AS idx FROM clean GROUP BY 1, 2
        ),
        t AS (
            SELECT product_id, store_id, idx,
                   SUM(idx) OVER (PARTITION BY product_id) AS tot
            FROM s
        )
        SELECT product_id,
               SUM(POWER(idx / NULLIF(tot, 0), 2)) AS hhi
        FROM t GROUP BY 1
    """).df()

    anom = con.execute(f"""
        WITH b AS (
            SELECT product_id, store_id, sales_index,
                   median(sales_index) OVER (PARTITION BY product_id, store_id) AS med
            FROM clean
        ),
        c AS (
            SELECT product_id, store_id, sales_index, med,
                   median(abs(sales_index - med)) OVER (PARTITION BY product_id, store_id) AS mad
            FROM b
        )
        SELECT product_id,
               SUM(CASE WHEN mad > 0 AND abs(sales_index - med) / (1.4826 * mad) > {ANOMALY_Z}
                        THEN 1 ELSE 0 END) AS anomaly_days,
               COUNT(*) AS n_days
        FROM c GROUP BY 1
    """).df()

    bands = con.execute("""
        SELECT CASE
                   WHEN discount = 0 THEN '缺失(0)'
                   WHEN discount > 1 THEN '异常(>1)'
                   WHEN discount = 1 THEN '无促销(1.0)'
                   WHEN discount >= 0.9 THEN '9-10折'
                   WHEN discount >= 0.8 THEN '8-9折'
                   WHEN discount >= 0.7 THEN '7-8折'
                   ELSE '<=7折'
               END AS band,
               COUNT(*) AS rows,
               AVG(sales_index) AS avg_index,
               MEDIAN(sales_index) AS median_index
        FROM clean GROUP BY 1
    """).df()

    df = p.merge(extra, on="product_id", how="left").merge(hhi, on="product_id", how="left").merge(anom, on="product_id", how="left")
    prod_cat = con.execute("""
        SELECT product_id,
               MAX(first_category_id) AS first_category_id,
               MAX(second_category_id) AS second_category_id,
               MAX(third_category_id) AS third_category_id
        FROM clean GROUP BY 1
    """).df()
    df = df.merge(prod_cat, on="product_id", how="left")
    df["zero_rate"] = 1 - df["active_day_rate"]
    # 动态使用实际观察天数（series_days），不写死 90，兼容数据窗口变化
    df["per_store_day"] = df["total_index"] / df["series_days"]
    df["anomaly_rate"] = df["anomaly_days"] / df["n_days"]
    df["promo_rate"] = df["promo_rows"] / df["series_days"]
    df["effective_stores"] = 1 / df["hhi"]

    mapping = {
        "product": _mapping(df["product_id"], "P", 4),
        "l1": _mapping(pd.Series(sorted(_category_ids(con, "first_category_id"))), "C", 2),
        "l2": _mapping(pd.Series(sorted(_category_ids(con, "second_category_id"))), "S", 3),
        "l3": _mapping(pd.Series(sorted(_category_ids(con, "third_category_id"))), "T", 3),
    }
    return df, {"bands": bands, "mapping": mapping}


def _category_ids(con, col: str) -> list[int]:
    return [int(x[0]) for x in con.execute(f"SELECT DISTINCT {col} FROM clean ORDER BY 1").fetchall()]


def _mapping(ids: pd.Series, prefix: str, width: int) -> pd.DataFrame:
    uniq = pd.Series(sorted(pd.unique(ids.dropna().astype(int))))
    return pd.DataFrame({"raw_id": uniq.astype(int),
                         "display_code": [f"{prefix}{i + 1:0{width}d}" for i in range(len(uniq))]})


def add_sku_metrics(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["total_share_pct"] = d["total_index"] / d["total_index"].sum() * 100
    d = d.sort_values("total_index", ascending=False).reset_index(drop=True)
    d["cum_share_pct"] = d["total_share_pct"].cumsum()
    d["rank_scale"] = np.arange(1, len(d) + 1)
    d["rank_eff_all"] = d["per_series_day"].rank(ascending=False, method="min").astype(int)
    d["rank_diff"] = d["rank_scale"] - d["rank_eff_all"]
    return d


def pareto(d: pd.DataFrame) -> dict:
    return {
        "sku_count": int(len(d)),
        "top10pct_share_pct": float(d.head(max(1, int(len(d) * 0.1)))["total_share_pct"].sum()),
        "top20pct_share_pct": float(d.head(max(1, int(len(d) * 0.2)))["total_share_pct"].sum()),
        "skus_to_80pct": int((d["cum_share_pct"] < 80).sum() + 1),
    }


def coverage_sensitivity(d: pd.DataFrame, thresholds: list[int]) -> pd.DataFrame:
    base_top = set(d.nlargest(10, "per_series_day")["product_id"])
    rows = []
    for t in thresholds:
        sub = d[d["store_count"] >= t]
        rows.append({
            "min_store_count": t,
            "sku_count": int(len(sub)),
            "median_store_count": float(sub["store_count"].median()),
            "spearman_scale_vs_eff": float(
                sub["total_index"].corr(sub["per_series_day"], method="spearman")
            ),
            "top10_eff_overlap_with_baseline": int(
                len(set(sub.nlargest(10, "per_series_day")["product_id"]) & base_top)
            ),
            "top10_eff_mean_store_count": float(
                sub.nlargest(10, "per_series_day")["store_count"].mean()
            ),
            "top10_scale_mean_store_count": float(
                sub.nlargest(10, "total_index")["store_count"].mean()
            ),
        })
    return pd.DataFrame(rows)


def stability_tiers(d: pd.DataFrame) -> pd.DataFrame:
    med_zero = d["zero_rate"].median()
    med_cv = d["cv_series_median"].median()
    d = d.copy()
    d["stability_tier"] = np.select(
        [(d["zero_rate"] <= med_zero) & (d["cv_series_median"] <= med_cv),
         (d["zero_rate"] > med_zero) & (d["cv_series_median"] <= med_cv),
         (d["zero_rate"] <= med_zero) & (d["cv_series_median"] > med_cv)],
        ["稳定（低零销/低波动）", "高频零销/低波动", "低零销/高波动"],
        default="不稳定（高零销/高波动）",
    )
    return d


def head_tail(d: pd.DataFrame) -> pd.DataFrame:
    n_head = max(1, int(len(d) * 0.2))
    n_tail = max(1, int(len(d) * 0.5))
    head = d.head(n_head)
    tail = d.tail(n_tail)
    cols = ["store_count", "per_series_day", "zero_rate", "cv_series_median", "promo_rate"]
    out = []
    for name, part in [("头部 Top20%", head), ("长尾 Bottom50%", tail)]:
        row = {"group": name, "sku_count": len(part)}
        row.update({f"{c}_median": float(part[c].median()) for c in cols})
        out.append(row)
    return pd.DataFrame(out)


def flag_anomalies(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    q_cv = d["cv_series_median"].quantile(FLAG_Q)
    q_zero = d["zero_rate"].quantile(FLAG_Q)
    # 门店集中度只在多店 SKU 中评估，避免单店 SKU 天然 HHI=1 造成误判
    q_hhi = d.loc[d["store_count"] >= 5, "hhi"].quantile(FLAG_Q)
    d["flag_high_cv"] = d["cv_series_median"] > q_cv
    d["flag_high_zero"] = d["zero_rate"] > q_zero
    d["flag_many_anomaly_days"] = d["anomaly_rate"] > 0.05
    d["flag_store_concentration"] = (d["store_count"] >= 5) & (d["hhi"] > q_hhi)
    d["risk_flag_count"] = d[["flag_high_cv", "flag_high_zero",
                              "flag_many_anomaly_days", "flag_store_concentration"]].sum(axis=1)
    d.attrs["thresholds"] = {"cv_p95": float(q_cv), "zero_p95": float(q_zero), "hhi_p95": float(q_hhi)}
    return d


def category_table(con, col: str, sku: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """类别指标。

    两个效率口径必须区分：
    - category_sku_store_day_avg：累计指数 / SKU-门店-日记录数（原指标，改名）
    - category_store_day_avg：累计指数 / 去重门店-日数（新增，真正的单店日均）
    """
    raw = con.execute(f"""
        SELECT {col} AS raw_id,
               COUNT(DISTINCT product_id) AS sku_count,
               COUNT(DISTINCT store_id) AS store_count,
               COUNT(*) AS sku_store_days,
               SUM(sales_index) AS total_index,
               SUM(CASE WHEN sales_index > 0 THEN 1 ELSE 0 END) AS active_days,
               SUM(CASE WHEN promo_flag THEN 1 ELSE 0 END) AS promo_rows
        FROM clean GROUP BY 1
    """).df()
    # 动态计算去重门店-日数，不写死 90 天，避免数据窗口变化时失真
    store_days = con.execute(f"""
        SELECT {col} AS raw_id, COUNT(*) AS store_days
        FROM (SELECT DISTINCT {col}, store_id, dt FROM clean)
        GROUP BY 1
    """).df()
    cv = sku.groupby(col)["cv_series_median"].median().rename("sku_cv_median").reset_index()
    cv = cv.rename(columns={col: "raw_id"})
    raw = (raw.merge(store_days, on="raw_id", how="left")
              .merge(cv, on="raw_id", how="left")
              .merge(mapping, on="raw_id", how="left"))
    raw["share_pct"] = raw["total_index"] / raw["total_index"].sum() * 100
    raw["category_sku_store_day_avg"] = raw["total_index"] / raw["sku_store_days"]
    raw["category_store_day_avg"] = raw["total_index"] / raw["store_days"]
    raw["observed_days_avg"] = raw["store_days"] / raw["store_count"]
    raw["sku_store_day_zero_rate"] = 1 - raw["active_days"] / raw["sku_store_days"]
    raw["sku_store_day_promo_rate"] = raw["promo_rows"] / raw["sku_store_days"]
    raw["rank_total_index"] = raw["total_index"].rank(ascending=False, method="min").astype(int)
    raw["rank_store_day_avg"] = raw["category_store_day_avg"].rank(ascending=False, method="min").astype(int)
    raw["rank_sku_store_day_avg"] = raw["category_sku_store_day_avg"].rank(ascending=False, method="min").astype(int)
    cols = ["raw_id", "display_code", "sku_count", "store_count", "store_days",
            "observed_days_avg", "sku_store_days", "total_index", "share_pct",
            "active_days", "promo_rows", "category_sku_store_day_avg",
            "category_store_day_avg", "sku_store_day_zero_rate",
            "sku_store_day_promo_rate", "sku_cv_median",
            "rank_total_index", "rank_store_day_avg", "rank_sku_store_day_avg"]
    return raw[cols].sort_values("total_index", ascending=False).reset_index(drop=True)


# ---------------- 图表 ----------------

def _save(fig, name: str) -> None:
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_top20(d: pd.DataFrame) -> None:
    t = d.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.barh(t["display_code"], t["total_index"], color="#08519c")
    for y, (_, r) in enumerate(t.iterrows()):
        ax.text(r["total_index"], y, f"  {r['store_count']:.0f}店", va="center", fontsize=8)
    ax.set_title("SKU 累计销量指数 Top 20（标注覆盖门店数）")
    ax.set_xlabel("累计归一化销量指数（90 天）")
    ax.set_ylabel("SKU（展示编码）")
    ax.grid(axis="x", alpha=0.25)
    _save(fig, "f1_sku_total_top20.png")


def fig_top20_eff(d: pd.DataFrame, min_cov: int) -> None:
    sub = d[d["store_count"] >= min_cov]
    t = sub.nlargest(20, "per_series_day").iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.barh(t["display_code"], t["per_series_day"], color="#238b45")
    for y, (_, r) in enumerate(t.iterrows()):
        ax.text(r["per_series_day"], y, f"  {r['store_count']:.0f}店", va="center", fontsize=8)
    ax.set_title(f"SKU 单店日均销量指数 Top 20（覆盖门店数 ≥ {min_cov}）")
    ax.set_xlabel("单店日均归一化销量指数")
    ax.set_ylabel("SKU（展示编码）")
    ax.grid(axis="x", alpha=0.25)
    _save(fig, "f2_sku_efficiency_top20.png")


def fig_rank_compare(d: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 6.2))
    sc = ax.scatter(d["rank_scale"], d["rank_eff_all"], c=d["store_count"],
                    s=10, cmap="viridis", alpha=0.7, edgecolors="none")
    ax.plot([1, len(d)], [1, len(d)], color="#d62728", ls="--", lw=1)
    ax.set_xlabel("规模排名（1=累计销量指数最高）")
    ax.set_ylabel("效率排名（1=单店日均最高）")
    ax.set_title("SKU 规模排名与效率排名对比")
    ticks = [1, 100, 200, 400, 600, 800]
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xlim(len(d) + 5, -5)
    ax.set_ylim(len(d) + 5, -5)
    ax.grid(alpha=0.25)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("覆盖门店数")
    _save(fig, "f3_rank_compare.png")


def fig_coverage(d: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    bins = [0, 1, 2, 5, 10, 20, 50, 100, 200, 400, 800]
    ax.hist(d["store_count"], bins=bins, color="#6baed6", edgecolor="white")
    ax.set_xscale("log")
    ax.set_title("865 个 SKU 的覆盖门店数分布（对数横轴）")
    ax.set_xlabel("覆盖门店数（家）")
    ax.set_ylabel("SKU 数")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f4_coverage_distribution.png")


def fig_pareto(d: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(np.arange(1, len(d) + 1), d["cum_share_pct"], color="#08519c", lw=2)
    ax.axhline(80, color="#d62728", ls="--", lw=1)
    k = int((d["cum_share_pct"] < 80).sum() + 1)
    ax.axvline(k, color="#d62728", ls="--", lw=1)
    ax.annotate(f"前 {k} 个 SKU 贡献 80%", (k, 80), xytext=(k + 30, 70),
                arrowprops={"arrowstyle": "->", "color": "#d62728"}, fontsize=9, color="#d62728")
    ax.set_title("SKU 销量贡献 Pareto 曲线")
    ax.set_xlabel("按累计销量指数排序的 SKU 数")
    ax.set_ylabel("累计贡献（%）")
    ax.grid(alpha=0.25)
    _save(fig, "f5_pareto.png")


def fig_long_tail(d: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.scatter(np.arange(1, len(d) + 1), d["total_index"], s=8, alpha=0.5, color="#4292c6")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("SKU 销量长尾分布（双对数）")
    ax.set_xlabel("SKU 排名（对数）")
    ax.set_ylabel("累计销量指数（对数）")
    ax.grid(alpha=0.25)
    _save(fig, "f6_long_tail.png")


def fig_zero_cv(d: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    axes[0].hist(d["zero_rate"] * 100, bins=40, color="#fd8d3c", edgecolor="white")
    for q, c in [(0.5, "#d62728"), (0.9, "#6a51a3")]:
        v = d["zero_rate"].quantile(q) * 100
        axes[0].axvline(v, color=c, ls="--", lw=1)
        axes[0].text(v, axes[0].get_ylim()[1] * 0.9, f"P{int(q*100)}\n{v:.1f}%", fontsize=8, color=c)
    axes[0].set_title("SKU 零销量率分布")
    axes[0].set_xlabel("零销量率（%）")
    axes[0].set_ylabel("SKU 数")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].hist(d["cv_series_median"], bins=40, color="#9ecae1", edgecolor="white")
    for q, c in [(0.5, "#d62728"), (0.9, "#6a51a3")]:
        v = d["cv_series_median"].quantile(q)
        axes[1].axvline(v, color=c, ls="--", lw=1)
        axes[1].text(v, axes[1].get_ylim()[1] * 0.9, f"P{int(q*100)}\n{v:.2f}", fontsize=8, color=c)
    axes[1].set_title("SKU 日销量变异系数分布")
    axes[1].set_xlabel("CV（序列中位数）")
    axes[1].set_ylabel("SKU 数")
    axes[1].grid(axis="y", alpha=0.25)
    _save(fig, "f7_zero_and_cv.png")


def fig_category(l1: pd.DataFrame, l2: pd.DataFrame, l3: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6))
    for ax, df, title, topn in [
        (axes[0], l1, "一级类别销量份额", 12),
        (axes[1], l2.head(15), "二级类别累计销量指数 Top 15", 15),
        (axes[2], l3.head(15), "三级类别累计销量指数 Top 15", 15),
    ]:
        if title == "一级类别销量份额":
            ax.bar(df["display_code"], df["share_pct"], color="#6baed6")
            ax.set_ylabel("份额（%）")
        else:
            ax.barh(df["display_code"][::-1], df["total_index"][::-1], color="#4292c6")
            ax.set_xlabel("累计销量指数")
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=60, labelsize=7)
        ax.grid(alpha=0.25)
    _save(fig, "f8_category_l1_l2_l3.png")


def fig_category_scale_cov(l3: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    sc = ax.scatter(l3["store_count"], l3["total_index"], s=12 + l3["sku_count"] * 0.8,
                    c=l3["category_store_day_avg"], cmap="viridis", alpha=0.8, edgecolors="none")
    ax.set_xscale("log")
    ax.set_title("三级类别：覆盖门店数、累计销量与类别单店日均")
    ax.set_xlabel("覆盖门店数（对数）")
    ax.set_ylabel("累计销量指数")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("类别单店日均销量指数")
    ax.grid(alpha=0.25)
    _save(fig, "f9_category_scale_coverage.png")


def fig_category_eff_rank(df: pd.DataFrame, metric: str, filename: str,
                          title: str, xlabel: str, topn: int = 15) -> None:
    """单一口径的类别效率排行图，避免两种口径混在同一张图中。"""
    d = df.nlargest(topn, metric).sort_values(metric, ascending=True)
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    ax.barh(d["display_code"], d[metric], color="#238b45")
    for y, (_, r) in enumerate(d.iterrows()):
        ax.text(r[metric], y, f"  {r[metric]:.2f}", va="center", fontsize=8)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("类别（展示编码）")
    ax.grid(axis="x", alpha=0.25)
    _save(fig, filename)


def fig_anomaly(d: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    flagged = d[d["risk_flag_count"] > 0]
    ax.scatter(d["zero_rate"] * 100, d["cv_series_median"], s=10 + d["store_count"] * 0.5,
               c="#9ecae1", alpha=0.5, edgecolors="none", label="其他 SKU")
    ax.scatter(flagged["zero_rate"] * 100, flagged["cv_series_median"],
               s=20 + flagged["store_count"] * 0.8, c="#d62728", alpha=0.85,
               edgecolors="white", linewidths=0.4, label="触发至少 1 项风险标记")
    ax.set_title("SKU 零销量率与销量波动（点大小=覆盖门店数）")
    ax.set_xlabel("零销量率（%）")
    ax.set_ylabel("日销量变异系数（序列中位数）")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)
    _save(fig, "f10_sku_risk.png")


def run() -> dict:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    con = _con()
    sku, extra = load_base(con)

    # 展示编码
    sku = sku.merge(extra["mapping"]["product"], left_on="product_id", right_on="raw_id", how="left")
    l1map = extra["mapping"]["l1"]
    l2map = extra["mapping"]["l2"]
    l3map = extra["mapping"]["l3"]

    sku = add_sku_metrics(sku)
    sku = stability_tiers(sku)
    sku = flag_anomalies(sku)
    sku["rank_eff_cov5"] = sku["per_series_day"].where(sku["store_count"] >= DEFAULT_MIN_COVERAGE).rank(
        ascending=False, method="min"
    )

    l1 = category_table(con, "first_category_id", sku, l1map)
    l2 = category_table(con, "second_category_id", sku, l2map)
    l3 = category_table(con, "third_category_id", sku, l3map)

    # 审计指定的复核对照片区
    cmp_pairs = [
        ("L1", l1, ["C05", "C22", "C21", "C17"]),
        ("L2", l2, ["S029"]),
        ("L3", l3, ["T185", "T083"]),
    ]
    cat_cmp = pd.concat([
        df[df["display_code"].isin(codes)].assign(level=level)
        for level, df, codes in cmp_pairs
    ])[["level", "display_code", "total_index", "store_count", "store_days",
        "sku_store_days", "category_sku_store_day_avg", "category_store_day_avg",
        "rank_total_index", "rank_store_day_avg", "rank_sku_store_day_avg"]]

    par = pareto(sku)
    sens = coverage_sensitivity(sku, THRESHOLDS)
    ht = head_tail(sku)
    bands = extra["bands"].copy()
    bands["band"] = pd.Categorical(bands["band"], categories=BAND_ORDER, ordered=True)
    bands = bands.sort_values("band")
    bands["row_share_pct"] = bands["rows"] / bands["rows"].sum() * 100

    top_scale = sku.head(20)[["display_code", "product_id", "total_index", "store_count",
                              "per_series_day", "zero_rate", "cv_series_median"]]
    top_eff = sku[sku["store_count"] >= DEFAULT_MIN_COVERAGE].nlargest(20, "per_series_day")[
        ["display_code", "product_id", "total_index", "store_count", "per_series_day",
         "zero_rate", "cv_series_median"]
    ]
    risk = sku[sku["risk_flag_count"] > 0].sort_values(
        ["risk_flag_count", "anomaly_rate"], ascending=False
    )[["display_code", "product_id", "store_count", "total_index", "per_series_day",
       "zero_rate", "cv_series_median", "anomaly_rate", "hhi", "risk_flag_count",
       "flag_high_cv", "flag_high_zero", "flag_many_anomaly_days", "flag_store_concentration"]]

    # 落表
    sku.to_csv(OUT_TABLES / "t1_sku_metrics.csv", index=False, encoding="utf-8-sig")
    top_scale.to_csv(OUT_TABLES / "t2_top20_scale.csv", index=False, encoding="utf-8-sig")
    top_eff.to_csv(OUT_TABLES / "t3_top20_efficiency.csv", index=False, encoding="utf-8-sig")
    l1.to_csv(OUT_TABLES / "t4_category_l1.csv", index=False, encoding="utf-8-sig")
    l2.to_csv(OUT_TABLES / "t5_category_l2.csv", index=False, encoding="utf-8-sig")
    l3.to_csv(OUT_TABLES / "t6_category_l3.csv", index=False, encoding="utf-8-sig")
    sens.to_csv(OUT_TABLES / "t7_coverage_sensitivity.csv", index=False, encoding="utf-8-sig")
    ht.to_csv(OUT_TABLES / "t8_head_tail.csv", index=False, encoding="utf-8-sig")
    risk.to_csv(OUT_TABLES / "t9_sku_risk_flags.csv", index=False, encoding="utf-8-sig")
    bands.to_csv(OUT_TABLES / "t10_discount_bands.csv", index=False, encoding="utf-8-sig")
    cat_cmp.to_csv(OUT_TABLES / "t11_category_metric_comparison.csv", index=False, encoding="utf-8-sig")
    extra["mapping"]["product"].to_csv(OUT_TABLES / "map_product.csv", index=False, encoding="utf-8-sig")
    l1map.to_csv(OUT_TABLES / "map_l1.csv", index=False, encoding="utf-8-sig")
    l2map.to_csv(OUT_TABLES / "map_l2.csv", index=False, encoding="utf-8-sig")
    l3map.to_csv(OUT_TABLES / "map_l3.csv", index=False, encoding="utf-8-sig")

    summary = {
        "sku_count": int(len(sku)),
        "coverage": {
            "median": float(sku["store_count"].median()),
            "mean": float(sku["store_count"].mean()),
            "p10": float(sku["store_count"].quantile(0.1)),
            "p90": float(sku["store_count"].quantile(0.9)),
            "max": int(sku["store_count"].max()),
            "skus_le_2_stores": int((sku["store_count"] <= 2).sum()),
            "skus_le_5_stores": int((sku["store_count"] <= 5).sum()),
        },
        "pareto": par,
        "spearman_total_vs_coverage": float(sku["total_index"].corr(sku["store_count"], method="spearman")),
        "spearman_total_vs_efficiency": float(sku["total_index"].corr(sku["per_series_day"], method="spearman")),
        "spearman_scale_rank_vs_eff_rank": float(
            sku["rank_scale"].corr(sku["rank_eff_all"], method="spearman")
        ),
        "top20_scale_mean_coverage": float(sku.head(20)["store_count"].mean()),
        "top20_eff_mean_coverage": float(top_eff["store_count"].mean()),
        "zero_rate": {
            "median": float(sku["zero_rate"].median()),
            "p90": float(sku["zero_rate"].quantile(0.9)),
            "p99": float(sku["zero_rate"].quantile(0.99)),
            "max": float(sku["zero_rate"].max()),
            "skus_gt_20pct": int((sku["zero_rate"] > 0.2).sum()),
        },
        "cv": {
            "median": float(sku["cv_series_median"].median()),
            "p90": float(sku["cv_series_median"].quantile(0.9)),
            "max": float(sku["cv_series_median"].max()),
        },
        "risk": {
            "flagged_skus": int((sku["risk_flag_count"] > 0).sum()),
            "multi_flag_skus": int((sku["risk_flag_count"] >= 2).sum()),
            "thresholds": {
                "cv_p95": float(sku["cv_series_median"].quantile(FLAG_Q)),
                "zero_p95": float(sku["zero_rate"].quantile(FLAG_Q)),
                "hhi_p95": float(sku.loc[sku["store_count"] >= 5, "hhi"].quantile(FLAG_Q)),
                "hhi_min_store_count": 5,
                "anomaly_rate_gt": 0.05,
            },
        },
        "coverage_sensitivity": sens.to_dict("records"),
        "head_tail": ht.to_dict("records"),
        "top1_scale": top_scale.head(1).to_dict("records"),
        "top1_eff": top_eff.head(1).to_dict("records"),
        "category_comparison": cat_cmp.to_dict("records"),
        "category_top_store_day": {
            "L1": l1.nlargest(5, "category_store_day_avg")[
                ["display_code", "category_store_day_avg", "rank_store_day_avg"]
            ].to_dict("records"),
            "L2": l2.nlargest(5, "category_store_day_avg")[
                ["display_code", "category_store_day_avg", "rank_store_day_avg"]
            ].to_dict("records"),
            "L3": l3.nlargest(5, "category_store_day_avg")[
                ["display_code", "category_store_day_avg", "rank_store_day_avg"]
            ].to_dict("records"),
        },
    }
    with open(OUT_TABLES / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    # 图
    fig_top20(sku)
    fig_top20_eff(sku, DEFAULT_MIN_COVERAGE)
    fig_rank_compare(sku)
    fig_coverage(sku)
    fig_pareto(sku)
    fig_long_tail(sku)
    fig_zero_cv(sku)
    fig_category(l1, l2, l3)
    fig_category_scale_cov(l3)
    fig_category_eff_rank(
        l1, "category_store_day_avg", "f11_category_store_day_rank.png",
        "一级类别：类别单店日均销量指数 Top 15", "类别单店日均销量指数"
    )
    fig_category_eff_rank(
        l1, "category_sku_store_day_avg", "f12_category_sku_store_day_rank.png",
        "一级类别：类别单 SKU-门店日均销量指数 Top 15", "类别单 SKU-门店日均销量指数"
    )
    fig_anomaly(sku)

    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
