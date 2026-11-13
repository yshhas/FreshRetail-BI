import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
P4 = ROOT / "data" / "analysis" / "p4"
P3C = ROOT / "data" / "analysis" / "p3c"
P3D = ROOT / "data" / "analysis" / "p3d"


def test_p4_a_profile_scope():
    a = pd.read_csv(P4 / "p4_a_store_profile.csv")
    c1 = pd.read_csv(P3C / "c1_store_structure.csv")
    assert len(a) == 898
    assert a["profile_status"].value_counts().to_dict() == {"完整档案": 888, "基础档案（SKU<10）": 10}
    assert a["R1"].isna().sum() == 10
    assert a.loc[a.profile_status == "完整档案", "cluster"].notna().all()
    for c in ["total_index", "per_day_index", "sku_count", "cv", "zero_rate", "stockout_hour_rate"]:
        assert np.allclose(a.set_index("store_id")[c], c1.set_index("store_id")[c], equal_nan=True)
    assert "rank" not in a.columns


def test_p4_b_matches_p3d():
    b = pd.read_csv(P4 / "p4_b_store_diagnosis.csv")
    na = pd.read_csv(P4 / "p4_b_not_applicable.csv")
    d1 = pd.read_csv(P3D / "d1_store_risk_base.csv")
    d10 = pd.read_csv(P3D / "d10_top_combinations.csv")
    assert len(b) == 888
    assert len(na) == 10
    assert (na.diagnosis_status == "不适用").all()
    assert b.domain_count.value_counts().sort_index().to_dict() == {0.0: 581, 1.0: 175, 2.0: 101, 3.0: 25, 4.0: 4, 5.0: 2}
    assert int(b.multi_risk.sum()) == 132
    r = d1[d1.in_risk_sample == True].set_index("store_id")
    bb = b.set_index("store_id")
    for c in ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
        assert (bb[c].astype(bool) == r[c].astype(bool)).all()
    ex = pd.read_csv(P4 / "p4_b_exact_combinations.csv")
    assert ex.stores.sum() == 132
    assert ex.head(10)[["combination", "stores"]].to_dict("records") == d10.head(10)[["combination", "stores"]].to_dict("records")


def test_p4_b_at_least_vs_exact():
    pairs = pd.read_csv(P4 / "p4_b_store_pairs.csv")
    ex = pd.read_csv(P4 / "p4_b_exact_combinations.csv")
    at_least = int(((pairs.domain_a == "缺货") & (pairs.domain_b == "高零销")).sum())
    exact = int(ex.loc[ex.combination == "缺货+高零销", "stores"].iloc[0])
    assert at_least == 56
    assert exact == 38


def test_p4_c_incidence_contract():
    inc = pd.read_csv(P4 / "p4_c_store_sku_incidence.csv")
    c1 = pd.read_csv(P3C / "c1_store_structure.csv")
    assert len(inc) == 50000
    assert inc[["store_id", "product_id"]].duplicated().sum() == 0
    assert int(inc.observed_rows.sum()) == 4_500_000
    assert inc.total_index.sum() == pytest.approx(4493660.787, abs=1e-3)
    assert int(inc.product_id.nunique()) == 865
    assert int(inc.store_id.nunique()) == 898
    s = pd.read_csv(P4 / "p4_c_store_sku_risk_summary.csv")
    assert len(s) == 898
    assert (s.set_index("store_id").n_skus - c1.set_index("store_id").sku_count).abs().max() == 0
    assert (s["n_flagged_skus"] <= s["n_skus"]).all()
    assert np.allclose(s["share_flagged_skus"], s["n_flagged_skus"] / s["n_skus"])
    assert (s["n_risk_pairs"] == s["n_flagged_skus"] * (s["n_flagged_skus"] - 1) // 2).all()


def test_p4_c_flagged_sku_reuse():
    f = pd.read_csv(P4 / "p4_c_flagged_sku_distribution.csv")
    cat = pd.read_csv(P4 / "p4_c_category_risk_profile.csv")
    assert len(f) == 117
    assert int(f.risk_flag_count.ge(2).sum()) == 35
    assert f.store_count.between(1, 898).all()
    assert len(cat) == 32
    assert int(cat.n_flagged_skus.sum()) == 117
    assert int(cat.n_multi_flag_skus.sum()) == 35
    assert (cat.flagged_sku_share.between(0, 1)).all()


def test_p4_c_pairs_and_cells():
    pc = pd.read_csv(P4 / "p4_c_sku_pair_cooccurrence.csv")
    cells = pd.read_csv(P4 / "p4_c_quadrant_cluster_cross.csv")
    assert pc[["product_a", "product_b"]].duplicated().sum() == 0
    assert pc.stores_both.between(1, 898).all()
    assert np.allclose(pc.share_stores_both, pc.stores_both / 898)
    assert len(cells) == 16
    assert int(cells.stores.sum()) == 888
    assert (cells.sample_insufficient == (cells.stores < 20)).all()
    assert cells.sample_insufficient.any()


def test_p4_summary_and_no_scores():
    s = json.loads((P4 / "summary.json").read_text(encoding="utf-8"))
    assert s["p4_a"] == {"rows": 898, "full": 888, "basic": 10}
    assert s["p4_b"]["multi"] == 132
    assert s["p4_c"]["incidence_rows"] == 50000
    assert s["p4_c"]["flagged_skus"] == 117
    assert s["p4_c"]["quadrant_cluster_cells"] == 16
    for name in ["p4_a_store_profile.csv", "p4_b_store_diagnosis.csv", "p4_c_store_sku_risk_summary.csv"]:
        cols = pd.read_csv(P4 / name, nrows=0).columns
        assert not any("score" in c.lower() or c.lower() in {"store_rank", "risk_rank"} for c in cols)


def test_p4_no_eval_reference():
    src = (ROOT / "src" / "freshretail" / "analysis" / "p4_diagnosis.py").read_text(encoding="utf-8")
    assert "clean_eval" not in src
    assert "eval.parquet" not in src
    assert "clean_train.parquet" in src
