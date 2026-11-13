"""P3-D：缺货与门店风险分析（仅 train，复用已验收门店指标）。"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
P3C = ROOT / "data" / "analysis" / "p3c"
P3B = ROOT / "data" / "analysis" / "p3b" / "b1_store_metrics.csv"
AGG_STORE_DAY = ROOT / "data" / "derived" / "agg_store_day.parquet"
OUT = ROOT / "data" / "analysis" / "p3d"
FIGS = ROOT / "reports" / "figures" / "p3d"

SEED = 42
BOOT_N = 1000
MIN_SKU = 10

RISK_COLS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]


def equal_size_groups(df: pd.DataFrame, k: int, name: str) -> pd.Series:
    """确定性等样本量分组：按 sku_count、store_id 升序后 np.array_split。"""
    order = df.sort_values(["sku_count", "store_id"], kind="mergesort").index.to_numpy()
    out = pd.Series(index=df.index, dtype=int)
    for i, idx in enumerate(np.array_split(order, k), start=1):
        out.loc[idx] = i
    return out.rename(name)


def low_run_table() -> pd.DataFrame:
    """按 P1 原规则复算真实最长连续低销天数（不截断 1–6 天）。

    P1 `sustained_low` 只把 ≥7 天的门店写入 t11，P3-B 合并时对缺失门店填 0，
    导致 c1 的 `max_low_run_days` 对真实 1–6 天的门店为 0。此处独立复算真实值，
    仅作为 P3-D 派生字段，不修改 P1/P3-B/P3-C 文件。
    """
    sd = pd.read_parquet(AGG_STORE_DAY)
    rows = []
    for sid, g in sd.groupby("store_id"):
        s = g.sort_values("dt")["sales_index"].reset_index(drop=True)
        base = s.median()
        if base <= 0:
            rows.append({"store_id": int(sid), "low_run_max_days": 0, "low_run_median": np.nan})
            continue
        roll = s.rolling(7, min_periods=7).mean()
        flag = (roll < 0.7 * base).fillna(False).to_numpy()
        best = cur = 0
        for v in flag:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        rows.append({"store_id": int(sid), "low_run_max_days": int(best),
                     "low_run_median": float(base)})
    return pd.DataFrame(rows)


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    c1 = pd.read_csv(P3C / "c1_store_structure.csv")
    c4 = pd.read_csv(P3C / "c4_store_deciles.csv")
    low = low_run_table()
    c1 = c1.merge(low, on="store_id", how="left")
    c1["low_run_max_days"] = c1["low_run_max_days"].fillna(0).astype(int)
    d = c1[c1["structure_valid"]].copy().merge(c4[["store_id", "decile"]], on="store_id", how="left")
    d["quartile"] = equal_size_groups(d, 4, "quartile")
    return c1, d


def thresholds(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows = []
    specs = [
        ("R1", "stockout_sku_day_rate", "P90", 0.90, ">", "缺货广度"),
        ("R2", "stockout_hour_rate", "P90", 0.90, ">", "缺货强度"),
        ("R3", "max_low_run_days", "≥7", 7.0, ">=", "持续低销"),
        ("R4", "zero_rate", "P90", 0.90, ">", "高零销"),
        ("R5", "cv", "P90", 0.90, ">", "高波动"),
        ("R6", "anomaly_rate", "P90", 0.90, ">", "高异常日"),
        ("R7", "sku_count", "P10", 0.10, "<=", "覆盖偏窄"),
    ]
    for code, col, label, q, comp, dimension in specs:
        if label == "≥7":
            th = 7.0
        elif comp == "<=":
            th = float(d[col].quantile(q))
        else:
            th = float(d[col].quantile(q))
        hits = int((d[col] >= th).sum()) if comp == ">=" else (
            int((d[col] <= th).sum()) if comp == "<=" else int((d[col] > th).sum())
        )
        rows.append({"flag": code, "dimension": dimension, "metric": col,
                     "threshold_label": label, "threshold": th,
                     "comparator": comp, "n_sample": len(d), "hits": hits})

    # R8：同 SKU 十分位内 P90，逐十分位记录
    for dec, g in d.groupby("decile", observed=True):
        th = float(g["sku_hhi"].quantile(0.90))
        rows.append({"flag": "R8", "dimension": "结构集中", "metric": "sku_hhi",
                     "threshold_label": f"decile{int(dec)}_P90", "threshold": th,
                     "comparator": ">", "n_sample": len(g),
                     "hits": int((g["sku_hhi"] > th).sum())})
    tbl = pd.DataFrame(rows)
    summary = {
        "R1": float(tbl.loc[tbl.flag == "R1", "threshold"].iloc[0]),
        "R2": float(tbl.loc[tbl.flag == "R2", "threshold"].iloc[0]),
        "R4": float(tbl.loc[tbl.flag == "R4", "threshold"].iloc[0]),
        "R5": float(tbl.loc[tbl.flag == "R5", "threshold"].iloc[0]),
        "R6": float(tbl.loc[tbl.flag == "R6", "threshold"].iloc[0]),
        "R7": float(tbl.loc[tbl.flag == "R7", "threshold"].iloc[0]),
    }
    return tbl, summary


def add_flags(d: pd.DataFrame, th: dict) -> pd.DataFrame:
    d = d.copy()
    d["R1"] = d["stockout_sku_day_rate"] > th["R1"]
    d["R2"] = d["stockout_hour_rate"] > th["R2"]
    d["R3"] = d["max_low_run_days"] >= 7
    d["R4"] = d["zero_rate"] > th["R4"]
    d["R5"] = d["cv"] > th["R5"]
    d["R6"] = d["anomaly_rate"] > th["R6"]
    d["R7"] = d["sku_count"] <= th["R7"]
    d["R8"] = d.groupby("decile")["sku_hhi"].transform(lambda s: s > s.quantile(0.90))
    d["stockout_domain"] = d["R1"] | d["R2"]
    domains = ["stockout_domain", "R3", "R4", "R5", "R6"]
    d["domain_count"] = d[domains].sum(axis=1).astype(int)
    d["multi_risk"] = d["domain_count"] >= 2
    return d


def _spearman_ci(x, y, groups=None, store_ids=None, n_boot=BOOT_N, seed=SEED):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    mask = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[mask], y[mask]
    groups_arr = np.asarray(groups)[mask] if groups is not None else None
    if store_ids is not None:
        sid = np.asarray(store_ids)[mask]
        order = np.argsort(sid, kind="mergesort")
        x, y = x[order], y[order]
        if groups_arr is not None:
            groups_arr = groups_arr[order]
    if len(x) < 4:
        return np.nan, np.nan, np.nan, len(x)
    rho = float(pd.Series(x).corr(pd.Series(y), method="spearman"))
    rng = np.random.default_rng(seed)
    vals = []
    if groups_arr is None:
        for _ in range(n_boot):
            idx = rng.integers(0, len(x), len(x))
            r = pd.Series(x[idx]).corr(pd.Series(y[idx]), method="spearman")
            if not np.isnan(r):
                vals.append(r)
    else:
        uniq = np.unique(groups_arr)
        for _ in range(n_boot):
            pick = rng.choice(uniq, len(uniq), replace=True)
            idx = np.concatenate([np.where(groups_arr == k)[0] for k in pick])
            r = pd.Series(x[idx]).corr(pd.Series(y[idx]), method="spearman")
            if not np.isnan(r):
                vals.append(r)
    lo, hi = (np.nanpercentile(vals, [2.5, 97.5]) if vals else (np.nan, np.nan))
    return rho, float(lo), float(hi), len(x)


def relations(d: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("r1_vs_r2", "stockout_sku_day_rate", "stockout_hour_rate"),
        ("r1_vs_per_day", "stockout_sku_day_rate", "per_day_index"),
        ("r2_vs_per_day", "stockout_hour_rate", "per_day_index"),
        ("r1_vs_zero", "stockout_sku_day_rate", "zero_rate"),
        ("r2_vs_zero", "stockout_hour_rate", "zero_rate"),
        ("r1_vs_cv", "stockout_sku_day_rate", "cv"),
        ("r2_vs_cv", "stockout_hour_rate", "cv"),
        ("r1_vs_sku", "stockout_sku_day_rate", "sku_count"),
        ("r2_vs_sku", "stockout_hour_rate", "sku_count"),
        ("r1_vs_eff", "stockout_sku_day_rate", "eff_resid"),
        ("r2_vs_eff", "stockout_hour_rate", "eff_resid"),
        ("r1_vs_low", "stockout_sku_day_rate", "low_run_max_days"),
        ("r2_vs_low", "stockout_hour_rate", "low_run_max_days"),
    ]
    rows = []
    for name, a, b in pairs:
        r, lo, hi, n = _spearman_ci(d[a], d[b], store_ids=d["store_id"])
        rc, loc, hic, _ = _spearman_ci(d[a], d[b], groups=d["city_id"], store_ids=d["store_id"])
        rows.append({"relation": name, "x": a, "y": b, "n": n,
                     "spearman": r, "ci_low": lo, "ci_high": hi,
                     "city_boot_low": loc, "city_boot_high": hic})
    return pd.DataFrame(rows)


def within_deciles(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    pairs = [("r1_per_day", "stockout_sku_day_rate", "per_day_index"),
             ("r2_per_day", "stockout_hour_rate", "per_day_index"),
             ("r1_zero", "stockout_sku_day_rate", "zero_rate"),
             ("r2_zero", "stockout_hour_rate", "zero_rate")]
    for stratum, col, min_n in [("decile", "decile", 20), ("quartile", "quartile", 20)]:
        for grp, g in d.groupby(col, observed=True):
            for name, a, b in pairs:
                rho = np.nan
                if len(g) >= min_n and g[a].nunique() > 1 and g[b].nunique() > 1:
                    rho = float(g[a].corr(g[b], method="spearman"))
                rows.append({"stratum": stratum, "group": int(grp), "n": len(g),
                             "relation": name, "spearman": rho})
    return pd.DataFrame(rows)


def flag_cross(d: pd.DataFrame) -> pd.DataFrame:
    """R1 × R2 命中 2×2 交叉，披露交集/并集。"""
    rows = []
    for a in [True, False]:
        for b in [True, False]:
            rows.append({"R1": a, "R2": b,
                         "stores": int(((d.R1 == a) & (d.R2 == b)).sum())})
    return pd.DataFrame(rows)


def city_table(c1: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for city, g in d.groupby("city_id", observed=True):
        allg = c1[c1["city_id"] == city]
        w = allg["observed_rows"].sum()
        rows.append({
            "city_id": int(city),
            "stores_all": len(allg), "stores_risk": len(g),
            "small_city": len(allg) < 10,
            "stockout_sku_day_pooled": float((allg["stockout_sku_day_rate"] * allg["observed_rows"]).sum() / w),
            "stockout_hour_pooled": float((allg["stockout_hour_rate"] * allg["observed_rows"]).sum() / w),
            "stockout_sku_day_median": float(g["stockout_sku_day_rate"].median()),
            "stockout_sku_day_q1": float(g["stockout_sku_day_rate"].quantile(0.25)),
            "stockout_sku_day_q3": float(g["stockout_sku_day_rate"].quantile(0.75)),
            "stockout_hour_median": float(g["stockout_hour_rate"].median()),
            "stockout_hour_q1": float(g["stockout_hour_rate"].quantile(0.25)),
            "stockout_hour_q3": float(g["stockout_hour_rate"].quantile(0.75)),
            "zero_median": float(g["zero_rate"].median()),
            "multi_risk": int(g["multi_risk"].sum()),
            "multi_risk_rate_risk": float(g["multi_risk"].mean()),
            "multi_risk_rate_all": float(g["multi_risk"].sum() / len(allg)),
        })
    return pd.DataFrame(rows).sort_values("city_id").reset_index(drop=True)


def quadrant_table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for q, g in d.groupby("quadrant", observed=True):
        row = {"quadrant": q, "stores": len(g),
               "multi_risk": int(g["multi_risk"].sum()),
               "multi_risk_rate": float(g["multi_risk"].mean())}
        for f in ["R1", "R2", "R3", "R4", "R5", "R6"]:
            row[f"{f}_rate"] = float(g[f].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def structure_table(d: pd.DataFrame) -> pd.DataFrame:
    c8 = pd.read_csv(P3C / "c8_cluster_assignments.csv")
    x = d.merge(c8[["store_id", "cluster_k4"]], on="store_id", how="left")
    rows = []
    for cl, g in x.groupby("cluster_k4", observed=True):
        rows.append({"cluster": f"G{int(cl)}", "stores": len(g),
                     "R7_rate": float(g["R7"].mean()), "R8_rate": float(g["R8"].mean()),
                     "multi_risk_rate": float(g["multi_risk"].mean()),
                     "stockout_sku_day_median": float(g["stockout_sku_day_rate"].median()),
                     "stockout_hour_median": float(g["stockout_hour_rate"].median())})
    return pd.DataFrame(rows)


def cooccurrence(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    domains = ["stockout_domain", "R3", "R4", "R5", "R6"]
    labels = ["缺货", "持续低销", "高零销", "高波动", "高异常日"]
    mat = pd.DataFrame(0, index=labels, columns=labels, dtype=int)
    for i, a in enumerate(domains):
        for j, b in enumerate(domains):
            mat.iloc[i, j] = int((d[a] & d[b]).sum())

    pair_rows = []
    for i, a in enumerate(domains):
        for j, b in enumerate(domains):
            if j < i:
                continue
            pair_rows.append({
                "domain_a": labels[i], "domain_b": labels[j],
                "stores_at_least": int((d[a] & d[b]).sum()),
                "definition": ("命中该域" if i == j else "至少同时命中这两个域（允许其他域）"),
            })
    pair = pd.DataFrame(pair_rows)

    dist = d["domain_count"].value_counts().sort_index().rename_axis("domain_count").reset_index(name="stores")

    d = d.copy()
    d["combo"] = d.apply(
        lambda row: "+".join([lab for k, lab in zip(domains, labels) if bool(row[k])]), axis=1
    )
    exact = (d[d.domain_count >= 2].groupby("combo").size()
             .rename("stores").reset_index().rename(columns={"combo": "combination"}))
    exact["rank"] = exact["stores"].rank(method="min", ascending=False).astype(int)
    exact["definition"] = "恰好只命中这些域"
    top = exact[exact["rank"] <= 10].sort_values(
        ["rank", "stores", "combination"], ascending=[True, False, True]).reset_index(drop=True)
    return mat, pair, dist, top


def sensitivity(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = [("R1", "stockout_sku_day_rate"), ("R2", "stockout_hour_rate"),
               ("R4", "zero_rate"), ("R5", "cv"), ("R6", "anomaly_rate")]
    for q in [0.85, 0.90, 0.95]:
        for code, col in metrics:
            th = float(d[col].quantile(q))
            rows.append({"sensitivity": f"{code}_P{int(q*100)}", "metric": col,
                         "threshold": th, "hits": int((d[col] > th).sum())})
    for q in [0.05, 0.10, 0.15]:
        th = float(d["sku_count"].quantile(q))
        rows.append({"sensitivity": f"R7_P{int(q*100)}", "metric": "sku_count",
                     "threshold": th, "hits": int((d["sku_count"] <= th).sum())})
    p90 = float(d["anomaly_rate"].quantile(.9))
    rows.append({"sensitivity": "R6_ge_P90", "metric": "anomaly_rate",
                 "threshold": p90, "hits": int((d["anomaly_rate"] >= p90).sum())})
    for nmin in [5, 20, 30]:
        s = d[d["sku_count"] >= nmin]
        for code, col in metrics:
            th = float(s[col].quantile(.9))
            rows.append({"sensitivity": f"minSKU{nmin}_{code}_P90", "metric": col,
                         "threshold": th, "hits": int((s[col] > th).sum())})
    # R8 全局 P90 对照
    th = float(d["sku_hhi"].quantile(.9))
    rows.append({"sensitivity": "R8_global_P90", "metric": "sku_hhi",
                 "threshold": th, "hits": int((d["sku_hhi"] > th).sum())})
    # 城市内 P90：每个城市各自取 P90，命中数按城市加总
    for code, col in metrics:
        hits = 0
        for _, g in d.groupby("city_id", observed=True):
            th = float(g[col].quantile(.9))
            hits += int((g[col] > th).sum())
        rows.append({"sensitivity": f"city_within_{code}_P90", "metric": col,
                     "threshold": np.nan, "hits": hits})
    # 剔除 City 0：两种方案分开披露
    non0 = d[d["city_id"] != 0]
    orig = {code: float(d[col].quantile(.9)) for code, col in metrics}
    for code, col in metrics:
        rows.append({"sensitivity": f"exclude_city0_original_thresholds_{code}",
                     "metric": col, "threshold": orig[code],
                     "hits": int((non0[col] > orig[code]).sum())})
    rows.append({"sensitivity": "exclude_city0_original_thresholds_multi",
                 "metric": "domain_count>=2", "threshold": np.nan,
                 "hits": int(non0["multi_risk"].sum())})

    new_th = {code: float(non0[col].quantile(.9)) for code, col in metrics}
    b = non0.copy()
    b["B1"] = b["stockout_sku_day_rate"] > new_th["R1"]
    b["B2"] = b["stockout_hour_rate"] > new_th["R2"]
    b["B4"] = b["zero_rate"] > new_th["R4"]
    b["B5"] = b["cv"] > new_th["R5"]
    b["B6"] = b["anomaly_rate"] > new_th["R6"]
    b["B_domain"] = (b["B1"] | b["B2"]).astype(int) + b["R3"].astype(int) + \
                    b["B4"].astype(int) + b["B5"].astype(int) + b["B6"].astype(int)
    for code, col in metrics:
        rows.append({"sensitivity": f"exclude_city0_recomputed_thresholds_{code}",
                     "metric": col, "threshold": new_th[code],
                     "hits": int((non0[col] > new_th[code]).sum())})
    rows.append({"sensitivity": "exclude_city0_recomputed_thresholds_multi",
                 "metric": "domain_count>=2", "threshold": np.nan,
                 "hits": int((b["B_domain"] >= 2).sum())})
    return pd.DataFrame(rows)


def overall_rates(c1: pd.DataFrame) -> pd.DataFrame:
    """全样本池化缺货率：分子合计 / 分母合计。"""
    obs = c1["observed_rows"].astype(float)
    num1 = float((c1["stockout_sku_day_rate"] * obs).sum())
    num2 = float((c1["stockout_hour_rate"] * obs).sum())
    den = float(obs.sum())
    return pd.DataFrame([
        {"metric": "SKU-日缺货率（全样本池化）", "numerator": num1, "denominator": den,
         "rate": num1 / den, "formula": "Σ(有缺货 SKU-日) / Σ(有效 SKU-日)"},
        {"metric": "小时槽位缺货率（全样本池化）", "numerator": num2 * 16.0,
         "denominator": 16.0 * den, "rate": num2 / den,
         "formula": "Σ(缺货小时) / (16 × Σ有效 SKU-日)"},
    ])


def decomposition(d: pd.DataFrame) -> dict:
    """R2 = R1 × (每个缺货 SKU-日的平均缺货小时 / 16)。"""
    r1 = d["stockout_sku_day_rate"].to_numpy(float)
    r2 = d["stockout_hour_rate"].to_numpy(float)
    intensity = np.where(r1 > 0, 16.0 * r2 / r1, np.nan)
    identity = np.where(r1 > 0, r1 * intensity / 16.0, 0.0)
    return {
        "identity_max_abs_diff": float(np.nanmax(np.abs(identity - np.where(r1 > 0, r2, 0.0)))),
        "intensity_median_hours": float(np.nanmedian(intensity)),
        "spearman_intensity_vs_sku": float(pd.Series(intensity).corr(d["sku_count"], method="spearman")),
        "spearman_intensity_vs_zero": float(pd.Series(intensity).corr(d["zero_rate"], method="spearman")),
        "spearman_intensity_vs_per_day": float(pd.Series(intensity).corr(d["per_day_index"], method="spearman")),
        "note": "恒等式为数学关系；强度与 SKU/零销的关系仅为样本统计关联",
    }


def city_boot_sizes(groups, n_boot: int = BOOT_N, seed: int = SEED) -> dict:
    """复现城市 Cluster Bootstrap 的抽样门店数（不改动 Bootstrap 结果）。"""
    g = np.asarray(groups)
    uniq = np.unique(g)
    rng = np.random.default_rng(seed)
    sizes = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, len(uniq), replace=True)
        sizes.append(int(sum(int((g == k).sum()) for k in pick)))
    return {"min": int(np.min(sizes)), "max": int(np.max(sizes)),
            "median": float(np.median(sizes)), "n_cities": int(len(uniq)),
            "n_boot": int(n_boot), "seed": int(seed)}


def typical_stores(d: pd.DataFrame) -> pd.DataFrame:
    feats = ["stockout_sku_day_rate", "stockout_hour_rate", "zero_rate", "cv", "per_day_index"]
    z = d.copy()
    for c in feats:
        z[c + "_z"] = (z[c] - z[c].mean()) / z[c].std(ddof=0)
    z["group"] = np.select(
        [z.domain_count == 0, z.domain_count == 1, z.domain_count == 2],
        ["0域", "1域", "2域"], default="≥3域"
    )
    rows = []
    for gname, g in z.groupby("group", observed=True):
        center = g[[c + "_z" for c in feats]].mean()
        dist = np.sqrt(((g[[c + "_z" for c in feats]] - center) ** 2).sum(axis=1))
        cand = pd.DataFrame({"store_id": z.loc[dist.index, "store_id"].to_numpy(),
                             "distance": dist.to_numpy()}, index=dist.index)
        idx = int(cand.sort_values(["distance", "store_id"], kind="mergesort").index[0])
        r = z.loc[idx]
        row = {"group": gname, "stores_in_group": len(g), "store_id": int(r.store_id),
               "city_id": int(r.city_id), "domain_count": int(r.domain_count),
               "distance": float(dist.loc[idx])}
        row.update({c: float(r[c]) for c in feats})
        row.update({f: int(r[f]) for f in RISK_COLS})
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------- 图表 ----------------

def save(fig, name):
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_f1(d, th):
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    sc = ax.scatter(d.stockout_sku_day_rate, d.stockout_hour_rate, c=d.decile, cmap="viridis", s=14, alpha=.7)
    ax.axvline(th["R1"], color="#d62728", ls="--", lw=1)
    ax.axhline(th["R2"], color="#d62728", ls="--", lw=1)
    ax.set_title("两种缺货口径：SKU-日 vs 小时槽位（888 家）")
    ax.set_xlabel("SKU-日缺货率（至少 1 个缺货小时）")
    ax.set_ylabel("小时槽位缺货率（16 槽位）")
    fig.colorbar(sc, ax=ax).set_label("SKU 十分位")
    ax.grid(alpha=.25)
    save(fig, "f1_two_stockout_metrics.png")


def fig_f2(d, th):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, col, t, name in [(axes[0], "stockout_sku_day_rate", th["R1"], "SKU-日缺货率"),
                             (axes[1], "stockout_hour_rate", th["R2"], "小时槽位缺货率")]:
        ax.hist(d[col], bins=35, color="#9ecae1", edgecolor="white")
        ax.axvline(t, color="#d62728", ls="--", lw=1.1)
        ax.set_title(f"{name}分布（虚线=P90）")
        ax.set_xlabel(name); ax.set_ylabel("门店数"); ax.grid(axis="y", alpha=.25)
    save(fig, "f2_stockout_distributions.png")


def fig_f3(d, th):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, col, name in [(axes[0], "stockout_sku_day_rate", "SKU-日缺货率"),
                          (axes[1], "stockout_hour_rate", "小时槽位缺货率")]:
        sc = ax.scatter(d[col], d.per_day_index, c=d.decile, cmap="viridis", s=12, alpha=.65)
        ax.set_title(f"{name} vs 单店日均")
        ax.set_xlabel(name); ax.set_ylabel("单店日均销量指数"); ax.grid(alpha=.25)
    save(fig, "f3_stockout_vs_sales.png")


def fig_f4(d, th):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, col, name in [(axes[0], "stockout_sku_day_rate", "SKU-日缺货率"),
                          (axes[1], "stockout_hour_rate", "小时槽位缺货率")]:
        ax.scatter(d[col], d.zero_rate, c=d.decile, cmap="viridis", s=12, alpha=.65)
        ax.set_title(f"{name} vs 零销率")
        ax.set_xlabel(name); ax.set_ylabel("零销率"); ax.grid(alpha=.25)
    save(fig, "f4_stockout_vs_zero.png")


def fig_f5(d):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.4))
    cols = [("stockout_sku_day_rate", "SKU-日缺货率"), ("stockout_hour_rate", "小时槽位缺货率")]
    for j, (col, name) in enumerate(cols):
        ax = axes[0, j]
        ax.scatter(d[col], d.cv, c=d.decile, cmap="viridis", s=12, alpha=.65)
        ax.set_title(f"{name} vs 销量 CV")
        ax.set_xlabel(name); ax.set_ylabel("CV"); ax.grid(alpha=.25)

        ax = axes[1, j]
        ax.scatter(d[col], d.low_run_max_days, c=d.decile, cmap="viridis", s=12, alpha=.65)
        ax.set_title(f"{name} vs 真实最长连续低销天数")
        ax.set_xlabel(name); ax.set_ylabel("最长连续低销天数（P1 规则复算）"); ax.grid(alpha=.25)
    save(fig, "f5_stockout_vs_cv.png")


def fig_f6(city):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, med, q1, q3, name in [
        (axes[0], "stockout_sku_day_median", "stockout_sku_day_q1", "stockout_sku_day_q3", "SKU-日缺货率"),
        (axes[1], "stockout_hour_median", "stockout_hour_q1", "stockout_hour_q3", "小时槽位缺货率")]:
        order = city.sort_values(med)
        colors = ["#d62728" if s else "#4292c6" for s in order.small_city]
        y = np.arange(len(order))
        ax.errorbar(order[med], y, xerr=[order[med] - order[q1], order[q3] - order[med]],
                    fmt="none", ecolor="#999999", elinewidth=1.1, capsize=2)
        ax.scatter(order[med], y, c=colors, s=20, zorder=3)
        ax.set_yticks(y); ax.set_yticklabels([f"C{int(c):02d}" for c in order.city_id], fontsize=7)
        ax.set_title(f"城市{name}中位/IQR（红=小城市）")
        ax.set_xlabel(name); ax.grid(axis="x", alpha=.25)
    save(fig, "f6_city_stockout.png")


def fig_f7(tbl):
    sub = tbl[tbl.flag.isin(["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"])].groupby("flag", as_index=False)["hits"].sum()
    order = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]
    sub["flag"] = pd.Categorical(sub.flag, order, ordered=True); sub = sub.sort_values("flag")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.bar(sub.flag.astype(str), sub.hits, color="#6baed6")
    for i, v in enumerate(sub.hits): ax.text(i, v + 2, str(int(v)), ha="center", fontsize=9)
    ax.set_title("风险标记命中门店数（888 家；R1/R2 均 89）")
    ax.set_ylabel("门店数"); ax.grid(axis="y", alpha=.25)
    save(fig, "f7_risk_flag_counts.png")


def fig_f8(mat):
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    im = ax.imshow(mat.values, cmap="Reds")
    ax.set_xticks(range(len(mat.columns))); ax.set_xticklabels(mat.columns, rotation=25)
    ax.set_yticks(range(len(mat.index))); ax.set_yticklabels(mat.index)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, str(int(mat.iloc[i, j])), ha="center", va="center", fontsize=9,
                    color="white" if mat.iloc[i, j] > mat.values.max()*.6 else "#333333")
    ax.set_title("运营风险域共现门店数（含对角线）")
    fig.colorbar(im, ax=ax).set_label("门店数")
    save(fig, "f8_risk_cooccurrence.png")


def fig_f9(dist):
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    ax.bar(dist.domain_count.astype(str), dist.stores, color="#fd8d3c")
    for i, v in enumerate(dist.stores): ax.text(i, v + 5, str(int(v)), ha="center", fontsize=9)
    ax.set_title("运营风险域数量分布（888 家）")
    ax.set_xlabel("运营风险域数量"); ax.set_ylabel("门店数"); ax.grid(axis="y", alpha=.25)
    save(fig, "f9_domain_count.png")


def fig_f10(q):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(q)); w = .15
    for i, f in enumerate(["R1_rate", "R2_rate", "R3_rate", "R4_rate", "R5_rate", "R6_rate"]):
        ax.bar(x + (i-2.5)*w, q[f]*100, width=w, label=f.replace("_rate", ""))
    ax.set_xticks(x); ax.set_xticklabels([s.replace("·", "\n") for s in q.quadrant], fontsize=7)
    ax.set_ylabel("命中率（%）"); ax.set_title("P3-B 四象限 × 风险标记命中率")
    ax.legend(ncol=6, fontsize=7, frameon=False); ax.grid(axis="y", alpha=.25)
    save(fig, "f10_quadrant_risk.png")


def fig_a1(d):
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.hist(d.store_day_any_stockout_rate, bins=30, color="#bdbdbd", edgecolor="white")
    ax.set_title("门店日任一 SKU 缺货率（饱和，仅附录）")
    ax.set_xlabel("store_day_any_stockout_rate"); ax.set_ylabel("门店数"); ax.grid(axis="y", alpha=.25)
    save(fig, "a1_store_day_any_stockout.png")


def fig_a2(t):
    flags = RISK_COLS
    mat = t[flags].to_numpy(int)
    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    im = ax.imshow(mat, cmap="Reds", aspect="auto")
    ax.set_xticks(range(len(flags))); ax.set_xticklabels(flags)
    ax.set_yticks(range(len(t))); ax.set_yticklabels(t.group, fontsize=8)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, str(mat[i, j]), ha="center", va="center", fontsize=8)
    ax.set_title("典型门店风险标记（规则：风险域组中心最近）")
    fig.colorbar(im, ax=ax).set_label("0/1")
    save(fig, "a2_typical_store_risk.png")


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True); FIGS.mkdir(parents=True, exist_ok=True)
    c1, d = load()
    th_tbl, th = thresholds(d)
    d = add_flags(d, th)

    # 全部门店基础表：风险样本外的 10 家不参与标记，标记留空（NA），不记为 0/False
    base = c1.merge(d[["store_id"] + RISK_COLS + ["stockout_domain", "domain_count", "multi_risk"]],
                    on="store_id", how="left")
    base["in_risk_sample"] = base["store_id"].isin(d["store_id"])
    flag_cols = RISK_COLS + ["stockout_domain", "multi_risk"]
    for f in flag_cols:
        base[f] = base[f].astype("boolean")
    base.loc[~base["in_risk_sample"], flag_cols] = pd.NA
    base["domain_count"] = base["domain_count"].astype("Int64")
    base.loc[~base["in_risk_sample"], "domain_count"] = pd.NA

    rel = relations(d)
    cross = flag_cross(d)
    dec = within_deciles(d)
    city = city_table(c1, d)
    quad = quadrant_table(d)
    struct = structure_table(d)
    mat, pair, dist, top = cooccurrence(d)
    sens = sensitivity(d)
    typ = typical_stores(d)
    overall = overall_rates(c1)
    decomp = decomposition(d)
    boot_sizes = city_boot_sizes(d["city_id"])

    base.to_csv(OUT / "d1_store_risk_base.csv", index=False, encoding="utf-8-sig")
    th_tbl.to_csv(OUT / "d2_thresholds.csv", index=False, encoding="utf-8-sig")
    rel.to_csv(OUT / "d3_stockout_relations.csv", index=False, encoding="utf-8-sig")
    cross.to_csv(OUT / "d3b_stockout_flag_cross.csv", index=False, encoding="utf-8-sig")
    dec.to_csv(OUT / "d4_within_decile_relations.csv", index=False, encoding="utf-8-sig")
    city.to_csv(OUT / "d5_city_risk.csv", index=False, encoding="utf-8-sig")
    quad.to_csv(OUT / "d6_quadrant_risk.csv", index=False, encoding="utf-8-sig")
    struct.to_csv(OUT / "d7_structure_risk.csv", index=False, encoding="utf-8-sig")
    mat.to_csv(OUT / "d8_cooccurrence_matrix.csv", encoding="utf-8-sig")
    pair.to_csv(OUT / "d8b_pairwise_combinations.csv", index=False, encoding="utf-8-sig")
    dist.to_csv(OUT / "d9_domain_count.csv", index=False, encoding="utf-8-sig")
    top.to_csv(OUT / "d10_top_combinations.csv", index=False, encoding="utf-8-sig")
    sens.to_csv(OUT / "d11_sensitivity.csv", index=False, encoding="utf-8-sig")
    typ.to_csv(OUT / "d12_typical_stores.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(OUT / "d13_overall_rates.csv", index=False, encoding="utf-8-sig")

    low_summary = {
        "risk_true_0": int((d["low_run_max_days"] == 0).sum()),
        "risk_true_1_6": int(d["low_run_max_days"].between(1, 6).sum()),
        "risk_true_ge7": int((d["low_run_max_days"] >= 7).sum()),
        "p1_field_zero_but_true_1_6": int(((d["max_low_run_days"] == 0) &
                                           d["low_run_max_days"].between(1, 6)).sum()),
        "r3_hits": int(d["R3"].sum()),
        "r3_matches_true_ge7": bool((d["R3"] == (d["low_run_max_days"] >= 7)).all()),
    }
    city0 = sens[sens["sensitivity"].str.startswith("exclude_city0_")].to_dict("records")

    summary = {
        "n_all": len(base), "n_risk": len(d),
        "risk_sample_rule": "SKU coverage >= 10 (structure_valid=True)",
        "thresholds": th,
        "threshold_table": th_tbl.to_dict("records"),
        "flag_counts": {f: int(d[f].sum()) for f in RISK_COLS},
        "domain_counts": dist.to_dict("records"),
        "multi_risk": int(d.multi_risk.sum()), "multi_risk_rate": float(d.multi_risk.mean()),
        "r1_r2_overlap": int((d.R1 & d.R2).sum()), "r1_r2_union": int((d.R1 | d.R2).sum()),
        "r1_r2_cross": cross.to_dict("records"),
        "relations": rel.to_dict("records"),
        "within_decile": dec.to_dict("records"),
        "overall_rates": overall.to_dict("records"),
        "decomposition": decomp,
        "low_run": low_summary,
        "city_range": {"sku_day_median_min": float(city.stockout_sku_day_median.min()),
                       "sku_day_median_max": float(city.stockout_sku_day_median.max()),
                       "hour_median_min": float(city.stockout_hour_median.min()),
                       "hour_median_max": float(city.stockout_hour_median.max())},
        "quadrant": quad.to_dict("records"),
        "structure": struct.to_dict("records"),
        "top_combinations": top.to_dict("records"),
        "combination_definitions": {
            "at_least": "d8b_pairwise_combinations.csv：同时命中两个域，允许其他域",
            "exact": "d10_top_combinations.csv：恰好只命中该组合，rank 并列时全部列出",
        },
        "city0_exclusion": city0,
        "typical": typ.to_dict("records"),
        "bootstrap": {"seed": SEED, "n_boot": BOOT_N, "store_n": 888,
                      "city_n": 18, "city_sample": boot_sizes,
                      "method": "percentile 2.5/97.5; store_id sorted before resampling"},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    fig_f1(d, th); fig_f2(d, th); fig_f3(d, th); fig_f4(d, th); fig_f5(d)
    fig_f6(city); fig_f7(th_tbl); fig_f8(mat); fig_f9(dist); fig_f10(quad)
    fig_a1(d); fig_a2(typ)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str)[:6000])
