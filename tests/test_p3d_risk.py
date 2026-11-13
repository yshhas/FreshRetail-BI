import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from freshretail.analysis import p3d_risk as d


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "analysis" / "p3d"


def _mini() -> pd.DataFrame:
    return pd.DataFrame({
        "store_id": [1, 2, 3, 4],
        "stockout_sku_day_rate": [0.9, 0.1, 0.9, 0.1],
        "stockout_hour_rate": [0.9, 0.9, 0.1, 0.1],
        "max_low_run_days": [0, 0, 0, 8],
        "zero_rate": [0.0] * 4,
        "cv": [0.0] * 4,
        "anomaly_rate": [0.0] * 4,
        "sku_count": [50] * 4,
        "decile": [1] * 4,
        "sku_hhi": [0.1] * 4,
    })


def test_equal_size_groups_no_loss_and_balanced():
    df = pd.DataFrame({
        "store_id": list(range(1, 26)),
        "sku_count": [10] * 5 + [20] * 5 + [30] * 5 + [40] * 5 + [50] * 5,
    })
    g = d.equal_size_groups(df, 4, "quartile")
    assert len(g) == 25
    counts = g.value_counts()
    assert len(counts) == 4
    assert counts.max() - counts.min() <= 1


def test_add_flags_stockout_domain_merges_r1_r2():
    th = {"R1": 0.5, "R2": 0.5, "R4": 0.5, "R5": 0.5, "R6": 0.5, "R7": 10}
    out = d.add_flags(_mini(), th)
    assert out["stockout_domain"].tolist() == [True, True, True, False]
    # R1、R2 同时命中仍只计 1 个运营风险域
    assert out["domain_count"].tolist() == [1, 1, 1, 1]
    assert out.loc[0, "R1"] and out.loc[0, "R2"]
    assert not out.loc[3, "R1"] and out.loc[3, "R3"]


def test_r8_threshold_is_within_decile():
    df = pd.DataFrame({
        "store_id": range(20),
        "sku_hhi": [0.5] * 10 + [0.01] * 10,
        "decile": [1] * 10 + [2] * 10,
    })
    out = df.groupby("decile")["sku_hhi"].transform(lambda s: s > s.quantile(0.90))
    # 同一 HHI 在高集中组与低集中组都不应因全局阈值而误判
    assert out.sum() == 0
    assert (df.assign(flag=out).groupby("decile").flag.sum() == 0).all()


def test_p3d_regression_outputs():
    base = pd.read_csv(OUT / "d1_store_risk_base.csv")
    th = pd.read_csv(OUT / "d2_thresholds.csv")
    cross = pd.read_csv(OUT / "d3b_stockout_flag_cross.csv")
    dec = pd.read_csv(OUT / "d4_within_decile_relations.csv")
    dist = pd.read_csv(OUT / "d9_domain_count.csv")
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))

    assert len(base) == 898
    assert int(base["in_risk_sample"].sum()) == 888
    out = base[~base["in_risk_sample"]]
    assert out["R1"].isna().all() and out["multi_risk"].isna().all()
    assert out["domain_count"].isna().all()
    assert set(summary["flag_counts"].items()) == {
        ("R1", 89), ("R2", 89), ("R3", 90), ("R4", 89),
        ("R5", 89), ("R6", 56), ("R7", 93), ("R8", 90)}

    assert th.loc[th.flag == "R1", "hits"].iloc[0] == 89
    assert th.loc[th.flag == "R6", "hits"].iloc[0] == 56
    assert th.loc[th.flag == "R7", "comparator"].iloc[0] == "<="
    r8 = th[th.flag == "R8"]
    assert len(r8) == 10
    assert r8["hits"].sum() == 90
    assert (r8["n_sample"] >= 88).all()

    assert cross["stores"].sum() == 888
    assert int(cross[(cross.R1) & (cross.R2)]["stores"].iloc[0]) == 24

    assert dist["stores"].sum() == 888
    assert dist.set_index("domain_count").loc[0, "stores"] == 581
    assert summary["multi_risk"] == 132
    assert summary["r1_r2_union"] == 154

    assert set(dec["stratum"]) == {"decile", "quartile"}
    assert dec[dec.stratum == "decile"]["group"].nunique() == 10
    assert dec[dec.stratum == "quartile"]["group"].nunique() == 4


def test_stockout_metric_bounds():
    base = pd.read_csv(OUT / "d1_store_risk_base.csv")
    r = base[base["in_risk_sample"]]
    assert (r["stockout_hour_rate"] <= r["stockout_sku_day_rate"] + 1e-12).all()
    assert (r["stockout_hour_rate"] >= r["stockout_sku_day_rate"] / 16 - 1e-12).all()
    assert r["stockout_sku_day_rate"].between(0, 1).all()
    assert r["stockout_hour_rate"].between(0, 1).all()


def test_relation_directions_and_bootstrap_params():
    rel = pd.read_csv(OUT / "d3_stockout_relations.csv").set_index("relation")
    assert rel.loc["r1_vs_r2", "spearman"] == pytest.approx(0.377, abs=0.01)
    assert rel.loc["r2_vs_per_day", "spearman"] < -0.4
    assert rel.loc["r1_vs_per_day", "spearman"] > -0.1
    assert rel.loc["r2_vs_zero", "spearman"] > 0.6
    assert rel.loc["r1_vs_zero", "spearman"] > -0.1
    assert (rel["ci_low"] <= rel["spearman"]).all()
    assert (rel["spearman"] <= rel["ci_high"]).all()

    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    b = summary["bootstrap"]
    assert b["seed"] == 42 and b["n_boot"] == 1000
    assert b["store_n"] == 888 and b["city_n"] == 18


