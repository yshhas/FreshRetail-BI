"""P4：经营诊断与决策支持（只读复用 P1–P3 已验收结果）。"""

from __future__ import annotations

import itertools
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
CLEAN = ROOT / "data" / "derived" / "clean_train.parquet"
P2 = ROOT / "data" / "analysis" / "p2"
P3C = ROOT / "data" / "analysis" / "p3c"
P3D = ROOT / "data" / "analysis" / "p3d"
OUT = ROOT / "data" / "analysis" / "p4"
FIGS = ROOT / "reports" / "figures" / "p4"

DOMAIN_COLS = ["stockout_domain", "R3", "R4", "R5", "R6"]
DOMAIN_LABELS = {
    "stockout_domain": "缺货",
    "R3": "持续低销",
    "R4": "高零销",
    "R5": "高波动",
    "R6": "高异常日",
}


def _csv(df: pd.DataFrame, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, encoding="utf-8-sig")


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    c1 = pd.read_csv(P3C / "c1_store_structure.csv")
    d1 = pd.read_csv(P3D / "d1_store_risk_base.csv")
    c8 = pd.read_csv(P3C / "c8_cluster_assignments.csv")
    return c1, d1, c8


# ---------------- P4-A ----------------

def build_profile(c1: pd.DataFrame, d1: pd.DataFrame, c8: pd.DataFrame) -> pd.DataFrame:
    risk_cols = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8",
                 "stockout_domain", "domain_count", "multi_risk",
                 "low_run_max_days", "in_risk_sample"]
    p = c1.merge(d1[["store_id"] + risk_cols], on="store_id", how="left")
    p = p.merge(c8[["store_id", "cluster_k4"]], on="store_id", how="left")
    p["cluster"] = p["cluster_k4"].apply(lambda x: f"G{int(x)}" if pd.notna(x) else "不适用")
    p["profile_status"] = np.where(p["in_risk_sample"] == True, "完整档案", "基础档案（SKU<10）")
    cols = [
        "store_id", "city_id", "profile_status",
        "total_index", "per_day_index", "sku_count", "per_sku_day_index",
        "cv", "zero_rate", "promo_rate",
        "stockout_sku_day_rate", "stockout_hour_rate", "store_day_any_stockout_rate",
        "eff_resid", "rlm_weight", "high_influence", "quadrant", "in_model",
        "sku_hhi", "top1_sku_share", "top5_sku_share", "cat_hhi", "cat_entropy",
        "n_cat", "top_cat_share", "effective_sku", "structure_valid",
        "cluster",
        "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8",
        "stockout_domain", "domain_count", "multi_risk",
        "low_run_max_days", "max_low_run_days", "in_risk_sample",
    ]
    return p[cols].copy()


