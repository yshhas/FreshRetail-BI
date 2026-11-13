"""P1：模块一 销量经营状况描述性分析（仅使用 train 90 天）。"""

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
OUT_TABLES = ROOT / "data" / "analysis" / "p1"
OUT_FIGS = ROOT / "reports" / "figures" / "p1"
RAW_TRAIN = ROOT / "data" / "raw" / "freshretailnet50k" / "train.parquet"

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
PERIODS = [
    (0, 5, "凌晨 0-5"),
    (6, 8, "早市 6-8"),
    (9, 11, "上午 9-11"),
    (12, 13, "午间 12-13"),
    (14, 16, "下午 14-16"),
    (17, 19, "傍晚 17-19"),
    (20, 23, "夜间 20-23"),
]


def _q(path: Path, sql: str) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{str(path).replace(chr(92), '/')}')")
    df = con.execute(sql).df()
    con.close()
    return df


def load_inputs() -> dict:
    daily = pd.read_parquet(DERIVED / "agg_daily.parquet")
    daily["dt"] = pd.to_datetime(daily["dt"])
    holiday = _q(
        RAW_TRAIN,
        """
        SELECT dt::DATE AS dt, MAX(holiday_flag::INT) AS holiday_proxy
        FROM t GROUP BY 1 ORDER BY 1
        """,
    )
    holiday["dt"] = pd.to_datetime(holiday["dt"])
    daily = daily.merge(holiday, on="dt", how="left")
    daily["weekday"] = daily["dt"].dt.dayofweek

    product_count = _q(
        RAW_TRAIN,
        "SELECT store_id, COUNT(DISTINCT product_id) AS product_count FROM t GROUP BY 1",
    )

    return {
        "daily": daily,
        "hour_profile": pd.read_parquet(DERIVED / "agg_hour_profile.parquet"),
        "hour_weekday": pd.read_parquet(DERIVED / "agg_hour_weekday.parquet"),
        "store_summary": pd.read_parquet(DERIVED / "agg_store_summary.parquet"),
        "store_day": pd.read_parquet(DERIVED / "agg_store_day.parquet"),
        "anomaly": pd.read_parquet(DERIVED / "diag_anomaly_days.parquet"),
        "product_count": product_count,
    }