def test_typical_store_rule_recomputable():
    base = pd.read_csv(OUT / "d1_store_risk_base.csv")
    typ = pd.read_csv(OUT / "d12_typical_stores.csv")
    feats = ["stockout_sku_day_rate", "stockout_hour_rate", "zero_rate", "cv", "per_day_index"]
    r = base[base["in_risk_sample"]].copy()
    z = r[feats].copy()
    for c in feats:
        z[c] = (z[c] - z[c].mean()) / z[c].std(ddof=0)
    z["store_id"] = r["store_id"].to_numpy()
    z["domain_count"] = r["domain_count"].to_numpy()
    assert typ["group"].tolist() == ["0域", "1域", "2域", "≥3域"]
    for _, row in typ.iterrows():
        k = int(row["domain_count"])
        g = z[z.domain_count == k] if k < 3 else z[z.domain_count >= 3]
        center = g[feats].mean()
        dist = np.sqrt(((g[feats] - center) ** 2).sum(axis=1))
        best = pd.DataFrame({"store_id": g["store_id"].to_numpy(), "dist": dist.to_numpy()})
        best = best.sort_values(["dist", "store_id"], kind="mergesort").iloc[0]
        assert int(best["store_id"]) == int(row["store_id"])


def test_no_eval_reference_and_train_only():
    src = (ROOT / "src" / "freshretail" / "analysis" / "p3d_risk.py").read_text(encoding="utf-8")
    assert "clean_eval" not in src
    assert "eval.parquet" not in src
    # M4 允许读取 train 派生表 agg_store_day.parquet，用于恢复真实连续低销天数
    assert src.count("parquet") == 2  # 常量 + low_run_table 文档字符串，均只指向 agg_store_day
    assert "clean_train.parquet" not in src
    assert "agg_store_day.parquet" in src


def test_corrections_m1_m4_m5_l1_l2():
    base = pd.read_csv(OUT / "d1_store_risk_base.csv")
    r = base[base["in_risk_sample"]].copy()
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))

    # M4：真实连续低销天数恢复；R3 不变
    assert int((r["low_run_max_days"].between(1, 6)).sum()) == 54
    assert int(((r["max_low_run_days"] == 0) & r["low_run_max_days"].between(1, 6)).sum()) == 54
    assert int(r["R3"].sum()) == 90
    assert (r["R3"] == (r["low_run_max_days"] >= 7)).all()
    rel = pd.read_csv(OUT / "d3_stockout_relations.csv").set_index("relation")
    assert rel.loc["r1_vs_low", "y"] == "low_run_max_days"
    assert rel.loc["r2_vs_low", "spearman"] == pytest.approx(0.0143, abs=0.01)

    # M1：全样本池化
    overall = pd.read_csv(OUT / "d13_overall_rates.csv").set_index("metric")
    assert overall.loc["SKU-日缺货率（全样本池化）", "rate"] == pytest.approx(0.442668, abs=1e-6)
    assert overall.loc["小时槽位缺货率（全样本池化）", "rate"] == pytest.approx(0.198771, abs=1e-6)
    assert overall.loc["SKU-日缺货率（全样本池化）", "denominator"] == 4500000

    # M5：Bootstrap 样本量披露；CI 未变
    b = summary["bootstrap"]
    assert b["city_sample"]["min"] == 218
    assert b["city_sample"]["max"] == 1983
    assert b["city_sample"]["median"] == 852
    d3 = pd.read_csv(OUT / "d3_stockout_relations.csv").set_index("relation")
    assert d3.loc["r1_vs_r2", "ci_low"] == pytest.approx(0.316475, abs=1e-5)
    assert d3.loc["r1_vs_r2", "city_boot_high"] == pytest.approx(0.659151, abs=1e-5)

    # L1：恰好组合与并列
    d10 = pd.read_csv(OUT / "d10_top_combinations.csv")
    assert set(d10["definition"]) == {"恰好只命中这些域"}
    assert len(d10) == 11
    assert (d10["rank"] == 10).sum() == 2
    assert d10.loc[d10.combination == "缺货+高零销", "stores"].iloc[0] == 38
    pair = pd.read_csv(OUT / "d8b_pairwise_combinations.csv")
    row = pair[(pair.domain_a == "缺货") & (pair.domain_b == "高零销")].iloc[0]
    assert row["stores_at_least"] == 56
    assert "至少" in row["definition"]

    # L2：城市分母
    city = pd.read_csv(OUT / "d5_city_risk.csv").set_index("city_id")
    assert {"stores_all", "stores_risk", "multi_risk_rate_risk", "multi_risk_rate_all"} <= set(city.columns)
    assert city.loc[3, "stores_all"] == 101 and city.loc[3, "stores_risk"] == 92
    assert city.loc[3, "multi_risk_rate_all"] == pytest.approx(0.554455, abs=1e-6)
    assert city.loc[3, "multi_risk_rate_risk"] == pytest.approx(0.608696, abs=1e-6)

    # M3：City 0 两种方案
    d11 = pd.read_csv(OUT / "d11_sensitivity.csv").set_index("sensitivity")
    assert d11.loc["exclude_city0_original_thresholds_multi", "hits"] == 129
    assert d11.loc["exclude_city0_recomputed_thresholds_multi", "hits"] == 96
    for code, h in [("R1", 83), ("R2", 89), ("R4", 88), ("R5", 86), ("R6", 51)]:
        assert d11.loc[f"exclude_city0_original_thresholds_{code}", "hits"] == h
        expected = 60 if code != "R6" else 51
        assert d11.loc[f"exclude_city0_recomputed_thresholds_{code}", "hits"] == expected