def profile_dictionary() -> pd.DataFrame:
    rows = [
        ("store_id", "门店", "P3-D d1", "匿名门店 ID", "898"),
        ("city_id", "门店", "P3-D d1", "匿名城市 ID", "898"),
        ("profile_status", "门店", "P3-D d1.in_risk_sample", "完整档案 / 基础档案（SKU<10）", "898"),
        ("total_index", "门店", "P1/P3-B", "90 天归一化销量指数合计", "898"),
        ("per_day_index", "门店", "P1/P3-B", "total_index / 90", "898"),
        ("sku_count", "门店", "P1/P3-B", "90 天去重 SKU 数", "898"),
        ("per_sku_day_index", "门店", "P1/P3-B", "per_day_index / sku_count", "898"),
        ("cv", "门店", "P3-B", "门店日指数总体标准差 / 均值", "898"),
        ("zero_rate", "门店", "P3-B", "零销 SKU-日 / 门店 SKU-日", "898"),
        ("promo_rate", "门店", "P1/P3-B", "促销 SKU-日 / 门店 SKU-日", "898"),
        ("stockout_sku_day_rate", "门店", "P3-B", "有缺货 SKU-日 / 门店 SKU-日", "898"),
        ("stockout_hour_rate", "门店", "P3-B", "缺货小时 / (16×门店 SKU-日)", "898"),
        ("store_day_any_stockout_rate", "门店", "P1/P3-B", "至少 1 个 SKU 缺货的门店-日 / 90；饱和，仅背景", "898"),
        ("eff_resid", "门店", "P3-B", "log-log Huber 残差；相对统计偏离", "888"),
        ("rlm_weight", "门店", "P3-B", "Huber 最终权重", "888"),
        ("high_influence", "门店", "P3-B", "RLM 权重 <0.5", "888"),
        ("quadrant", "门店", "P3-B", "规模 P50 × 效率 P50 四象限", "888"),
        ("in_model", "门店", "P3-B", "SKU≥10", "898"),
        ("sku_hhi", "门店", "P3-C", "Σ 门店内 SKU 销量份额²", "898"),
        ("top1_sku_share", "门店", "P3-C", "最大 SKU 份额", "898"),
        ("top5_sku_share", "门店", "P3-C", "前 5 SKU 份额", "898"),
        ("cat_hhi", "门店", "P3-C", "Σ 一级类别份额²", "898"),
        ("cat_entropy", "门店", "P3-C", "类别熵", "898"),
        ("n_cat", "门店", "P3-C", "一级类别数", "898"),
        ("top_cat_share", "门店", "P3-C", "最大类别份额", "898"),
        ("effective_sku", "门店", "P3-C", "1 / sku_hhi", "898"),
        ("structure_valid", "门店", "P3-C", "SKU≥10，结构指标有效", "898"),
        ("cluster", "门店", "P3-C c8", "G1–G4 结构相似群；非业态", "888"),
        ("R1–R8", "门店", "P3-D", "冻结风险标记", "888 / 10 NA"),
        ("stockout_domain", "门店", "P3-D", "R1 或 R2", "888"),
        ("domain_count", "门店", "P3-D", "5 个运营域计数", "888"),
        ("multi_risk", "门店", "P3-D", "domain_count ≥2", "888"),
        ("low_run_max_days", "门店", "P3-D", "P1 规则复算真实最长连续低销天数", "898"),
        ("max_low_run_days", "门店", "P1/P3-B", "P1 截断字段；未达 7 天记为 0", "898"),
        ("in_risk_sample", "门店", "P3-D", "是否进入 888 风险样本", "898"),
    ]
    return pd.DataFrame(rows, columns=["field", "grain", "source", "definition", "n_scope"])


# ---------------- P4-B ----------------

