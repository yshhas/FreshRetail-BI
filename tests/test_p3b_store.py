import numpy as np
import pandas as pd
import pytest

from freshretail.analysis import p3b_store as b


def test_r2_definitions():
    y = np.array([1.0, 2.0, 3.0])
    fitted = np.array([1.1, 1.9, 3.1])
    assert b.r2_corr(y, y) == pytest.approx(1.0)
    assert b.r2_corr(y, fitted) > 0.98
    assert b.r2_weighted(y, y, np.ones(3)) == pytest.approx(1.0)
    w = np.array([1.0, 1.0, 2.0])
    assert b.r2_weighted(y, fitted, w) < 1.0


def test_quadrant_tie_goes_low():
    # 加入 5 家：中位 scale=20、eff=0；等于中位的门店应进入低组
    df = pd.DataFrame({
        "per_day_index": [10.0, 10.0, 30.0, 30.0, 20.0],
        "eff_resid": [-1.0, 1.0, -1.0, 1.0, 0.0],
    })
    out, p50s, p50e = b.assign_quadrants(df, "eff_resid")
    assert p50s == 20.0 and p50e == 0.0
    tie = out.iloc[4]
    assert tie["quadrant"] == "Q4 低规模·相对低效率"
    assert set(out["quadrant"]) == {
        "Q1 高规模·相对高效率", "Q2 高规模·相对低效率",
        "Q3 低规模·相对高效率", "Q4 低规模·相对低效率",
    }


def test_typical_store_selection_deterministic():
    df = pd.DataFrame({
        "store_id": [1, 2, 3, 4],
        "city_id": [0, 0, 1, 1],
        "per_day_index": [10.0, 12.0, 30.0, 32.0],
        "eff_resid": [-1.0, -0.9, 1.0, 1.1],
        "sku_count": [20, 20, 20, 20],
        "quadrant": ["Q3 低规模·相对高效率", "Q3 低规模·相对高效率",
                     "Q1 高规模·相对高效率", "Q1 高规模·相对高效率"],
    })
    a = b.typical_stores(df).sort_values("quadrant").reset_index(drop=True)
    c = b.typical_stores(df).sort_values("quadrant").reset_index(drop=True)
    assert a["store_id"].tolist() == c["store_id"].tolist()
    assert set(a["store_id"]).issubset({1, 2, 3, 4})


def test_p3b_regression_numbers():
    from pathlib import Path
    import json
    root = Path(__file__).resolve().parents[1]
    out = root / "data" / "analysis" / "p3b"
    stores = pd.read_csv(out / "b1_store_metrics.csv")
    sens = pd.read_csv(out / "b3_threshold_sensitivity.csv")
    comp = pd.read_csv(out / "b2_model_comparison.csv")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert len(stores) == 898
    assert int(stores["in_model"].sum()) == 888
    assert int((stores["sku_count"] < 10).sum()) == 10
    assert set(stores.loc[~stores["in_model"], "quadrant"]) == {"不参与（SKU<10）"}
    counts = stores.loc[stores["in_model"], "quadrant"].value_counts().to_dict()
    assert counts == {
        "Q1 高规模·相对高效率": 261, "Q2 高规模·相对低效率": 183,
        "Q3 低规模·相对高效率": 183, "Q4 低规模·相对低效率": 261,
    }
    m = summary["model"]
    assert m["slope"] == pytest.approx(0.054567, abs=1e-5)
    assert m["ci_low"] == pytest.approx(0.044180, abs=1e-5)
    assert m["ci_high"] == pytest.approx(0.064954, abs=1e-5)
    assert m["high_influence_count"] == 48
    assert m["fit_status"] == "ok_with_caution"
    assert len(sens) == 4
    assert (sens["slope"] > 0).all()
    assert (sens["same_quadrant_share_vs_main"] >= 0.80).all()
    assert len(comp) == 5
