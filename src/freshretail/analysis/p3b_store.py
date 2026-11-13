"""P3-B：门店经营分层与四象限分析（仅 train）。"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.robust.norms import HuberT, TukeyBiweight
from statsmodels.stats.outliers_influence import OLSInfluence

matplotlib.use("Agg")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
DERIVED = ROOT / "data" / "derived"
CLEAN = DERIVED / "clean_train.parquet"
STORE_BASE = DERIVED / "agg_store_summary.parquet"
STORE_DAY = DERIVED / "agg_store_day.parquet"
P1_STORE = ROOT / "data" / "analysis" / "p1" / "t6_store.csv"
P1_ANOM = ROOT / "data" / "analysis" / "p1" / "t10_store_day_anomaly.csv"
P1_LOW = ROOT / "data" / "analysis" / "p1" / "t11_sustained_low.csv"

OUT_TABLES = ROOT / "data" / "analysis" / "p3b"
OUT_FIGS = ROOT / "reports" / "figures" / "p3b"

MIN_SKU = 10
THRESHOLDS = [5, 10, 20, 30]
WEIGHT_FLAG = 0.5
HUBER_M = 1.345
R2_REF = 0.10


# ---------------- 数据 ----------------

def load_store_metrics() -> pd.DataFrame:
    """复用 P1 门店表，只补零销率、小时槽位缺货率、异常/持续低销。"""
    base = pd.read_csv(P1_STORE)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW clean AS SELECT * FROM read_parquet('{CLEAN.as_posix()}')")
    extra = con.execute("""
        SELECT store_id,
               AVG(CASE WHEN sales_index = 0 THEN 1.0 ELSE 0 END) AS zero_rate,
               SUM(stockout_hours_6_22) / (16.0 * COUNT(*)) AS stockout_hour_rate,
               COUNT(*) AS observed_rows
        FROM clean GROUP BY 1
    """).df()
    base = base.merge(extra, on="store_id", how="left")
    anomaly = pd.read_csv(P1_ANOM).groupby("store_id").size().rename("anomaly_days").reset_index()
    base = base.merge(anomaly, on="store_id", how="left")
    base["anomaly_days"] = base["anomaly_days"].fillna(0).astype(int)
    base["anomaly_rate"] = base["anomaly_days"] / base["store_days"]
    low = pd.read_csv(P1_LOW)[["store_id", "max_low_run_days"]]
    base = base.merge(low, on="store_id", how="left")
    base["max_low_run_days"] = base["max_low_run_days"].fillna(0).astype(int)
    base["sku_count"] = base["product_count"]
    # 契约校验：单 SKU 日均必须等于单店日均 / SKU 数
    diff = (base["per_sku_day_index"] - base["per_day_index"] / base["sku_count"]).abs().max()
    if diff > 1e-9:
        raise AssertionError(f"per_sku_day_index 与 per_day_index/sku_count 不一致：{diff}")
    return base


def model_frame(df: pd.DataFrame, min_sku: int) -> pd.DataFrame:
    d = df[df["sku_count"] >= min_sku].copy()
    d["x"] = np.log(d["sku_count"].astype(float))
    d["y"] = np.log1p(d["per_sku_day_index"].astype(float))
    return d


# ---------------- 模型 ----------------

def r2_corr(y, fitted) -> float:
    y = np.asarray(y, float)
    fitted = np.asarray(fitted, float)
    if np.std(y) == 0 or np.std(fitted) == 0:
        return np.nan
    return float(np.corrcoef(y, fitted)[0, 1] ** 2)


def r2_weighted(y, fitted, weights) -> float:
    y = np.asarray(y, float)
    fitted = np.asarray(fitted, float)
    w = np.asarray(weights, float)
    ybar = np.average(y, weights=w)
    ss_res = np.sum(w * (y - fitted) ** 2)
    ss_tot = np.sum(w * (y - ybar) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan


def fit_rlm(d: pd.DataFrame, norm: str = "huber", city_fe: bool = False) -> dict:
    y = d["y"].to_numpy(float)
    X = np.column_stack([np.ones(len(d)), d["x"].to_numpy(float)])
    if city_fe:
        dummies = pd.get_dummies(d["city_id"].astype(int), prefix="c", drop_first=True, dtype=float)
        X = np.column_stack([X, dummies.to_numpy(float)])
    if norm == "huber":
        res = sm.RLM(y, X, M=HuberT(t=HUBER_M)).fit()
    elif norm == "tukey":
        res = sm.RLM(y, X, M=TukeyBiweight()).fit()
    else:
        raise ValueError(norm)
    fitted = np.asarray(res.fittedvalues, float)
    resid = np.asarray(res.resid, float)
    weights = np.asarray(res.weights, float)
    slope = float(res.params[1])
    se = float(res.bse[1])
    return {
        "result": res, "y": y, "X": X, "fitted": fitted, "resid": resid,
        "weights": weights, "slope": slope, "se": se,
        "ci_low": slope - 1.96 * se, "ci_high": slope + 1.96 * se,
        "r2_corr": r2_corr(y, fitted),
        "r2_weighted": r2_weighted(y, fitted, weights),
        "resid_mad": float(np.median(np.abs(resid - np.median(resid)))),
    }


def fit_ols(d: pd.DataFrame) -> dict:
    y = d["y"].to_numpy(float)
    X = sm.add_constant(d["x"].to_numpy(float))
    res = sm.OLS(y, X).fit()
    fitted = np.asarray(res.fittedvalues, float)
    resid = np.asarray(res.resid, float)
    infl = OLSInfluence(res)
    return {
        "result": res, "y": y, "X": X, "fitted": fitted, "resid": resid,
        "slope": float(res.params[1]),
        "ci_low": float(res.conf_int()[1, 0]), "ci_high": float(res.conf_int()[1, 1]),
        "r2_corr": r2_corr(y, fitted),
        "hat": np.asarray(infl.hat_matrix_diag, float),
        "cooks": np.asarray(infl.cooks_distance[0], float),
    }


def fit_quantreg(d: pd.DataFrame) -> dict:
    y = d["y"].to_numpy(float)
    X = sm.add_constant(d["x"].to_numpy(float))
    res = sm.QuantReg(y, X).fit(q=0.5)
    fitted = np.asarray(res.fittedvalues, float)
    return {"slope": float(res.params[1]), "r2_corr": r2_corr(y, fitted)}


def binned_residual(fitted, resid, bins: int = 10) -> dict:
    q = pd.qcut(pd.Series(fitted), bins, duplicates="drop")
    g = pd.DataFrame({"bin": q, "resid": resid}).groupby("bin", observed=True)["resid"].agg(["mean", "count"])
    return {
        "max_abs_bin_mean": float(g["mean"].abs().max()),
        "bin_means": g["mean"].tolist(),
        "bin_counts": g["count"].tolist(),
    }


def model_comparison(d: pd.DataFrame, main: dict) -> pd.DataFrame:
    ols = fit_ols(d)
    tukey = fit_rlm(d, norm="tukey")
    qr = fit_quantreg(d)
    fe = fit_rlm(d, norm="huber", city_fe=True)
    main_resid = main["resid"]
    rows = [
        {"model": "RLM-Huber", "slope": main["slope"], "ci_low": main["ci_low"],
         "ci_high": main["ci_high"], "r2_corr": main["r2_corr"],
         "r2_weighted": main["r2_weighted"], "resid_mad": main["resid_mad"],
         "resid_corr_with_main": 1.0},
        {"model": "RLM-Tukey", "slope": tukey["slope"], "ci_low": tukey["ci_low"],
         "ci_high": tukey["ci_high"], "r2_corr": tukey["r2_corr"],
         "r2_weighted": tukey["r2_weighted"], "resid_mad": tukey["resid_mad"],
         "resid_corr_with_main": float(np.corrcoef(main_resid, tukey["resid"])[0, 1])},
        {"model": "QuantReg-median", "slope": qr["slope"], "ci_low": np.nan,
         "ci_high": np.nan, "r2_corr": qr["r2_corr"], "r2_weighted": np.nan,
         "resid_mad": np.nan, "resid_corr_with_main": np.nan},
        {"model": "OLS", "slope": ols["slope"], "ci_low": ols["ci_low"],
         "ci_high": ols["ci_high"], "r2_corr": ols["r2_corr"],
         "r2_weighted": np.nan, "resid_mad": float(np.median(np.abs(ols["resid"] - np.median(ols["resid"])))),
         "resid_corr_with_main": float(np.corrcoef(main_resid, ols["resid"])[0, 1])},
        {"model": "RLM-Huber + City FE", "slope": fe["slope"], "ci_low": fe["ci_low"],
         "ci_high": fe["ci_high"], "r2_corr": fe["r2_corr"],
         "r2_weighted": fe["r2_weighted"], "resid_mad": fe["resid_mad"],
         "resid_corr_with_main": float(np.corrcoef(main_resid, fe["resid"])[0, 1])},
    ]
    return pd.DataFrame(rows)


# ---------------- 分层 ----------------

def assign_quadrants(df: pd.DataFrame, eff_col: str = "eff_resid") -> tuple[pd.DataFrame, float, float]:
    d = df.copy()
    p50_scale = float(d["per_day_index"].median())
    p50_eff = float(d[eff_col].median())
    high_scale = d["per_day_index"] > p50_scale
    high_eff = d[eff_col] > p50_eff
    d["quadrant"] = np.select(
        [high_scale & high_eff, high_scale & ~high_eff, ~high_scale & high_eff],
        ["Q1 高规模·相对高效率", "Q2 高规模·相对低效率", "Q3 低规模·相对高效率"],
        default="Q4 低规模·相对低效率",
    )
    return d, p50_scale, p50_eff


def fallback_efficiency(df: pd.DataFrame, deciles: int = 10) -> pd.Series:
    """拟合失败时的非参数替代：SKU 数分箱内的单 SKU 日均百分位。"""
    d = df.copy()
    d["sku_bin"] = pd.qcut(d["sku_count"], deciles, duplicates="drop")
    pct = d.groupby("sku_bin", observed=True)["per_sku_day_index"].rank(pct=True)
    return pct.reindex(d.index)


def threshold_analysis(df: pd.DataFrame, main_quad: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, trans = [], []
    main_map = main_quad.set_index("store_id")["quadrant"]
    for t in THRESHOLDS:
        d = model_frame(df, t)
        fit = fit_rlm(d, norm="huber")
        d = d.copy()
        d["eff_resid"] = fit["resid"]
        d, p50s, p50e = assign_quadrants(d, "eff_resid")
        counts = d["quadrant"].value_counts().to_dict()
        common = d.set_index("store_id")
        common_ids = common.index.intersection(main_map.index)
        same = (common.loc[common_ids, "quadrant"] == main_map.loc[common_ids]).mean()
        rows.append({
            "min_sku": t, "n_stores": len(d), "slope": fit["slope"],
            "ci_low": fit["ci_low"], "ci_high": fit["ci_high"],
            "r2_corr": fit["r2_corr"], "r2_weighted": fit["r2_weighted"],
            "resid_mad": fit["resid_mad"], "p50_scale": p50s, "p50_eff": p50e,
            "q1": counts.get("Q1 高规模·相对高效率", 0),
            "q2": counts.get("Q2 高规模·相对低效率", 0),
            "q3": counts.get("Q3 低规模·相对高效率", 0),
            "q4": counts.get("Q4 低规模·相对低效率", 0),
            "same_quadrant_share_vs_main": float(same),
            "common_stores": int(len(common_ids)),
        })
        for q_main in main_quad["quadrant"].unique():
            ids = main_quad.loc[main_quad["quadrant"] == q_main, "store_id"]
            ids = ids[ids.isin(common.index)]
            vc = common.loc[ids, "quadrant"].value_counts()
            for q_t, n in vc.items():
                trans.append({"min_sku": t, "main_quadrant": q_main,
                              "threshold_quadrant": q_t, "stores": int(n)})
    return pd.DataFrame(rows), pd.DataFrame(trans)


def quadrant_profile(df: pd.DataFrame) -> pd.DataFrame:
    metrics = ["per_day_index", "per_sku_day_index", "sku_count", "zero_rate",
               "stockout_sku_day_rate", "stockout_hour_rate", "cv", "anomaly_rate",
               "promo_rate", "max_low_run_days"]
    rows = []
    for q, g in df.groupby("quadrant", observed=True):
        row = {"quadrant": q, "stores": len(g)}
        row.update({f"{m}_median": float(g[m].median()) for m in metrics})
        row["sustained_low_share"] = float((g["max_low_run_days"] >= 7).mean())
        rows.append(row)
    order = ["Q1 高规模·相对高效率", "Q2 高规模·相对低效率",
             "Q3 低规模·相对高效率", "Q4 低规模·相对低效率"]
    out = pd.DataFrame(rows)
    out["quadrant"] = pd.Categorical(out["quadrant"], categories=order, ordered=True)
    return out.sort_values("quadrant").reset_index(drop=True)


def typical_stores(df: pd.DataFrame, eff_col: str = "eff_resid") -> pd.DataFrame:
    d = df.copy()
    d["z_scale"] = (d["per_day_index"] - d["per_day_index"].mean()) / d["per_day_index"].std(ddof=0)
    d["z_eff"] = (d[eff_col] - d[eff_col].mean()) / d[eff_col].std(ddof=0)
    rows = []
    for q, g in d.groupby("quadrant", observed=True):
        cx, cy = g["z_scale"].mean(), g["z_eff"].mean()
        dist = np.sqrt((g["z_scale"] - cx) ** 2 + (g["z_eff"] - cy) ** 2)
        idx = dist.sort_values(kind="mergesort").index[0]  # 距离相同按原顺序，结果确定
        r = d.loc[idx]
        rows.append({"quadrant": q, "store_id": int(r["store_id"]), "city_id": int(r["city_id"]),
                     "per_day_index": float(r["per_day_index"]),
                     "eff_resid": float(r[eff_col]), "sku_count": int(r["sku_count"])})
    return pd.DataFrame(rows)


# ---------------- 图表 ----------------

def _save(fig, name: str) -> None:
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_scale_dist(df: pd.DataFrame, p50: float) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hist(df["per_day_index"], bins=45, color="#9ecae1", edgecolor="white")
    ax.axvline(p50, color="#d62728", ls="--", lw=1.2)
    ax.text(p50, ax.get_ylim()[1] * 0.9, f"P50={p50:.2f}", color="#d62728", fontsize=9)
    ax.set_title("门店单店日均销量指数分布（898 家）")
    ax.set_xlabel("单店日均归一化销量指数")
    ax.set_ylabel("门店数")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f1_store_scale_distribution.png")


def fig_sku_scale(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.scatter(df["sku_count"], df["per_day_index"], s=12, alpha=0.55, color="#4292c6")
    ax.set_xscale("log")
    ax.set_title("门店 SKU 覆盖数与单店日均（898 家）")
    ax.set_xlabel("门店 90 天 SKU 覆盖数（对数）")
    ax.set_ylabel("单店日均归一化销量指数")
    ax.grid(alpha=0.25)
    _save(fig, "f2_sku_vs_scale.png")


def fig_sku_efficiency(df: pd.DataFrame, x_line, y_line) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.scatter(df["sku_count"], df["per_sku_day_index"], s=12, alpha=0.45, color="#6baed6")
    ax.plot(np.exp(x_line), np.expm1(y_line), color="#d62728", lw=2, label="Huber RLM 拟合")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("门店 SKU 覆盖数与单 SKU 日均（双对数）")
    ax.set_xlabel("门店 90 天 SKU 覆盖数（对数）")
    ax.set_ylabel("单 SKU 日均（对数轴）")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)
    _save(fig, "f3_sku_vs_efficiency.png")


def fig_diagnostics(df: pd.DataFrame, fit: dict, binned: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    axes[0].scatter(fit["fitted"], fit["resid"], s=10, alpha=0.45, color="#6baed6")
    axes[0].axhline(0, color="#444444", lw=0.8)
    axes[0].plot(np.sort(fit["fitted"]), np.zeros(len(fit["fitted"])), alpha=0)
    axes[0].set_title("残差 vs 拟合值")
    axes[0].set_xlabel("拟合值 log(1+单 SKU 日均)")
    axes[0].set_ylabel("稳健残差")
    axes[0].grid(alpha=0.25)
    axes[1].hist(fit["resid"], bins=40, color="#9ecae1", edgecolor="white")
    axes[1].set_title("稳健残差分布")
    axes[1].set_xlabel("残差")
    axes[1].set_ylabel("门店数")
    axes[1].grid(axis="y", alpha=0.25)
    _save(fig, "f4_model_diagnostics.png")


def fig_quadrant(df: pd.DataFrame, p50s: float, p50e: float) -> None:
    colors = {"Q1 高规模·相对高效率": "#08519c", "Q2 高规模·相对低效率": "#d94801",
              "Q3 低规模·相对高效率": "#238b45", "Q4 低规模·相对低效率": "#807dba"}
    fig, ax = plt.subplots(figsize=(9, 5.6))
    for q, g in df.groupby("quadrant", observed=True):
        ax.scatter(g["per_day_index"], g["eff_resid"], s=10 + g["sku_count"] * 0.5,
                   alpha=0.6, label=q, color=colors[q], edgecolors="none")
    ax.axvline(p50s, color="#444444", ls="--", lw=1)
    ax.axhline(p50e, color="#444444", ls="--", lw=1)
    ax.set_title("门店规模—相对效率四象限（SKU≥10）")
    ax.set_xlabel("单店日均归一化销量指数（规模轴）")
    ax.set_ylabel("Huber 残差（相对效率轴）")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.25)
    _save(fig, "f5_quadrant.png")


def fig_threshold(sens: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    x = np.arange(len(sens))
    width = 0.2
    for i, (q, c) in enumerate([("q1", "#08519c"), ("q2", "#d94801"), ("q3", "#238b45"), ("q4", "#807dba")]):
        axes[0].bar(x + (i - 1.5) * width, sens[q], width=width, label=q.upper(), color=c)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([f"≥{t}" for t in sens["min_sku"]])
    axes[0].set_title("不同 SKU 门槛下四象限门店数")
    axes[0].set_xlabel("SKU 门槛")
    axes[0].set_ylabel("门店数")
    axes[0].legend(frameon=False, fontsize=7, ncol=2)
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].plot(sens["min_sku"], sens["same_quadrant_share_vs_main"] * 100, marker="o", color="#08519c")
    axes[1].set_title("与主分析（≥10）象限归属一致率")
    axes[1].set_xlabel("SKU 门槛")
    axes[1].set_ylabel("一致率（%）")
    axes[1].set_ylim(0, 100)
    axes[1].grid(alpha=0.25)
    _save(fig, "f6_threshold_sensitivity.png")


def fig_profile(prof: pd.DataFrame) -> None:
    metrics = [("per_day_index_median", "单店日均"), ("per_sku_day_index_median", "单 SKU 日均"),
               ("sku_count_median", "SKU 覆盖数"), ("zero_rate_median", "零销率"),
               ("stockout_hour_rate_median", "小时槽位缺货率"), ("cv_median", "销量 CV")]
    fig, axes = plt.subplots(2, 3, figsize=(14, 7))
    for ax, (col, title) in zip(axes.ravel(), metrics):
        ax.bar(prof["quadrant"], prof[col], color="#6baed6")
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=25, labelsize=7)
        ax.grid(axis="y", alpha=0.25)
    _save(fig, "f7_quadrant_profile.png")


def fig_typical(df: pd.DataFrame, typical: pd.DataFrame, store_day: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 6), sharex=True)
    for ax, (_, r) in zip(axes.ravel(), typical.iterrows()):
        g = store_day[store_day["store_id"] == r["store_id"]].sort_values("dt")
        ax.plot(pd.to_datetime(g["dt"]), g["sales_index"], color="#08519c", lw=1.2)
        ax.set_title(f"{r['quadrant']}｜S{int(r['store_id']):04d}（C{int(r['city_id']):02d}）")
        ax.set_ylabel("日销量指数")
        ax.grid(alpha=0.25)
    for ax in axes[-1]:
        ax.set_xlabel("日期")
    _save(fig, "f8_typical_stores.png")


def fig_influence(df: pd.DataFrame, ols: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    axes[0].scatter(df["eff_resid"], df["rlm_weight"], s=10, alpha=0.5, color="#6baed6")
    axes[0].axhline(WEIGHT_FLAG, color="#d62728", ls="--", lw=1)
    axes[0].set_title("Huber 权重 vs 残差")
    axes[0].set_xlabel("稳健残差")
    axes[0].set_ylabel("RLM 权重")
    axes[0].grid(alpha=0.25)
    axes[1].scatter(np.arange(len(ols["cooks"])), ols["cooks"], s=10, alpha=0.5, color="#fd8d3c")
    axes[1].set_title("OLS Cook's D（参考诊断）")
    axes[1].set_xlabel("门店序号")
    axes[1].set_ylabel("Cook's D")
    axes[1].grid(alpha=0.25)
    _save(fig, "a1_influence_diagnostics.png")


def fig_ols_compare(df: pd.DataFrame, fit: dict, ols: dict) -> None:
    xx = np.linspace(df["x"].min(), df["x"].max(), 100)
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.scatter(df["x"], df["y"], s=10, alpha=0.35, color="#9ecae1")
    ax.plot(xx, fit["result"].params[0] + fit["result"].params[1] * xx,
            color="#d62728", lw=2, label="Huber RLM")
    ax.plot(xx, ols["result"].params[0] + ols["result"].params[1] * xx,
            color="#08519c", lw=1.5, ls="--", label="OLS")
    ax.set_title("Huber RLM 与 OLS 拟合对照")
    ax.set_xlabel("log(SKU 覆盖数)")
    ax.set_ylabel("log(1+单 SKU 日均)")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)
    _save(fig, "a2_ols_vs_rlm.png")


# ---------------- 主流程 ----------------

def run() -> dict:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    store = load_store_metrics()
    d = model_frame(store, MIN_SKU)
    fit = fit_rlm(d, norm="huber")
    d = d.copy()
    d["eff_resid"] = fit["resid"]
    d["rlm_weight"] = fit["weights"]
    d["high_influence"] = d["rlm_weight"] < WEIGHT_FLAG
    d["rlm_fitted"] = fit["fitted"]

    binned = binned_residual(fit["fitted"], fit["resid"])
    comp = model_comparison(d, fit)
    ols = fit_ols(d)
    d["ols_hat"] = ols["hat"]
    d["ols_cooks"] = ols["cooks"]

    d, p50s, p50e = assign_quadrants(d, "eff_resid")
    prof = quadrant_profile(d)
    typical = typical_stores(d, "eff_resid")
    sens, trans = threshold_analysis(store, d)

    # 拟合状态：不以单一 R2 硬性降级
    hard = not (fit["ci_low"] > 0 or fit["ci_high"] < 0)
    soft = []
    if fit["r2_corr"] < R2_REF and fit["r2_weighted"] < R2_REF:
        soft.append("both_r2_below_0.10")
    if binned["max_abs_bin_mean"] > 0.10:
        soft.append("binned_residual_gt_0.10")
    if abs(fit["slope"] - ols["slope"]) > 0.5 * abs(fit["slope"]):
        soft.append("ols_slope_diff_gt_50pct")
    if d["high_influence"].mean() > 0.05:
        soft.append("high_influence_gt_5pct")
    if len(set(np.sign(sens["slope"]))) > 1:
        soft.append("slope_sign_unstable")
    if (sens["same_quadrant_share_vs_main"] < 0.80).any():
        soft.append("quadrant_instability_gt_20pct")
    downgrade = hard or len(soft) >= 2
    caution = []
    if fit["r2_corr"] < R2_REF:
        caution.append("low_corr2")
    if d["high_influence"].mean() > 0.05:
        caution.append("high_influence_gt_5pct")
    if abs(fit["slope"] - ols["slope"]) > 0.3 * abs(fit["slope"]):
        caution.append("ols_slope_diff_gt_30pct")
    if comp.loc[comp["model"] == "RLM-Huber + City FE", "resid_corr_with_main"].iloc[0] < 0.80:
        caution.append("city_fe_changes_residual")

    # 输出门店表：全部门店保留；<10 门店象限为空
    out = store.merge(
        d[["store_id", "eff_resid", "rlm_weight", "high_influence", "quadrant",
           "rlm_fitted", "ols_hat", "ols_cooks"]],
        on="store_id", how="left"
    )
    out["in_model"] = out["sku_count"] >= MIN_SKU
    out["quadrant"] = out["quadrant"].fillna("不参与（SKU<10）")
    out.to_csv(OUT_TABLES / "b1_store_metrics.csv", index=False, encoding="utf-8-sig")
    comp.to_csv(OUT_TABLES / "b2_model_comparison.csv", index=False, encoding="utf-8-sig")
    sens.to_csv(OUT_TABLES / "b3_threshold_sensitivity.csv", index=False, encoding="utf-8-sig")
    trans.to_csv(OUT_TABLES / "b4_quadrant_transition.csv", index=False, encoding="utf-8-sig")
    prof.to_csv(OUT_TABLES / "b5_quadrant_profile.csv", index=False, encoding="utf-8-sig")
    typical.to_csv(OUT_TABLES / "b6_typical_stores.csv", index=False, encoding="utf-8-sig")
    infl = d.nlargest(20, "ols_cooks")[["store_id", "city_id", "sku_count", "per_day_index",
                                        "per_sku_day_index", "eff_resid", "rlm_weight",
                                        "ols_hat", "ols_cooks"]]
    infl.to_csv(OUT_TABLES / "b7_top_influence.csv", index=False, encoding="utf-8-sig")

    summary = {
        "min_sku": MIN_SKU,
        "n_stores_total": int(len(store)),
        "n_stores_model": int(len(d)),
        "n_excluded_lt10": int((store["sku_count"] < MIN_SKU).sum()),
        "model": {
            "slope": fit["slope"], "ci_low": fit["ci_low"], "ci_high": fit["ci_high"],
            "r2_corr": fit["r2_corr"], "r2_weighted": fit["r2_weighted"],
            "resid_mad": fit["resid_mad"], "binned_max_abs": binned["max_abs_bin_mean"],
            "high_influence_count": int(d["high_influence"].sum()),
            "high_influence_share": float(d["high_influence"].mean()),
            "p50_scale": p50s, "p50_eff": p50e,
            "fit_status": "downgraded" if downgrade else ("ok_with_caution" if caution else "ok"),
            "fit_reasons": (["slope_ci_includes_zero"] if hard else []) + soft,
            "caution_flags": caution,
        },
        "model_comparison": comp.to_dict("records"),
        "quadrant_counts": d["quadrant"].value_counts().to_dict(),
        "threshold_sensitivity": sens.to_dict("records"),
        "quadrant_profile": prof.to_dict("records"),
        "typical_stores": typical.to_dict("records"),
        "axis_note": "效率轴为 log(1+单SKU日均) 对 log(SKU覆盖数) 的 Huber RLM 残差；仅表示相对统计预期的偏离，不是因果或管理能力。",
    }
    with open(OUT_TABLES / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    sd = pd.read_parquet(STORE_DAY)
    sd["dt"] = pd.to_datetime(sd["dt"])
    fig_scale_dist(store, p50s)
    fig_sku_scale(store)
    xx = np.linspace(d["x"].min(), d["x"].max(), 100)
    fig_sku_efficiency(store, xx, fit["result"].params[0] + fit["result"].params[1] * xx)
    fig_diagnostics(d, fit, binned)
    fig_quadrant(d, p50s, p50e)
    fig_threshold(sens)
    fig_profile(prof)
    fig_typical(d, typical, sd)
    fig_influence(d, ols)
    fig_ols_compare(d, fit, ols)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
