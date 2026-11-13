import duckdb
import numpy as np
import pandas as pd
import pytest

from freshretail.analysis import p3_city


def _con():
    c = duckdb.connect()
    c.execute("""
        CREATE TABLE clean (
            city_id INT, store_id INT, product_id INT, first_category_id INT,
            dt DATE, sales_index DOUBLE, stockout_day_flag BOOLEAN,
            stockout_hours_6_22 INT
        )
    """)
    c.execute("""
        INSERT INTO clean VALUES
        (1,1,1,1,'2024-01-01',10,FALSE,0),
        (1,1,1,1,'2024-01-02',10,FALSE,0),
        (1,1,2,2,'2024-01-01',5,TRUE,4),
        (1,1,2,2,'2024-01-02',5,FALSE,0),
        (1,2,1,1,'2024-01-01',20,FALSE,0),
        (1,2,1,1,'2024-01-02',20,FALSE,0),
        (1,2,2,2,'2024-01-01',10,FALSE,0),
        (1,2,2,2,'2024-01-02',10,FALSE,0),
        (2,3,1,1,'2024-01-01',1,FALSE,0),
        (2,3,1,1,'2024-01-02',1,FALSE,0)
    """)
    return c


def _store_frame():
    return pd.DataFrame({
        "city_id": [1, 1, 2],
        "store_id": [1, 2, 3],
        "total_index": [30.0, 60.0, 2.0],
        "per_day_index": [15.0, 30.0, 1.0],
        "stockout_sku_day_rate": [0.25, 0.0, 0.0],
    })


def test_city_core_denominators():
    out = p3_city.city_core(_con()).set_index("city_id")
    assert out.loc[1, "store_count"] == 2
    assert out.loc[1, "sku_union"] == 2
    assert out.loc[1, "observed_days"] == 2
    assert out.loc[1, "store_days"] == 4
    assert out.loc[1, "total_index"] == pytest.approx(90.0)
    assert out.loc[1, "city_store_day_avg"] == pytest.approx(22.5)
    assert out.loc[1, "zero_rate"] == pytest.approx(0.0)
    assert out.loc[1, "stockout_day_rate"] == pytest.approx(1 / 8)
    assert out.loc[1, "stockout_hour_rate"] == pytest.approx(4 / (16 * 8))
    assert out.loc[2, "store_days"] == 2
    assert out.loc[2, "city_store_day_avg"] == pytest.approx(1.0)


def test_city_sku_per_store_and_category():
    con = _con()
    sku = p3_city.city_sku_store_stats(con).set_index("city_id")
    # product 1 在每家店出现 2 天，仍只计 1 个 SKU；city1 有 product 1/2，故均值为 2
    assert sku.loc[1, "sku_per_store_mean"] == pytest.approx(2.0)
    assert sku.loc[1, "sku_per_store_median"] == pytest.approx(2.0)
    assert sku.loc[2, "sku_per_store_mean"] == pytest.approx(1.0)

    cat = p3_city.city_category_stats(con).set_index("city_id")
    assert cat.loc[1, "category_hhi"] == pytest.approx(5 / 9)
    assert cat.loc[1, "category_count"] == 2
    assert cat.loc[1, "top_category_share"] == pytest.approx(2 / 3)
    assert cat.loc[2, "category_hhi"] == pytest.approx(1.0)


def test_store_distribution_and_concentration():
    store = _store_frame()
    dist = p3_city.store_distribution(store).set_index("city_id")
    # city1 两家店，top10% 向上取整为 1 家，top1 份额 = 60/90
    assert dist.loc[1, "top10pct_store_share"] == pytest.approx(60 / 90)
    assert dist.loc[1, "top1_store_share"] == pytest.approx(60 / 90)
    assert dist.loc[1, "store_day_median"] == pytest.approx(22.5)


def test_finalize_small_city_and_ranks(monkeypatch):
    monkeypatch.setattr(p3_city, "SMALL_CITY_THRESHOLD", 2)
    con = _con()
    core = p3_city.city_core(con)
    sku = p3_city.city_sku_store_stats(con)
    cat = p3_city.city_category_stats(con)
    store = _store_frame()
    dist = p3_city.store_distribution(store)
    stock = p3_city.store_stockout_distribution(store)
    base = core[["city_id", "store_count", "store_days", "total_index"]].copy()
    base["per_store_day_mean"] = core["city_store_day_avg"].values
    base["per_store_day_median"] = [22.5, 1.0]
    base["stockout_sku_day_rate"] = [0.125, 0.0]
    base["store_day_any_stockout_rate"] = [1.0, 0.0]
    base["promo_rate"] = [0.0, 0.0]
    base["store_cv"] = [0.0, 0.0]
    base["share"] = base["total_index"] / base["total_index"].sum()
    base = base[["city_id", "store_count", "store_days", "total_index", "per_store_day_mean",
                 "per_store_day_median", "stockout_sku_day_rate", "store_day_any_stockout_rate",
                 "promo_rate", "store_cv", "share"]]
    out = p3_city.finalize_city_table(base, core, sku, cat, dist, stock).set_index("city_id")
    assert out.loc[1, "small_city"] == False
    assert out.loc[1, "rank_store_day"] == 1
    assert np.isnan(out.loc[2, "rank_store_day_eligible"])  # 1 店 <10，不参与强排名
    assert out["share_pct"].sum() == pytest.approx(100.0)


def test_p3a_regression_numbers_unchanged():
    from pathlib import Path
    b = Path(__file__).resolve().parents[1] / "data" / "analysis" / "p3"
    city = pd.read_csv(b / "a1_city_metrics.csv")
    corr = pd.read_csv(b / "a2_city_correlations.csv").set_index("relation")

    assert len(city) == 18
    c0 = city.set_index("city_id").loc[0]
    assert c0["store_count"] == 290
    assert c0["city_total_index"] == pytest.approx(2374623.838, abs=1e-3)
    assert c0["city_store_day_avg"] == pytest.approx(90.981756, abs=1e-5)
    assert c0["sku_union"] == 449
    assert int(city["small_city"].sum()) == 5
    assert city["share_pct"].sum() == pytest.approx(100.0, abs=1e-6)
    assert corr.loc["total_vs_store_count", "spearman_all"] == pytest.approx(0.9355, abs=1e-3)
    assert corr.loc["store_day_vs_store_count", "spearman_all"] == pytest.approx(0.0960, abs=1e-3)
    assert corr.loc["store_day_vs_sku_per_store", "spearman_all"] == pytest.approx(0.9670, abs=1e-3)
    assert c0["stockout_day_rate"] == pytest.approx(0.440337, abs=1e-5)
    assert c0["stockout_hour_rate"] == pytest.approx(0.192179, abs=1e-5)
    assert corr.loc["store_day_vs_stockout_hour", "spearman_all"] == pytest.approx(-0.5315, abs=1e-3)
    assert corr.loc["zero_vs_stockout_hour", "spearman_all"] == pytest.approx(0.6099, abs=1e-3)
    assert (corr["n_all"] == 18).all()


def test_bootstrap_metadata():
    import json
    from pathlib import Path
    b = Path(__file__).resolve().parents[1] / "data" / "analysis" / "p3"
    summary = json.loads((b / "summary.json").read_text(encoding="utf-8"))
    assert summary["bootstrap"]["n_boot"] == 1000
    assert summary["bootstrap"]["seed"] == 42
    assert summary["bootstrap"]["unit"] == "city"
    assert summary["bootstrap"]["n_cities"] == 18
    assert "90 天" in summary["sku_definition"]