def build_diagnosis(d1: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    risk = d1[d1["in_risk_sample"] == True].copy()
    def hit_labels(r):
        return [lab for col, lab in DOMAIN_LABELS.items() if bool(r[col])]
    risk["domain_labels"] = risk.apply(lambda r: ";".join(hit_labels(r)), axis=1)
    risk["exact_combo"] = risk.apply(lambda r: "+".join(hit_labels(r)) or "无运营域标记", axis=1)
    risk["structural_notes"] = risk.apply(
        lambda r: ";".join([x for x, ok in [("R7 覆盖偏窄", r["R7"]), ("R8 结构集中", r["R8"])] if bool(ok)]),
        axis=1)
    risk["diagnosis_status"] = "适用"

    cols = ["store_id", "city_id", "diagnosis_status",
            "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8",
            "stockout_domain", "domain_count", "multi_risk",
            "domain_labels", "exact_combo", "structural_notes"]
    dx = risk[cols].copy()

    not_app = d1[d1["in_risk_sample"] != True][["store_id", "city_id"]].copy()
    not_app["diagnosis_status"] = "不适用"
    not_app["reason"] = "SKU<10，仅保留基础档案，不参与风险诊断及同类比较"

    pair_rows = []
    for _, r in risk.iterrows():
        hit = [lab for col, lab in DOMAIN_LABELS.items() if bool(r[col])]
        for a, b in itertools.combinations(hit, 2):
            pair_rows.append({"store_id": int(r["store_id"]), "domain_a": a, "domain_b": b,
                              "definition": "至少同时命中这两个域（允许其他域）"})
    pairs = pd.DataFrame(pair_rows)

    rulebook = pd.DataFrame([
        ("B0", "适用性", "in_risk_sample=True", "P3-D in_risk_sample", "进入诊断", "不代表风险高低"),
        ("B0X", "适用性", "in_risk_sample=False", "P3-D in_risk_sample", "不适用，仅基础档案", "不得诊断/比较"),
        ("B1", "无运营域", "domain_count=0", "R1–R6", "无运营域标记", "不等于经营健康"),
        ("B2-STOCK", "单域", "domain_count=1 且 stockout_domain", "R1/R2", "缺货域单项命中", "不推断缺货原因"),
        ("B2-LOW", "单域", "domain_count=1 且 R3", "max_low_run_days>=7", "持续低销单项命中", "不代表需求不足"),
        ("B2-ZERO", "单域", "domain_count=1 且 R4", "zero_rate>P90", "高零销单项命中", "不区分无货/无需求"),
        ("B2-VOL", "单域", "domain_count=1 且 R5", "cv>P90", "高波动单项命中", "不推断经营能力"),
        ("B2-ANOM", "单域", "domain_count=1 且 R6", "anomaly_rate>P90", "高异常日单项命中", "可能是数据/促销/节假日"),
        ("B3", "多域", "domain_count>=2", "5 个运营域", "多标签 + 精确组合", "domain_count 不是严重度评分"),
        ("S7", "结构提示", "R7", "sku_count<=P10", "结构提示-覆盖偏窄", "不进入运营域"),
        ("S8", "结构提示", "R8", "同 SKU 十分位内 sku_hhi>P90", "结构提示-结构集中", "不进入运营域"),
    ], columns=["rule_id", "category", "condition", "evidence_fields", "label", "prohibited_interpretation"])

    # exact combination summary（只统计 ≥2 个运营域）
    multi = risk[risk["domain_count"] >= 2]
    exact = (multi.groupby("exact_combo").size().rename("stores").reset_index()
             .rename(columns={"exact_combo": "combination"}))
    exact["rank"] = exact["stores"].rank(method="min", ascending=False).astype(int)
    exact["definition"] = "恰好只命中这些域"
    exact = exact.sort_values(["rank", "stores", "combination"], ascending=[True, False, True]).reset_index(drop=True)

    # domain summary
    drows = []
    for col, lab in DOMAIN_LABELS.items():
        drows.append({"domain": lab, "stores": int(risk[col].sum()),
                      "rate_risk_sample": float(risk[col].mean()),
                      "single_domain_stores": int(((risk["domain_count"] == 1) & risk[col]).sum())})
    ds = pd.DataFrame(drows)
    return dx, not_app, pairs, rulebook, exact, ds


# ---------------- P4-C ----------------

def build_linkage() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect()
    inc = con.execute(f"""
        SELECT store_id, product_id, MAX(first_category_id) AS first_category_id,
               COUNT(DISTINCT dt) AS days_present,
               COUNT(*) AS observed_rows,
               SUM(sales_index) AS total_index,
               SUM(CASE WHEN sales_index = 0 THEN 1 ELSE 0 END) AS zero_days,
               SUM(CASE WHEN stockout_day_flag THEN 1 ELSE 0 END) AS stockout_days
        FROM read_parquet('{CLEAN.as_posix()}')
        GROUP BY 1, 2
    """).df()

    t1 = pd.read_csv(P2 / "t1_sku_metrics.csv")
    flags = t1[["product_id", "display_code", "store_count", "total_index",
                "first_category_id", "risk_flag_count", "flag_high_cv", "flag_high_zero",
                "flag_many_anomaly_days", "flag_store_concentration"]].copy()
    flags = flags.rename(columns={"total_index": "sku_total_index"})
    inc = inc.merge(flags, on="product_id", how="left", suffixes=("", "_p2"))
    inc["risk_flag_count"] = inc["risk_flag_count"].fillna(0).astype(int)
    for c in ["flag_high_cv", "flag_high_zero", "flag_many_anomaly_days", "flag_store_concentration"]:
        inc[c] = inc[c].fillna(False).astype(bool)
    inc["first_category_id"] = inc["first_category_id"].fillna(inc["first_category_id_p2"]).astype(int)
    inc = inc.drop(columns=["first_category_id_p2"])
    m = pd.read_csv(P2 / "map_l1.csv").rename(
        columns={"raw_id": "cat_raw_id", "display_code": "category_display_code"})
    inc = inc.merge(m, left_on="first_category_id", right_on="cat_raw_id", how="left").drop(columns=["cat_raw_id"])
    inc = inc.rename(columns={"display_code": "sku_display_code"})
    inc["is_flagged"] = inc["risk_flag_count"] > 0
    inc["is_multi_flag"] = inc["risk_flag_count"] >= 2

    inc_cols = ["store_id", "product_id", "sku_display_code", "first_category_id", "category_display_code",
                "days_present", "observed_rows", "total_index", "zero_days", "stockout_days",
                "risk_flag_count", "flag_high_cv", "flag_high_zero", "flag_many_anomaly_days",
                "flag_store_concentration", "is_flagged", "is_multi_flag"]
    inc = inc[inc_cols].sort_values(["store_id", "product_id"]).reset_index(drop=True)

    # store summary
    total = inc.groupby("store_id").agg(
        n_skus=("product_id", "nunique"),
        total_index=("total_index", "sum"),
        n_flagged_skus=("is_flagged", "sum"),
        n_multi_flag_skus=("is_multi_flag", "sum"),
        flagged_total_index=("total_index", lambda s: float(s[inc.loc[s.index, "is_flagged"]].sum())),
    ).reset_index()
    total["share_flagged_skus"] = total["n_flagged_skus"] / total["n_skus"]
    total["n_risk_pairs"] = total["n_flagged_skus"] * (total["n_flagged_skus"] - 1) // 2
    total["flagged_total_index_share"] = total["flagged_total_index"] / total["total_index"]

    # flagged SKU distribution
    f = t1[t1["risk_flag_count"] > 0].copy()
    f["store_coverage"] = f["store_count"] / 898.0
    f["total_share"] = f["total_index"] / t1["total_index"].sum()
    f = f.merge(m, left_on="first_category_id", right_on="cat_raw_id", how="left").drop(columns=["cat_raw_id"])
    f = f.rename(columns={"display_code": "sku_display_code"})
    fcols = ["product_id", "sku_display_code", "first_category_id", "category_display_code",
             "store_count", "store_coverage", "total_index", "total_share",
             "risk_flag_count", "flag_high_cv", "flag_high_zero",
             "flag_many_anomaly_days", "flag_store_concentration"]
    f = f[fcols].sort_values(["risk_flag_count", "store_count"], ascending=False).reset_index(drop=True)

    # category profile
    t4 = pd.read_csv(P2 / "t4_category_l1.csv")
    cat = t4[["raw_id", "display_code", "sku_count", "store_count", "total_index"]].copy()
    cat = cat.merge(
        f.groupby("first_category_id").agg(
            n_flagged_skus=("product_id", "nunique"),
            n_multi_flag_skus=("product_id", lambda s: int(f.loc[s.index, "risk_flag_count"].ge(2).sum())),
            flagged_total_index=("total_index", "sum"),
        ).reset_index().rename(columns={"first_category_id": "raw_id"}),
        on="raw_id", how="left")
    cat[["n_flagged_skus", "n_multi_flag_skus", "flagged_total_index"]] = \
        cat[["n_flagged_skus", "n_multi_flag_skus", "flagged_total_index"]].fillna(0)
    cat["flagged_sku_share"] = cat["n_flagged_skus"] / cat["sku_count"]
    cat["flagged_total_index_share"] = cat["flagged_total_index"] / cat["total_index"]
    # stores carrying flagged SKUs in category
    fs = inc[inc["is_flagged"]].groupby("first_category_id")["store_id"].nunique().rename("flagged_store_count")
    cat = cat.merge(fs, left_on="raw_id", right_index=True, how="left")
    cat["flagged_store_count"] = cat["flagged_store_count"].fillna(0).astype(int)
    cat["flagged_store_coverage"] = cat["flagged_store_count"] / 898.0
    cat = cat.rename(columns={"display_code": "category_display_code"})
    cat = cat.sort_values("flagged_sku_share", ascending=False).reset_index(drop=True)

    # SKU pair co-occurrence
    flagged_ids = f["product_id"].tolist()
    sets = inc[inc["is_flagged"]].groupby("product_id")["store_id"].apply(set).to_dict()
    codes = f.set_index("product_id")["sku_display_code"].to_dict()
    prows = []
    for a, b in itertools.combinations(sorted(flagged_ids), 2):
        n = len(sets.get(a, set()) & sets.get(b, set()))
        if n > 0:
            prows.append({"product_a": int(a), "product_b": int(b),
                          "sku_a": codes.get(a), "sku_b": codes.get(b),
                          "stores_both": n, "share_stores_both": n / 898.0})
    pairs = pd.DataFrame(prows).sort_values(["stores_both", "product_a"], ascending=[False, True]).reset_index(drop=True)

    # cross with B/C groups
    c1 = pd.read_csv(P3C / "c1_store_structure.csv")
    d1 = pd.read_csv(P3D / "d1_store_risk_base.csv")
    c8 = pd.read_csv(P3C / "c8_cluster_assignments.csv")
    s = total.merge(d1[["store_id", "quadrant", "domain_count", "multi_risk", "in_risk_sample"]], on="store_id", how="left")
    s["multi_risk"] = pd.to_numeric(s["multi_risk"], errors="coerce").astype(float)
    s["domain_count"] = pd.to_numeric(s["domain_count"], errors="coerce")
    s = s.merge(c8[["store_id", "cluster_k4"]], on="store_id", how="left")
    s["cluster"] = s["cluster_k4"].apply(lambda x: f"G{int(x)}" if pd.notna(x) else "不适用")
    s = s.merge(c1[["store_id", "n_cat", "sku_hhi"]], on="store_id", how="left")

    rows = []
    for gtype, gcol in [("quadrant", "quadrant"), ("cluster", "cluster")]:
        use = s[s["in_risk_sample"] == True].dropna(subset=[gcol])
        for g, gg in use.groupby(gcol):
            rows.append({"group_type": gtype, "group": g, "stores": len(gg),
                         "n_flagged_median": float(gg["n_flagged_skus"].median()),
                         "share_flagged_median": float(gg["share_flagged_skus"].median()),
                         "n_multi_median": float(gg["n_multi_flag_skus"].median()),
                         "n_risk_pairs_median": float(gg["n_risk_pairs"].median()),
                         "multi_risk_rate": float(gg["multi_risk"].mean()),
                         "sample_insufficient": bool(len(gg) < 20)})
    cross = pd.DataFrame(rows)
    cells = (s[s["in_risk_sample"] == True].dropna(subset=["quadrant", "cluster"])
             .groupby(["quadrant", "cluster"]).agg(
                 stores=("store_id", "size"),
                 n_flagged_median=("n_flagged_skus", "median"),
                 share_flagged_median=("share_flagged_skus", "median"),
                 multi_risk_rate=("multi_risk", "mean")).reset_index())
    q_order = sorted(s.loc[s["in_risk_sample"] == True, "quadrant"].dropna().unique())
    c_order = sorted(s.loc[s["in_risk_sample"] == True, "cluster"].dropna().unique())
    cells = (cells.set_index(["quadrant", "cluster"])
             .reindex(pd.MultiIndex.from_product([q_order, c_order], names=["quadrant", "cluster"]))
             .reset_index())
    cells["stores"] = cells["stores"].fillna(0).astype(int)
    cells["sample_insufficient"] = cells["stores"] < 20
    return inc, s, f, cat, pairs, cross, cells


# ---------------- figures ----------------

def save(fig, name: str) -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figure_combo(exact: pd.DataFrame) -> None:
    sub = exact[exact["rank"] <= 10].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(sub["combination"][::-1], sub["stores"][::-1], color="#6baed6")
    for i, v in enumerate(sub["stores"][::-1]):
        ax.text(v + 0.5, i, str(int(v)), va="center", fontsize=8)
    ax.set_xlabel("门店数")
    ax.set_title("P4-B 精确风险组合（恰好只命中该组合；并列全列）")
    ax.grid(axis="x", alpha=.25)
    save(fig, "p4_f1_exact_combinations.png")


def figure_quadrant_cluster(s: pd.DataFrame) -> None:
    use = s[s["in_risk_sample"] == True].dropna(subset=["quadrant", "cluster"])
    piv = use.pivot_table(index="quadrant", columns="cluster", values="multi_risk", aggfunc="mean")
    cnt = use.pivot_table(index="quadrant", columns="cluster", values="store_id", aggfunc="size")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    im = ax.imshow(piv.values * 100, cmap="Reds", vmin=0, vmax=35)
    ax.set_xticks(range(len(piv.columns))); ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(len(piv.index))); ax.set_yticklabels([x.replace("·", "\n") for x in piv.index], fontsize=7)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            n = int(cnt.values[i, j]) if not np.isnan(cnt.values[i, j]) else 0
            v = 0 if np.isnan(piv.values[i, j]) else piv.values[i, j] * 100
            txt = "—" if n < 20 else f"{v:.1f}%\n(n={n})"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7,
                    color="white" if v > 18 else "#333333")
    ax.set_title("P4-C 四象限 × 结构群多风险率（n<20 标 —）")
    fig.colorbar(im, ax=ax).set_label("多风险率（%）")
    save(fig, "p4_f2_quadrant_cluster_multi.png")


