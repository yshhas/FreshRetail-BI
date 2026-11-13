import duckdb
import numpy as np
import pandas as pd
import pytest

from freshretail.analysis import p3c_structure as c


def test_l2_norm_unit_rows():
    m = pd.DataFrame({"a": [3.0, 0.0], "b": [4.0, 2.0]})
    u = c.l2_norm(m)
    assert np.allclose(np.linalg.norm(u, axis=1), 1.0)


def test_equal_size_deciles_no_loss_and_ties_split():
    df = pd.DataFrame({
        "store_id": list(range(1, 26)),
        "sku_count": [10] * 5 + [20] * 5 + [30] * 5 + [40] * 5 + [50] * 5,
    })
    out = c.equal_size_deciles(df)
    assert len(out) == 25
    assert set(out["store_id"]) == set(df["store_id"])
    counts = out.groupby("decile").size()
    assert len(counts) == 10
    assert counts.max() - counts.min() <= 1
    assert counts.sum() == 25
    # 相同 SKU 数在边界处可进入不同组，但不得丢失门店
    assert out.loc[out["sku_count"] == 10, "decile"].nunique() >= 1


def test_store_sku_hhi_formula():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE clean (
            store_id INT, product_id INT, first_category_id INT,
            second_category_id INT, third_category_id INT, sales_index DOUBLE
        )
    """)
    con.execute("""
        INSERT INTO clean VALUES
        (1,1,1,10,100,60),
        (1,2,1,10,101,30),
        (1,3,2,20,200,10)
    """)
    out = c.store_sku_structure(con).set_index("store_id")
    assert out.loc[1, "sku_hhi"] == pytest.approx(0.46)
    assert out.loc[1, "top1_sku_share"] == pytest.approx(0.6)
    assert out.loc[1, "top5_sku_share"] == pytest.approx(1.0)
    assert out.loc[1, "n_sku"] == 3


def test_p3c_regression_outputs():
    from pathlib import Path
    import json
    root = Path(__file__).resolve().parents[1]
    out = root / "data" / "analysis" / "p3c"
    s = pd.read_csv(out / "c1_store_structure.csv")
    dec = pd.read_csv(out / "c5_decile_stats.csv")
    clus = pd.read_csv(out / "c8_cluster_assignments.csv")
    shares = pd.read_csv(out / "c2_store_category.csv")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert len(s) == 898
    assert int(s["structure_valid"].sum()) == 888
    assert s["total_index"].sum() == pytest.approx(4493660.787, abs=1e-3)
    assert len(dec) == 10
    assert dec["n"].sum() == 888
    assert dec["n"].max() - dec["n"].min() <= 1
    assert (dec["sku_min"] <= dec["sku_max"]).all()
    assert summary["rare"]["ari_k4"] == pytest.approx(1.0)
    assert summary["rare"]["distance_corr"] > 0.999
    assert summary["rare"]["keep_categories"] == 28
    assert summary["similarity"]["within_city_mean"] > summary["similarity"]["between_city_mean"]
    assert summary["jaccard"]["n_sample"] == 100
    assert clus["cluster_k4"].nunique() == 4
    assert clus["cluster_k4"].value_counts().sort_index().to_dict() == {1: 189, 2: 181, 3: 168, 4: 350}

    # 门店内类别份额合计为 1
    sums = shares.groupby("store_id")["share"].sum()
    assert np.allclose(sums.to_numpy(), 1.0, atol=1e-9)


def test_p3c_decile_direction_instability():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    dec = pd.read_csv(root / "data" / "analysis" / "p3c" / "c5_decile_stats.csv")
    rho = dec["spearman_hhi_per_day"].dropna()
    assert rho.min() < 0 < rho.max()


def test_spearman_ci_order_invariant():
    rng = np.random.default_rng(7)
    n = 200
    sid = rng.permutation(np.arange(1, n + 1))
    x = rng.normal(size=n)
    y = 0.4 * x + rng.normal(size=n)
    r1 = c._spearman_ci(x, y, store_ids=sid, n_boot=200)
    perm = rng.permutation(n)
    r2 = c._spearman_ci(x[perm], y[perm], store_ids=sid[perm], n_boot=200)
    assert r1[0] == pytest.approx(r2[0])
    assert r1[1] == pytest.approx(r2[1])
    assert r1[2] == pytest.approx(r2[2])
    assert r1[3] == r2[3] == n