def build_daily(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.sort_values("dt").copy()
    d["ma7"] = d["sales_index_total"].rolling(7, min_periods=7).mean()
    d["daily_change_pct"] = d["sales_index_total"].pct_change() * 100
    med = d["sales_index_total"].median()
    mad = (d["sales_index_total"] - med).abs().median()
    d["robust_z"] = (d["sales_index_total"] - med) / (1.4826 * mad)
    d["is_anomaly"] = d["robust_z"].abs() > 3
    d["weekday_cn"] = d["weekday"].map(dict(enumerate(WEEKDAY_CN)))
    return d


def weekday_summary(daily: pd.DataFrame) -> pd.DataFrame:
    g = daily.groupby("weekday")["sales_index_total"]
    out = pd.DataFrame({
        "weekday": range(7),
        "weekday_cn": WEEKDAY_CN,
        "days": g.size().values,
        "mean": g.mean().values,
        "median": g.median().values,
        "std": g.std().values,
        "min": g.min().values,
        "max": g.max().values,
        "sum": g.sum().values,
    })
    out["share_pct"] = out["sum"] / out["sum"].sum() * 100
    out["pct_vs_overall_mean"] = (out["mean"] / daily["sales_index_total"].mean() - 1) * 100
    return out


def holiday_comparison(daily: pd.DataFrame) -> dict:
    overall = daily.groupby("holiday_proxy")["sales_index_total"].agg(["mean", "median", "count"])
    weekdays_only = daily[daily["weekday"] < 5]
    within = weekdays_only.groupby("holiday_proxy")["sales_index_total"].agg(["mean", "median", "count"])
    return {
        "overall": overall,
        "within_weekdays": within,
        "overall_uplift_pct": (overall.loc[1, "mean"] / overall.loc[0, "mean"] - 1) * 100,
        "weekday_only_uplift_pct": (
            within.loc[1, "mean"] / within.loc[0, "mean"] - 1
        ) * 100 if 1 in within.index else np.nan,
        "holiday_days": int((daily["holiday_proxy"] == 1).sum()),
        "holiday_weekdays": int(((daily["holiday_proxy"] == 1) & (daily["weekday"] < 5)).sum()),
    }


def hour_summary(hour_profile: pd.DataFrame) -> pd.DataFrame:
    h = hour_profile.sort_values("hour").copy()
    h["share_pct"] = h["share"] * 100
    h["cum_share_pct"] = h["share_pct"].cumsum()
    h["period"] = ""
    for lo, hi, name in PERIODS:
        h.loc[(h["hour"] >= lo) & (h["hour"] <= hi), "period"] = name
    return h


def period_summary(hour_df: pd.DataFrame) -> pd.DataFrame:
    g = hour_df.groupby("period", sort=False)["share_pct"].sum().reset_index()
    g.columns = ["period", "share_pct"]
    g["cum_share_pct"] = g["share_pct"].cumsum()
    return g


def hour_weekday_matrix(hw: pd.DataFrame) -> pd.DataFrame:
    pivot = hw.pivot(index="weekday", columns="hour", values="sales_index").sort_index()
    return pivot.div(pivot.values.sum()) * 100


def store_table(store_summary: pd.DataFrame, product_count: pd.DataFrame) -> pd.DataFrame:
    s = store_summary.merge(product_count, on="store_id", how="left")
    # 效率口径：单 SKU 日均销量指数，用于剥离商品数（铺货广度）的影响
    s["per_sku_day_index"] = s["per_day_index"] / s["product_count"]
    s = s.sort_values("per_day_index", ascending=False).reset_index(drop=True)
    s["rank"] = s.index + 1
    return s


def store_distribution(store: pd.DataFrame) -> dict:
    x = store["per_day_index"]
    e = store["per_sku_day_index"]
    total = store["total_index"]
    top10_n = max(1, int(len(store) * 0.1))
    return {
        "n_stores": int(len(store)),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "p10": float(x.quantile(0.1)),
        "p25": float(x.quantile(0.25)),
        "p75": float(x.quantile(0.75)),
        "p90": float(x.quantile(0.9)),
        "min": float(x.min()),
        "max": float(x.max()),
        "p90_p10_ratio": float(x.quantile(0.9) / x.quantile(0.1)),
        "cv_of_store_means": float(x.std(ddof=0) / x.mean()),
        "top10pct_share_of_total_pct": float(total.nlargest(top10_n).sum() / total.sum() * 100),
        "top20pct_share_of_total_pct": float(total.nlargest(max(1, int(len(store) * 0.2))).sum() / total.sum() * 100),
        "per_sku_median": float(e.median()),
        "per_sku_p10": float(e.quantile(0.1)),
        "per_sku_p90": float(e.quantile(0.9)),
        "per_sku_p90_p10_ratio": float(e.quantile(0.9) / e.quantile(0.1)),
        "spearman_scale_vs_product_count": float(x.corr(store["product_count"], method="spearman")),
        "spearman_efficiency_vs_product_count": float(e.corr(store["product_count"], method="spearman")),
        "spearman_rank_scale_vs_efficiency": float(
            x.rank().corr(e.rank(), method="spearman")
        ),
    }


def store_quartile_profile(store: pd.DataFrame) -> pd.DataFrame:
    s = store.copy()
    s["tier"] = pd.qcut(s["per_day_index"], 4, labels=["最低 25%", "次低 25%", "次高 25%", "最高 25%"])
    prof = s.groupby("tier", observed=True).agg(
        stores=("store_id", "count"),
        per_day_median=("per_day_index", "median"),
        per_sku_median=("per_sku_day_index", "median"),
        cv_median=("cv", "median"),
        stockout_sku_day_rate_median=("stockout_sku_day_rate", "median"),
        promo_rate_median=("promo_rate", "median"),
        product_count_median=("product_count", "median"),
    ).reset_index()
    return prof


def store_efficiency_quartile(store: pd.DataFrame) -> pd.DataFrame:
    s = store.copy()
    s["tier"] = pd.qcut(s["per_sku_day_index"], 4, labels=["最低 25%", "次低 25%", "次高 25%", "最高 25%"])
    prof = s.groupby("tier", observed=True).agg(
        stores=("store_id", "count"),
        per_sku_median=("per_sku_day_index", "median"),
        per_day_median=("per_day_index", "median"),
        cv_median=("cv", "median"),
        stockout_sku_day_rate_median=("stockout_sku_day_rate", "median"),
        promo_rate_median=("promo_rate", "median"),
        product_count_median=("product_count", "median"),
    ).reset_index()
    return prof


def daily_anomalies(daily: pd.DataFrame) -> pd.DataFrame:
    return daily[daily["is_anomaly"]][
        ["dt", "sales_index_total", "per_store_index", "robust_z", "daily_change_pct", "weekday_cn"]
    ].copy()


def store_cross_section_anomalies(store: pd.DataFrame) -> pd.DataFrame:
    med = store["per_day_index"].median()
    mad = (store["per_day_index"] - med).abs().median()
    s = store.copy()
    s["robust_z"] = (s["per_day_index"] - med) / (1.4826 * mad)
    out = s[s["robust_z"].abs() > 3].copy()
    out["direction"] = np.where(out["robust_z"] > 0, "极高", "极低")
    return out.sort_values("robust_z", ascending=False)[
        ["store_id", "city_id", "per_day_index", "robust_z", "direction",
         "stockout_sku_day_rate", "promo_rate", "product_count"]
    ]


def store_day_anomalies(store_day: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sid, g in store_day.groupby("store_id"):
        s = g.sort_values("dt")["sales_index"]
        med = s.median()
        mad = (s - med).abs().median()
        if mad == 0:
            continue
        z = (s - med) / (1.4826 * mad)
        flag = z.abs() > 3
        if flag.any():
            for idx in s.index[flag]:
                rows.append({
                    "store_id": sid,
                    "dt": pd.to_datetime(g.loc[idx, "dt"]),
                    "sales_index": float(g.loc[idx, "sales_index"]),
                    "store_median": float(med),
                    "robust_z": float(z.loc[idx]),
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("robust_z", ascending=False)


def sustained_low(store_day: pd.DataFrame, ratio: float = 0.7,
                  window: int = 7, min_run: int = 7) -> tuple[pd.DataFrame, int]:
    rows = []
    for sid, g in store_day.groupby("store_id"):
        s = g.sort_values("dt")["sales_index"].reset_index(drop=True)
        base = s.median()
        if base <= 0:
            continue
        roll = s.rolling(window, min_periods=window).mean()
        flag = (roll < ratio * base).fillna(False).to_numpy()
        best = cur = 0
        for v in flag:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        if best >= min_run:
            rows.append({"store_id": sid, "median": float(base), "max_low_run_days": int(best)})
    df = pd.DataFrame(rows).sort_values("max_low_run_days", ascending=False) if rows else pd.DataFrame()
    return df, int(len(df))


# ---------------- 图表 ----------------

def _save(fig, name: str) -> None:
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_trend(daily: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(daily["dt"], daily["sales_index_total"], color="#9ecae1", lw=1.2, label="日销量指数")
    ax.plot(daily["dt"], daily["ma7"], color="#08519c", lw=2.2, label="7 日移动平均")
    a = daily[daily["is_anomaly"]]
    ax.scatter(a["dt"], a["sales_index_total"], color="#d62728", s=60, zorder=5, label="异常日（稳健 z>3）")
    for _, r in a.iterrows():
        ax.annotate(r["dt"].strftime("%m-%d"), (r["dt"], r["sales_index_total"]),
                    textcoords="offset points", xytext=(0, 10), ha="center", fontsize=9, color="#d62728")
    ax.set_title("2024-03-28 至 2024-06-25 样本日销量指数趋势（90 天）")
    ax.set_xlabel("日期")
    ax.set_ylabel("归一化销量指数（日合计）")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, loc="upper left")
    _save(fig, "f1_daily_trend.png")


def fig_weekday(wd: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    colors = ["#6baed6"] * 5 + ["#fb6a4a"] * 2
    bars = ax.bar(wd["weekday_cn"], wd["mean"], yerr=wd["std"], color=colors,
                  capsize=3, error_kw={"elinewidth": 0.8, "ecolor": "#666666"})
    for b, v in zip(bars, wd["mean"]):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_title("周内日均销量指数对比（误差线为日度标准差）")
    ax.set_xlabel("星期")
    ax.set_ylabel("日均归一化销量指数")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f2_weekday.png")


def fig_hour(hour: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(hour["hour"], hour["share_pct"], color="#4292c6")
    for _, r in hour.nlargest(3, "share_pct").iterrows():
        ax.annotate(f"{r['share_pct']:.1f}%", (r["hour"], r["share_pct"]),
                    textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8)
    ax.set_title("0–23 点销量份额分布")
    ax.set_xlabel("小时")
    ax.set_ylabel("销量份额（%）")
    ax.set_xticks(range(0, 24, 2))
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f3_hour_share.png")


def fig_heatmap(mat: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.2))
    im = ax.imshow(mat.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24), fontsize=8)
    ax.set_yticks(range(7))
    ax.set_yticklabels(WEEKDAY_CN)
    ax.set_title("星期 × 小时销量份额热力图（占全期总指数 %）")
    ax.set_xlabel("小时")
    ax.set_ylabel("星期")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("份额（%）")
    _save(fig, "f4_weekday_hour_heatmap.png")


def fig_store_dist(store: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.hist(store["per_day_index"], bins=40, color="#9ecae1", edgecolor="white")
    for q, c, label in [(0.1, "#fd8d3c", "P10"), (0.5, "#d62728", "中位数"), (0.9, "#fd8d3c", "P90")]:
        v = store["per_day_index"].quantile(q)
        ax.axvline(v, color=c, ls="--", lw=1.2)
        ax.text(v, ax.get_ylim()[1] * 0.92, f"{label}\n{v:,.1f}", ha="center", fontsize=8, color=c)
    ax.set_title("898 家门店单店日均销量指数分布")
    ax.set_xlabel("单店日均归一化销量指数")
    ax.set_ylabel("门店数")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f5_store_distribution.png")


def fig_store_rank(store: pd.DataFrame) -> None:
    top = store.head(15)
    bottom = store.tail(15)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    for ax, df, color, title in [
        (axes[0], top.iloc[::-1], "#08519c", "单店日均销量指数 Top 15"),
        (axes[1], bottom, "#d94801", "单店日均销量指数 Bottom 15"),
    ]:
        ax.barh([f"S{int(s):04d}" for s in df["store_id"]], df["per_day_index"], color=color)
        ax.set_title(title)
        ax.set_xlabel("单店日均归一化销量指数")
        ax.grid(axis="x", alpha=0.25)
    _save(fig, "f6_store_ranking.png")


def fig_daily_change(daily: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.2))
    colors = np.where(daily["is_anomaly"], "#d62728", "#9ecae1")
    ax.bar(daily["dt"], daily["daily_change_pct"], color=colors, width=0.8)
    ax.axhline(0, color="#444444", lw=0.8)
    ax.set_title("日环比变化（红色为异常日）")
    ax.set_xlabel("日期")
    ax.set_ylabel("日环比（%）")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f7_daily_change.png")


def fig_store_scatter(store: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    sc = ax.scatter(store["per_day_index"], store["cv"],
                    s=8 + store["product_count"] * 1.2,
                    c=store["stockout_sku_day_rate"] * 100,
                    cmap="viridis", alpha=0.75, edgecolors="none")
    ax.set_title("门店经营水平与波动（点大小=商品数，颜色=SKU-日缺货率%）")
    ax.set_xlabel("单店日均归一化销量指数")
    ax.set_ylabel("门店日销量变异系数（CV）")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("缺货率（%）")
    ax.grid(alpha=0.25)
    _save(fig, "f8_store_scatter.png")


def fig_store_breadth(store: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    sc = ax.scatter(store["product_count"], store["per_day_index"],
                    c=store["per_sku_day_index"], cmap="coolwarm",
                    s=14, alpha=0.8, edgecolors="none")
    ax.set_title("门店商品数、规模与效率的关系")
    ax.set_xlabel("门店在售商品数（SKU）")
    ax.set_ylabel("单店日均归一化销量指数（规模口径）")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("单 SKU 日均销量指数（效率口径）")
    ax.grid(alpha=0.25)
    _save(fig, "f9_store_breadth_vs_scale.png")


def run() -> dict:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    data = load_inputs()

    daily = build_daily(data["daily"])
    wd = weekday_summary(daily)
    hol = holiday_comparison(daily)
    hour = hour_summary(data["hour_profile"])
    periods = period_summary(hour)
    mat = hour_weekday_matrix(data["hour_weekday"])
    store = store_table(data["store_summary"], data["product_count"])
    sdist = store_distribution(store)
    quart = store_quartile_profile(store)
    eff_quart = store_efficiency_quartile(store)
    d_anom = daily_anomalies(daily)
    s_cross = store_cross_section_anomalies(store)
    s_day = store_day_anomalies(data["store_day"])
    low, low_n = sustained_low(data["store_day"])

    peak = hour.nlargest(3, "share_pct")[["hour", "share_pct"]]
    daytime = hour[(hour["hour"] >= 6) & (hour["hour"] <= 22)]
    trough = daytime.nsmallest(1, "share_pct")[["hour", "share_pct"]].iloc[0]
    overnight_share = hour[hour["hour"] <= 5]["share_pct"].sum()

    first30 = daily.head(30)["sales_index_total"].mean()
    last30 = daily.tail(30)["sales_index_total"].mean()
    peak_row = daily.loc[daily["sales_index_total"].idxmax()]
    low_row = daily.loc[daily["sales_index_total"].idxmin()]

    summary = {
        "days": int(len(daily)),
        "total_index_sum": float(daily["sales_index_total"].sum()),
        "daily_mean": float(daily["sales_index_total"].mean()),
        "daily_median": float(daily["sales_index_total"].median()),
        "daily_cv": float(daily["sales_index_total"].std(ddof=0) / daily["sales_index_total"].mean()),
        "first30_mean": float(first30),
        "last30_mean": float(last30),
        "last30_vs_first30_pct": float((last30 / first30 - 1) * 100),
        "peak_date": str(peak_row["dt"].date()),
        "peak_value": float(peak_row["sales_index_total"]),
        "low_date": str(low_row["dt"].date()),
        "low_value": float(low_row["sales_index_total"]),
        "peak_low_ratio": float(peak_row["sales_index_total"] / low_row["sales_index_total"]),
        "weekend_uplift_pct": float(
            wd.loc[wd["weekday"] >= 5, "mean"].mean() / wd.loc[wd["weekday"] < 5, "mean"].mean() * 100 - 100
        ),
        "best_weekday": WEEKDAY_CN[int(wd.loc[wd["mean"].idxmax(), "weekday"])],
        "worst_weekday": WEEKDAY_CN[int(wd.loc[wd["mean"].idxmin(), "weekday"])],
        "holiday_days": hol["holiday_days"],
        "holiday_weekdays": hol["holiday_weekdays"],
        "holiday_overall_uplift_pct": float(hol["overall_uplift_pct"]),
        "holiday_weekday_only_uplift_pct": float(hol["weekday_only_uplift_pct"]),
        "peak_hours": peak.to_dict("records"),
        "trough_hour_6_22": int(trough["hour"]),
        "trough_share_pct": float(trough["share_pct"]),
        "overnight_0_5_share_pct": float(overnight_share),
        "periods": periods.to_dict("records"),
        "store": sdist,
        "anomaly_days": int(len(d_anom)),
        "store_cross_anomalies": int(len(s_cross)),
        "store_day_anomaly_rows": int(len(s_day)),
        "stores_with_store_day_anomaly": int(s_day["store_id"].nunique()) if len(s_day) else 0,
        "sustained_low_stores": low_n,
    }

    # 落表
    daily.to_csv(OUT_TABLES / "t1_daily.csv", index=False, encoding="utf-8-sig")
    wd.to_csv(OUT_TABLES / "t2_weekday.csv", index=False, encoding="utf-8-sig")
    hour.to_csv(OUT_TABLES / "t3_hour.csv", index=False, encoding="utf-8-sig")
    periods.to_csv(OUT_TABLES / "t4_period.csv", index=False, encoding="utf-8-sig")
    mat.to_csv(OUT_TABLES / "t5_weekday_hour.csv", encoding="utf-8-sig")
    store.to_csv(OUT_TABLES / "t6_store.csv", index=False, encoding="utf-8-sig")
    quart.to_csv(OUT_TABLES / "t7_store_quartile.csv", index=False, encoding="utf-8-sig")
    eff_quart.to_csv(OUT_TABLES / "t12_store_efficiency_quartile.csv", index=False, encoding="utf-8-sig")
    d_anom.to_csv(OUT_TABLES / "t8_anomaly_days.csv", index=False, encoding="utf-8-sig")
    s_cross.to_csv(OUT_TABLES / "t9_store_cross_anomaly.csv", index=False, encoding="utf-8-sig")
    if len(s_day):
        s_day.to_csv(OUT_TABLES / "t10_store_day_anomaly.csv", index=False, encoding="utf-8-sig")
    if low_n:
        low.to_csv(OUT_TABLES / "t11_sustained_low.csv", index=False, encoding="utf-8-sig")
    with open(OUT_TABLES / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    # 图
    fig_trend(daily)
    fig_weekday(wd)
    fig_hour(hour)
    fig_heatmap(mat)
    fig_store_dist(store)
    fig_store_rank(store)
    fig_daily_change(daily)
    fig_store_scatter(store)
    fig_store_breadth(store)

    return summary


if __name__ == "__main__":
    s = run()
    print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