def figure_flagged_coverage(f: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.hist(f["store_coverage"], bins=25, color="#9ecae1", edgecolor="white")
    ax.set_xlabel("门店覆盖率（P2 flagged SKU 的 store_count / 898）")
    ax.set_ylabel("SKU 数")
    ax.set_title(f"P4-C {len(f)} 个风险 SKU 的门店覆盖分布")
    ax.grid(axis="y", alpha=.25)
    save(fig, "p4_f3_flagged_sku_coverage.png")


def figure_store_share(s: pd.DataFrame) -> None:
    use = s[s["in_risk_sample"] == True]
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.hist(use["share_flagged_skus"], bins=30, color="#fdae6b", edgecolor="white")
    ax.axvline(use["share_flagged_skus"].median(), color="#d62728", ls="--", lw=1)
    ax.set_xlabel("门店风险 SKU 占比（flagged SKU / 门店 SKU）")
    ax.set_ylabel("门店数")
    ax.set_title("P4-C 门店风险 SKU 占比分布（888 家）")
    ax.grid(axis="y", alpha=.25)
    save(fig, "p4_f4_store_flagged_share.png")


def figure_category(cat: pd.DataFrame) -> None:
    sub = cat.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(sub["category_display_code"], sub["flagged_sku_share"] * 100, color="#74c476")
    ax.set_xlabel("类别内 flagged SKU 占比（%）")
    ax.set_title("P4-C 一级类别风险 SKU 占比（Top 15）")
    ax.grid(axis="x", alpha=.25)
    save(fig, "p4_f5_category_flagged_share.png")


def figure_pairs(pairs: pd.DataFrame) -> None:
    sub = pairs.head(15).iloc[::-1]
    labels = [f"{a}/{b}" for a, b in zip(sub["sku_a"], sub["sku_b"])]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(labels, sub["stores_both"], color="#9e9ac8")
    ax.set_xlabel("观察期内同店共同出现的门店数")
    ax.set_title("P4-C 风险 SKU 观察期内同店共同出现 Top 15")
    ax.grid(axis="x", alpha=.25)
    save(fig, "p4_f6_sku_pair_cooccurrence.png")


# ---------------- run ----------------

def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True); FIGS.mkdir(parents=True, exist_ok=True)
    c1, d1, c8 = load()

    profile = build_profile(c1, d1, c8)
    _csv(profile, "p4_a_store_profile.csv")
    _csv(profile_dictionary(), "p4_a_field_dictionary.csv")

    dx, not_app, pairs, rulebook, exact, ds = build_diagnosis(d1)
    _csv(dx, "p4_b_store_diagnosis.csv")
    _csv(not_app, "p4_b_not_applicable.csv")
    _csv(pairs, "p4_b_store_pairs.csv")
    _csv(rulebook, "p4_b_rulebook.csv")
    _csv(exact, "p4_b_exact_combinations.csv")
    _csv(ds, "p4_b_domain_summary.csv")

    inc, total, fdist, cat, pair_inc, cross, cells = build_linkage()
    _csv(inc, "p4_c_store_sku_incidence.csv")
    _csv(total, "p4_c_store_sku_risk_summary.csv")
    _csv(fdist, "p4_c_flagged_sku_distribution.csv")
    _csv(cat, "p4_c_category_risk_profile.csv")
    _csv(pair_inc, "p4_c_sku_pair_cooccurrence.csv")
    _csv(cross, "p4_c_group_risk_cross.csv")
    _csv(cells, "p4_c_quadrant_cluster_cross.csv")

    figure_combo(exact)
    figure_quadrant_cluster(total)
    figure_flagged_coverage(fdist)
    figure_store_share(total)
    figure_category(cat)
    figure_pairs(pair_inc)

    s = total
    summary = {
        "p4_a": {"rows": len(profile), "full": int((profile.profile_status == "完整档案").sum()),
                 "basic": int((profile.profile_status != "完整档案").sum())},
        "p4_b": {"rows": len(dx), "not_applicable": len(not_app),
                 "domain_counts": dx.domain_count.value_counts().sort_index().to_dict(),
                 "multi": int(dx.multi_risk.sum()), "exact_combinations": len(exact),
                 "pair_rows": len(pairs), "rulebook_rows": len(rulebook)},
        "p4_c": {"incidence_rows": len(inc), "unique_store_sku": int(inc[["store_id", "product_id"]].drop_duplicates().shape[0]),
                 "observed_rows": int(inc.observed_rows.sum()),
                 "total_index": float(inc.total_index.sum()),
                 "skus": int(inc.product_id.nunique()), "stores": int(inc.store_id.nunique()),
                 "flagged_skus": len(fdist), "multi_flag_skus": int(fdist.risk_flag_count.ge(2).sum()),
                 "pair_rows": len(pair_inc),
                 "store_summary_rows": len(total),
                 "quadrant_cluster_cells": len(cells),
                 "insufficient_cells": int(cells.sample_insufficient.sum())},
        "p4_d": {"report": "08_P4经营诊断与决策支持报告.md"},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
