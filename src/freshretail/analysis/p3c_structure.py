"""P3-C：门店商品结构分析（仅 train）。"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import pdist
from sklearn.metrics import adjusted_rand_score

matplotlib.use("Agg")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
DERIVED = ROOT / "data" / "derived"
CLEAN = DERIVED / "clean_train.parquet"
P3B = ROOT / "data" / "analysis" / "p3b" / "b1_store_metrics.csv"
MAP_L1 = ROOT / "data" / "analysis" / "p2" / "map_l1.csv"

OUT_TABLES = ROOT / "data" / "analysis" / "p3c"
OUT_FIGS = ROOT / "reports" / "figures" / "p3c"

MIN_SKU = 10
SEED = 42
RARE_STORES = 10
BOOT_N = 1000
K_DISPLAY = 4


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW clean AS SELECT * FROM read_parquet('{CLEAN.as_posix()}')")
    return con


# ---------------- 结构指标 ----------------

def store_sku_structure(con) -> pd.DataFrame:
    return con.execute("""
        WITH s AS (
            SELECT store_id, product_id, SUM(sales_index) AS idx
            FROM clean GROUP BY 1, 2
        ),
        r AS (
            SELECT store_id, product_id, idx,
                   SUM(idx) OVER (PARTITION BY store_id) AS tot,
                   ROW_NUMBER() OVER (PARTITION BY store_id ORDER BY idx DESC) AS rn
            FROM s
        )
        SELECT store_id,
               SUM(POWER(idx / NULLIF(tot, 0), 2)) AS sku_hhi,
               MAX(CASE WHEN rn = 1 THEN idx / NULLIF(tot, 0) END) AS top1_sku_share,
               SUM(CASE WHEN rn <= 5 THEN idx / NULLIF(tot, 0) ELSE 0 END) AS top5_sku_share,
               COUNT(*) AS n_sku
        FROM r GROUP BY 1
    """).df()


def store_category_structure(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    long = con.execute("""
        SELECT store_id, first_category_id, SUM(sales_index) AS idx,
               COUNT(DISTINCT product_id) AS n_sku
        FROM clean GROUP BY 1, 2
    """).df()
    total = long.groupby("store_id")["idx"].transform("sum")
    long["share"] = long["idx"] / total
    agg = long.groupby("store_id").apply(
        lambda g: pd.Series({
            "cat_hhi": float(np.sum(g["share"] ** 2)),
            "cat_entropy": float(-np.sum(g["share"] * np.log(g["share"]))),
            "n_cat": int(len(g)),
            "top_cat_share": float(g["share"].max()),
        }), include_groups=False
    ).reset_index()
    return long, agg


def store_counts(con) -> pd.DataFrame:
    return con.execute("""
        SELECT store_id,
               COUNT(DISTINCT product_id) AS sku_count,
               COUNT(DISTINCT second_category_id) AS n_cat2,
               COUNT(DISTINCT third_category_id) AS n_cat3,
               SUM(sales_index) AS total_index
        FROM clean GROUP BY 1
    """).df()


def category_penetration(con) -> pd.DataFrame:
    d = con.execute("""
        WITH s AS (
            SELECT store_id, first_category_id, SUM(sales_index) AS idx,
                   COUNT(DISTINCT product_id) AS n_sku
            FROM clean GROUP BY 1, 2
        ),
        t AS (SELECT store_id, SUM(idx) AS tot FROM s GROUP BY 1)
        SELECT s.first_category_id AS raw_id,
               COUNT(*) AS stores,
               AVG(s.idx / t.tot) AS avg_share,
               MEDIAN(s.idx / t.tot) AS median_share,
               MEDIAN(s.n_sku) AS median_sku
        FROM s JOIN t USING (store_id)
        GROUP BY 1
    """).df()
    d["coverage"] = d["stores"] / 898
    d = d.merge(pd.read_csv(MAP_L1), on="raw_id", how="left")
    d["rare"] = d["stores"] < RARE_STORES
    return d.sort_values("stores", ascending=False).reset_index(drop=True)


def build_structure() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con = _con()
    b1 = pd.read_csv(P3B)
    sku = store_sku_structure(con)
    long, cat = store_category_structure(con)
    counts = store_counts(con)
    s = (b1.merge(sku, on="store_id", how="left")
           .merge(cat, on="store_id", how="left")
           .merge(counts[["store_id", "n_cat2", "n_cat3"]], on="store_id", how="left"))
    if "total_index_x" in s.columns:
        s = s.rename(columns={"total_index_x": "total_index"}).drop(columns=["total_index_y"], errors="ignore")
    s = s.drop(columns=["product_count", "n_sku"], errors="ignore")
    s["effective_sku"] = 1 / s["sku_hhi"]
    s["structure_valid"] = s["sku_count"] >= MIN_SKU
    return s, long, category_penetration(con)


# ---------------- 十分位 ----------------

def equal_size_deciles(df: pd.DataFrame) -> pd.DataFrame:
    d = df.sort_values(["sku_count", "store_id"], kind="mergesort").reset_index(drop=True)
    groups = np.array_split(np.arange(len(d)), 10)
    d["decile"] = 0
    for i, idx in enumerate(groups, start=1):
        d.loc[idx, "decile"] = i
    return d


def decile_stats(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dec, g in d.groupby("decile", observed=True):
        rho = np.nan
        if len(g) >= 20 and g["sku_hhi"].nunique() > 1:
            rho = float(g["sku_hhi"].corr(g["per_day_index"], method="spearman"))
        rows.append({
            "decile": int(dec), "n": len(g),
            "sku_min": int(g["sku_count"].min()), "sku_max": int(g["sku_count"].max()),
            "hhi_median": float(g["sku_hhi"].median()),
            "hhi_p25": float(g["sku_hhi"].quantile(0.25)),
            "hhi_p75": float(g["sku_hhi"].quantile(0.75)),
            "per_day_median": float(g["per_day_index"].median()),
            "spearman_hhi_per_day": rho,
            "sample_flag": "样本不足" if len(g) < 20 else "",
        })
    return pd.DataFrame(rows)


# ---------------- 相关 ----------------

def _spearman_ci(x, y, groups=None, store_ids=None, n_boot=BOOT_N, seed=SEED):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    mask = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[mask], y[mask]
    groups_arr = np.asarray(groups)[mask] if groups is not None else None
    if store_ids is not None:
        sid = np.asarray(store_ids)[mask]
        # 固定按 store_id 排序，消除 Bootstrap 随机索引对输入行序的依赖
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
            if len(np.unique(idx)) < 4:
                continue
            r = pd.Series(x[idx]).corr(pd.Series(y[idx]), method="spearman")
            if not np.isnan(r):
                vals.append(r)
    else:
        uniq = np.unique(groups_arr)
        for _ in range(n_boot):
            pick = rng.choice(uniq, len(uniq), replace=True)
            idx = np.concatenate([np.where(groups_arr == k)[0] for k in pick])
            if len(np.unique(idx)) < 4:
                continue
            r = pd.Series(x[idx]).corr(pd.Series(y[idx]), method="spearman")
            if not np.isnan(r):
                vals.append(r)
    lo, hi = (np.nanpercentile(vals, [2.5, 97.5]) if vals else (np.nan, np.nan))
    return rho, float(lo), float(hi), len(x)


def correlation_table(d: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("hhi_vs_per_day", "sku_hhi", "per_day_index"),
        ("hhi_vs_per_sku", "sku_hhi", "per_sku_day_index"),
        ("hhi_vs_eff_resid", "sku_hhi", "eff_resid"),
        ("top1_vs_per_sku", "top1_sku_share", "per_sku_day_index"),
        ("cat_count_vs_per_day", "n_cat", "per_day_index"),
        ("cat_hhi_vs_per_day", "cat_hhi", "per_day_index"),
    ]
    rows = []
    for name, a, b in pairs:
        r, lo, hi, n = _spearman_ci(d[a], d[b], store_ids=d["store_id"])
        rc, loc, hic, nc = _spearman_ci(d[a], d[b], groups=d["city_id"], store_ids=d["store_id"])
        rows.append({"relation": name, "x": a, "y": b, "n": n,
                     "spearman": r, "ci_low": lo, "ci_high": hi,
                     "city_boot_low": loc, "city_boot_high": hic})
    return pd.DataFrame(rows)


# ---------------- 相似度与聚类 ----------------

def prepare_vectors(d: pd.DataFrame, long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ids = d["store_id"].tolist()
    p = long[long["store_id"].isin(ids)].pivot_table(
        index="store_id", columns="first_category_id", values="share", aggfunc="sum"
    ).reindex(ids).fillna(0)
    return p, p.div(p.sum(axis=1), axis=0)


def l2_norm(m: pd.DataFrame) -> np.ndarray:
    a = m.to_numpy(float)
    n = np.linalg.norm(a, axis=1, keepdims=True)
    n[n == 0] = 1
    return a / n


def cosine_summary(u: np.ndarray, d: pd.DataFrame) -> dict:
    sim = u @ u.T
    city = d["city_id"].to_numpy()
    same = city[:, None] == city[None, :]
    off = ~np.eye(len(d), dtype=bool)
    within = sim[same & off]
    between = sim[~same & off]
    return {
        "within_city_mean": float(within.mean()), "within_city_median": float(np.median(within)),
        "between_city_mean": float(between.mean()), "between_city_median": float(np.median(between)),
        "diff_mean": float(within.mean() - between.mean()),
    }, sim


def jaccard_sample(d: pd.DataFrame, con) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(SEED)
    picks = []
    for dec, g in d.groupby("decile", observed=True):
        ids = np.sort(g["store_id"].to_numpy())
        take = rng.choice(ids, size=min(10, len(ids)), replace=False)
        picks.extend([(int(x), int(dec)) for x in np.sort(take)])
    sample = pd.DataFrame(picks, columns=["store_id", "decile"])
    ids = sample["store_id"].tolist()
    q = ",".join(str(int(x)) for x in ids)
    presence = con.execute(f"""
        SELECT store_id, product_id, MAX(CASE WHEN sales_index > 0 THEN 1 ELSE 0 END) AS present
        FROM clean WHERE store_id IN ({q}) GROUP BY 1,2
    """).df()
    b = presence.pivot_table(index="store_id", columns="product_id", values="present",
                             aggfunc="max").reindex(ids).fillna(0).to_numpy(float)
    counts = b.sum(axis=1)
    inter = b @ b.T
    union = counts[:, None] + counts[None, :] - inter
    jac = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
    city = sample.merge(d[["store_id", "city_id"]], on="store_id")["city_id"].to_numpy()
    same = city[:, None] == city[None, :]
    off = ~np.eye(len(ids), dtype=bool)
    summary = {
        "n_sample": len(ids),
        "within_city_mean": float(jac[same & off].mean()) if (same & off).any() else np.nan,
        "between_city_mean": float(jac[~same & off].mean()) if (~same & off).any() else np.nan,
        "median": float(np.median(jac[off])),
    }
    return sample, summary


def linkage_and_clusters(u: np.ndarray, k: int = K_DISPLAY):
    z = linkage(u, method="ward", metric="euclidean")
    labels = fcluster(z, k, criterion="maxclust")
    return z, labels


def rare_sensitivity(d: pd.DataFrame, shares: pd.DataFrame, pen: pd.DataFrame,
                     u_main: np.ndarray, labels_main: np.ndarray):
    rare_ids = pen.loc[pen["rare"], "raw_id"].tolist()
    keep = [c for c in shares.columns if c not in rare_ids]
    sub = shares[keep]
    sub = sub.div(sub.sum(axis=1), axis=0)
    u_sub = l2_norm(sub)
    z_sub, labels_sub = linkage_and_clusters(u_sub)
    ari = adjusted_rand_score(labels_main, labels_sub)
    dist_corr = float(np.corrcoef(pdist(u_main), pdist(u_sub))[0, 1])
    return {
        "rare_categories": [int(x) for x in rare_ids],
        "keep_categories": int(len(keep)),
        "ari_k4": float(ari),
        "distance_corr": dist_corr,
        "main_cluster_sizes": pd.Series(labels_main).value_counts().sort_index().to_dict(),
        "sensitivity_cluster_sizes": pd.Series(labels_sub).value_counts().sort_index().to_dict(),
    }, labels_sub, z_sub


def quadrant_profile(d: pd.DataFrame) -> pd.DataFrame:
    metrics = ["sku_count", "sku_hhi", "top1_sku_share", "n_cat", "cat_hhi", "cat_entropy"]
    rows = []
    for q, g in d.groupby("quadrant", observed=True):
        row = {"quadrant": q, "stores": len(g)}
        row.update({f"{m}_median": float(g[m].median()) for m in metrics})
        rows.append(row)
    return pd.DataFrame(rows)


def typical_stores(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["z_sku"] = (d["sku_count"] - d["sku_count"].mean()) / d["sku_count"].std(ddof=0)
    d["z_hhi"] = (d["sku_hhi"] - d["sku_hhi"].mean()) / d["sku_hhi"].std(ddof=0)
    p50s, p50h = d["sku_count"].median(), d["sku_hhi"].median()
    d["group"] = np.select(
        [(d.sku_count > p50s) & (d.sku_hhi > p50h),
         (d.sku_count > p50s) & (d.sku_hhi <= p50h),
         (d.sku_count <= p50s) & (d.sku_hhi > p50h)],
        ["高SKU·高HHI", "高SKU·低HHI", "低SKU·高HHI"], default="低SKU·低HHI"
    )
    rows = []
    for gname, g in d.groupby("group", observed=True):
        cx, cy = g["z_sku"].mean(), g["z_hhi"].mean()
        dist = np.sqrt((g["z_sku"] - cx) ** 2 + (g["z_hhi"] - cy) ** 2)
        idx = dist.sort_values(kind="mergesort").index[0]
        r = d.loc[idx]
        rows.append({"group": gname, "store_id": int(r["store_id"]), "city_id": int(r["city_id"]),
                     "sku_count": int(r["sku_count"]), "sku_hhi": float(r["sku_hhi"])})
    return pd.DataFrame(rows)


# ---------------- 图表 ----------------

def _save(fig, name: str) -> None:
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_hhi_dist(d): 
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hist(d["sku_hhi"], bins=45, color="#9ecae1", edgecolor="white")
    med = d["sku_hhi"].median()
    ax.axvline(med, color="#d62728", ls="--", lw=1.2)
    ax.text(med, ax.get_ylim()[1]*0.9, f"P50={med:.3f}", color="#d62728", fontsize=9)
    ax.set_title("门店 SKU HHI 分布（888 家，SKU≥10）")
    ax.set_xlabel("SKU HHI")
    ax.set_ylabel("门店数")
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "f1_store_hhi_distribution.png")


def fig_sku_hhi(d):
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.scatter(d["sku_count"], d["sku_hhi"], s=12, alpha=0.5, color="#4292c6")
    ax.set_xscale("log")
    ax.set_title("门店 SKU 覆盖数与 SKU HHI")
    ax.set_xlabel("门店 90 天 SKU 覆盖数（对数）")
    ax.set_ylabel("SKU HHI")
    ax.grid(alpha=0.25)
    _save(fig, "f2_sku_vs_hhi.png")


def fig_top_share(d):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, col, title in [(axes[0], "top1_sku_share", "Top1 SKU 份额"),
                           (axes[1], "top5_sku_share", "Top5 SKU 份额")]:
        ax.hist(d[col]*100, bins=40, color="#fd8d3c", edgecolor="white")
        ax.set_title(title)
        ax.set_xlabel("份额（%）")
        ax.set_ylabel("门店数")
        ax.grid(axis="y", alpha=0.25)
    _save(fig, "f3_top_share_distribution.png")


def fig_cat_count(d):
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    sc = ax.scatter(d["n_cat"], d["per_day_index"], c=d["decile"], cmap="viridis", s=14, alpha=0.7)
    ax.set_title("门店类别数与单店日均（颜色=SKU 十分位）")
    ax.set_xlabel("门店一级类别数")
    ax.set_ylabel("单店日均归一化销量指数")
    cbar = fig.colorbar(sc, ax=ax); cbar.set_label("SKU 十分位")
    ax.grid(alpha=0.25)
    _save(fig, "f4_category_count_vs_scale.png")


def fig_cat_hhi_entropy(d):
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    ax.scatter(d["cat_hhi"], d["cat_entropy"], s=14, alpha=0.55, color="#6baed6")
    ax.set_title("门店类别 HHI 与类别熵")
    ax.set_xlabel("类别 HHI")
    ax.set_ylabel("类别熵")
    ax.grid(alpha=0.25)
    _save(fig, "f5_category_hhi_entropy.png")


def fig_penetration(pen):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    sc = ax.scatter(pen["coverage"]*100, pen["median_share"]*100, s=20+pen["median_sku"]*3,
                    c=pen["rare"].map({True:"#d62728", False:"#4292c6"}), alpha=0.8,
                    edgecolors="white", linewidths=0.4)
    for _, r in pen.head(8).iterrows():
        ax.annotate(r["display_code"], (r["coverage"]*100, r["median_share"]*100),
                    textcoords="offset points", xytext=(4,4), fontsize=8)
    ax.set_title("一级类别覆盖率与份额中位（红=稀有类别 <10 店）")
    ax.set_xlabel("门店覆盖率（%）")
    ax.set_ylabel("类别份额中位（%）")
    ax.grid(alpha=0.25)
    _save(fig, "f6_category_penetration.png")


def fig_raw_vs_strat(d, dec_stats):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    sc = axes[0].scatter(d["sku_hhi"], d["per_day_index"], c=d["decile"], cmap="viridis", s=12, alpha=0.6)
    axes[0].set_title("原始：SKU HHI vs 单店日均")
    axes[0].set_xlabel("SKU HHI")
    axes[0].set_ylabel("单店日均")
    axes[0].grid(alpha=0.25)
    cbar = fig.colorbar(sc, ax=axes[0]); cbar.set_label("SKU 十分位")
    axes[1].bar(dec_stats["decile"], dec_stats["spearman_hhi_per_day"], color="#6baed6")
    axes[1].axhline(0, color="#444444", lw=0.8)
    axes[1].set_title("分层：各 SKU 十分位内 HHI-单店日均 Spearman")
    axes[1].set_xlabel("SKU 十分位（1=最少 SKU）")
    axes[1].set_ylabel("Spearman")
    axes[1].grid(axis="y", alpha=0.25)
    _save(fig, "f7_raw_vs_stratified.png")


def fig_hhi_resid(d):
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    ax.scatter(d["sku_hhi"], d["eff_resid"], s=12, alpha=0.55, color="#807dba")
    ax.set_title("SKU HHI 与 P3-B 相对效率残差")
    ax.set_xlabel("SKU HHI")
    ax.set_ylabel("P3-B Huber 残差（仅上下文）")
    ax.grid(alpha=0.25)
    _save(fig, "f8_hhi_vs_p3b_residual.png")


def fig_structure_heatmap(d, shares, labels):
    order = np.lexsort((d["store_id"].to_numpy(), labels))
    mat = shares.iloc[order].to_numpy()
    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(mat, aspect="auto", cmap="YlGnBu")
    ax.set_title("门店类别结构热图（按聚类排序，32 类）")
    ax.set_xlabel("一级类别（匿名编码列）")
    ax.set_ylabel("门店（按聚类排序）")
    cbar = fig.colorbar(im, ax=ax); cbar.set_label("门店内类别份额")
    _save(fig, "f9_structure_heatmap.png")


def fig_quadrant_profile(qp):
    metrics = ["sku_count_median", "sku_hhi_median", "top1_sku_share_median", "cat_hhi_median"]
    mat = qp[metrics].to_numpy()
    z = (mat - mat.mean(axis=0)) / np.where(mat.std(axis=0)==0, 1, mat.std(axis=0))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    im = ax.imshow(z, aspect="auto", cmap="coolwarm")
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(["SKU 数", "SKU HHI", "Top1 份额", "类别 HHI"], rotation=20)
    ax.set_yticks(range(len(qp)))
    ax.set_yticklabels(qp["quadrant"], fontsize=8)
    ax.set_title("P3-B 四象限 × 结构指标（列内标准化中位）")
    fig.colorbar(im, ax=ax).set_label("列内 z 分数")
    _save(fig, "f10_quadrant_structure.png")


def fig_dendrogram(z):
    fig, ax = plt.subplots(figsize=(11, 4.8))
    dendrogram(z, truncate_mode="lastp", p=30, ax=ax, no_labels=True, color_threshold=0)
    ax.set_title("门店类别结构层次聚类（L2+Euclidean+Ward，截断显示 30 簇）")
    ax.set_xlabel("簇")
    ax.set_ylabel("距离")
    _save(fig, "a1_dendrogram.png")


def fig_typical(d, typical, shares):
    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = np.zeros(len(typical))
    cats = shares.columns.tolist()
    top_cats = shares.sum().nlargest(8).index.tolist()
    for c in top_cats:
        vals = []
        for _, r in typical.iterrows():
            vals.append(float(shares.loc[r["store_id"], c]) if c in shares.columns else 0.0)
        ax.bar(typical["group"], vals, bottom=bottom, label=str(c))
        bottom += np.array(vals)
    # 其余类别合并为“其他”，保证堆叠合计为 1
    other = np.clip(1 - bottom, 0, None)
    ax.bar(typical["group"], other, bottom=bottom, label="其他", color="#bdbdbd")
    ax.set_title("典型门店一级类别结构（前 8 类 + 其他）")
    ax.set_ylabel("门店内类别份额")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(ncol=2, fontsize=7, frameon=False)
    ax.grid(axis="y", alpha=0.25)
    _save(fig, "a2_typical_store_structure.png")


def run() -> dict:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    s, long, pen = build_structure()
    d = s[s["structure_valid"]].copy()
    d = equal_size_deciles(d)
    dec = decile_stats(d)
    corr = correlation_table(d)

    shares, shares_norm = prepare_vectors(d, long)
    u = l2_norm(shares)
    cos_sum, sim = cosine_summary(u, d)
    z, labels = linkage_and_clusters(u, K_DISPLAY)
    rare, labels_sub, z_sub = rare_sensitivity(d, shares, pen, u, labels)
    sample, jac_sum = jaccard_sample(d, _con())
    qp = quadrant_profile(d)
    typical = typical_stores(d)

    d["cluster_k4"] = labels
    d["cluster_k4_rare_excluded"] = labels_sub
    d["cosine_with_city"] = np.nan

    s.to_csv(OUT_TABLES / "c1_store_structure.csv", index=False, encoding="utf-8-sig")
    long.merge(pd.read_csv(MAP_L1), left_on="first_category_id", right_on="raw_id", how="left").to_csv(
        OUT_TABLES / "c2_store_category.csv", index=False, encoding="utf-8-sig")
    pen.to_csv(OUT_TABLES / "c3_category_penetration.csv", index=False, encoding="utf-8-sig")
    d[["store_id", "city_id", "sku_count", "decile", "sku_hhi"]].to_csv(
        OUT_TABLES / "c4_store_deciles.csv", index=False, encoding="utf-8-sig")
    dec.to_csv(OUT_TABLES / "c5_decile_stats.csv", index=False, encoding="utf-8-sig")
    corr.to_csv(OUT_TABLES / "c6_structure_correlations.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([cos_sum, jac_sum]).to_csv(OUT_TABLES / "c7_similarity_summary.csv",
                                            index=False, encoding="utf-8-sig")
    d[["store_id", "city_id", "cluster_k4", "cluster_k4_rare_excluded"]].to_csv(
        OUT_TABLES / "c8_cluster_assignments.csv", index=False, encoding="utf-8-sig")
    sample.to_csv(OUT_TABLES / "c9_jaccard_sample.csv", index=False, encoding="utf-8-sig")
    qp.to_csv(OUT_TABLES / "c10_quadrant_structure.csv", index=False, encoding="utf-8-sig")
    typical.to_csv(OUT_TABLES / "c11_typical_stores.csv", index=False, encoding="utf-8-sig")

    summary = {
        "n_stores": int(len(s)), "n_model": int(len(d)), "n_lt10": int((~s["structure_valid"]).sum()),
        "hhi": {"median": float(d["sku_hhi"].median()), "p90": float(d["sku_hhi"].quantile(0.9))},
        "deciles": dec.to_dict("records"),
        "raw_correlations": corr.to_dict("records"),
        "similarity": cos_sum, "jaccard": jac_sum,
        "rare": rare, "k4_sizes": pd.Series(labels).value_counts().sort_index().to_dict(),
        "quadrant_profile": qp.to_dict("records"),
        "typical": typical.to_dict("records"),
    }
    with open(OUT_TABLES / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    fig_hhi_dist(d); fig_sku_hhi(d); fig_top_share(d); fig_cat_count(d)
    fig_cat_hhi_entropy(d); fig_penetration(pen); fig_raw_vs_strat(d, dec)
    fig_hhi_resid(d); fig_structure_heatmap(d, shares, labels); fig_quadrant_profile(qp)
    fig_dendrogram(z); fig_typical(d, typical, shares)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
