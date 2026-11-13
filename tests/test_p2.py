import duckdb
import numpy as np
import pandas as pd
import pytest

from freshretail.analysis import p2

CLEAN_AVAILABLE = p2.CLEAN.exists()
requires_clean = pytest.mark.skipif(
    not CLEAN_AVAILABLE,
    reason=(
        "需要 data/derived/clean_train.parquet；"
        "请先运行 python scripts/build_derived.py（需要原始数据）"
    ),
)


def _sku_frame():
    return pd.DataFrame({
        "product_id": [1, 2, 3, 4],
        "total_index": [100.0, 50.0, 25.0, 25.0],
        "per_series_day": [10.0, 5.0, 2.5, 2.5],
        "store_count": [10, 8, 2, 1],
        "zero_rate": [0.01, 0.02, 0.30, 0.40],
        "cv_series_median": [0.3, 0.4, 1.5, 2.0],
        "anomaly_rate": [0.0, 0.0, 0.2, 0.3],
        "hhi": [0.1, 0.12, 1.0, 1.0],
        "promo_rate": [0.5, 0.5, 0.2, 0.1],
    })


def test_share_and_rank():
    d = p2.add_sku_metrics(_sku_frame())
    assert d.loc[0, "total_share_pct"] == pytest.approx(50.0)
    assert d.loc[1, "cum_share_pct"] == pytest.approx(75.0)
    assert d["rank_scale"].tolist() == [1, 2, 3, 4]
    assert d.loc[3, "rank_diff"] == 1


def test_pareto():
    d = p2.add_sku_metrics(_sku_frame())
    out = p2.pareto(d)
    assert out["top10pct_share_pct"] == pytest.approx(50.0)
    assert out["skus_to_80pct"] == 3


def test_coverage_sensitivity_changes_top_list():
    rows = []
    for i in range(6):
        rows.append({"product_id": i, "total_index": 10.0 + i, "per_series_day": 9.0 - i * 0.1,
                     "store_count": 1})
    for i in range(6, 12):
        rows.append({"product_id": i, "total_index": 100.0 + i, "per_series_day": 2.0 - (i - 6) * 0.1,
                     "store_count": 100})
    d = pd.DataFrame(rows)
    out = p2.coverage_sensitivity(d, [1, 5]).set_index("min_store_count")
    assert out.loc[1, "sku_count"] == 12
    assert out.loc[5, "sku_count"] == 6
    assert out.loc[5, "top10_eff_overlap_with_baseline"] == 4
    assert out.loc[5, "top10_eff_mean_store_count"] == 100


def test_stability_tiers():
    d = p2.stability_tiers(_sku_frame())
    assert d.loc[0, "stability_tier"] == "稳定（低零销/低波动）"
    assert d.loc[1, "stability_tier"] == "稳定（低零销/低波动）"
    assert d.loc[2, "stability_tier"] == "不稳定（高零销/高波动）"


def test_anomaly_flags_ignore_single_store_hhi():
    rows = []
    for i in range(20):
        rows.append({
            "product_id": i,
            "store_count": 1 if i < 10 else 10,
            "hhi": 1.0 if i < 10 else 0.1,
            "cv_series_median": 0.5,
            "zero_rate": 0.02,
            "anomaly_rate": 0.0,
            "total_index": 10.0,
            "per_series_day": 1.0,
            "promo_rate": 0.5,
        })
    d = p2.flag_anomalies(pd.DataFrame(rows))
    assert not d.loc[d["store_count"] == 1, "flag_store_concentration"].any()
    assert not d["flag_store_concentration"].any()


def test_head_tail_shape():
    d = p2.add_sku_metrics(_sku_frame())
    out = p2.head_tail(d)
    assert set(out["group"]) == {"头部 Top20%", "长尾 Bottom50%"}
    assert out.loc[out["group"] == "头部 Top20%", "sku_count"].iloc[0] == 1


def _category_con():
    c = duckdb.connect()
    c.execute(
        """
        CREATE TABLE clean (
            first_category_id INT, second_category_id INT,
            product_id INT, store_id INT, dt DATE,
            sales_index DOUBLE, promo_flag BOOLEAN
        )
        """
    )
    c.execute(
        """
        INSERT INTO clean VALUES
        (1,10,1,1,'2024-01-01',10,FALSE),
        (1,10,1,1,'2024-01-02',10,FALSE),
        (1,10,1,2,'2024-01-01',10,FALSE),
        (1,10,1,2,'2024-01-02',10,FALSE),
        (1,10,2,1,'2024-01-01',5,FALSE),
        (1,10,2,1,'2024-01-02',5,FALSE),
        (1,10,2,2,'2024-01-01',5,FALSE),
        (1,10,2,2,'2024-01-02',5,FALSE),
        (2,20,3,3,'2024-01-01',1,FALSE),
        (2,20,3,3,'2024-01-02',1,FALSE)
        """
    )
    return c


def _category_sku():
    return pd.DataFrame({
        "product_id": [1, 2, 3],
        "first_category_id": [1, 1, 2],
        "second_category_id": [10, 10, 20],
        "cv_series_median": [0.5, 0.5, 0.4],
    })


def test_category_two_efficiency_metrics():
    con = _category_con()
    m1 = pd.DataFrame({"raw_id": [1, 2], "display_code": ["C01", "C02"]})
    out = p2.category_table(con, "first_category_id", _category_sku(), m1).set_index("display_code")
    # C01: 2 个 SKU × 2 家门店 × 2 天 = 8 条 SKU-门店-日
    assert out.loc["C01", "store_count"] == 2
    assert out.loc["C01", "store_days"] == 4
    assert out.loc["C01", "sku_store_days"] == 8
    assert out.loc["C01", "category_sku_store_day_avg"] == pytest.approx(60 / 8)
    assert out.loc["C01", "category_store_day_avg"] == pytest.approx(60 / 4)
    assert out.loc["C01", "observed_days_avg"] == pytest.approx(2.0)
    assert out.loc["C01", "rank_store_day_avg"] == 1
    assert out.loc["C01", "rank_sku_store_day_avg"] == 1
    assert out.loc["C02", "category_store_day_avg"] == pytest.approx(1.0)


def test_category_metrics_consistent_across_levels():
    con = _category_con()
    sku = _category_sku()
    m1 = pd.DataFrame({"raw_id": [1, 2], "display_code": ["C01", "C02"]})
    m2 = pd.DataFrame({"raw_id": [10, 20], "display_code": ["S001", "S002"]})
    l1 = p2.category_table(con, "first_category_id", sku, m1).set_index("raw_id")
    l2 = p2.category_table(con, "second_category_id", sku, m2).set_index("raw_id")
    assert l1.loc[1, "total_index"] == pytest.approx(l2.loc[10, "total_index"])
    assert l1.loc[1, "store_days"] == l2.loc[10, "store_days"]
    assert l1.loc[1, "category_store_day_avg"] == pytest.approx(l2.loc[10, "category_store_day_avg"])
    assert l1.loc[1, "category_sku_store_day_avg"] == pytest.approx(l2.loc[10, "category_sku_store_day_avg"])


def test_category_uses_actual_days_not_90():
    con = _category_con()
    m1 = pd.DataFrame({"raw_id": [1, 2], "display_code": ["C01", "C02"]})
    out = p2.category_table(con, "first_category_id", _category_sku(), m1).set_index("display_code")
    # 数据只有 2 天；若写死 90，store_days 会变成 180
    assert out.loc["C01", "store_days"] == 4
    assert out.loc["C01", "observed_days_avg"] == 2


def test_p2_audited_numbers_unchanged():
    from pathlib import Path
    b = Path(__file__).resolve().parents[1] / "data" / "analysis" / "p2"
    t1 = pd.read_csv(b / "t1_sku_metrics.csv")
    t7 = pd.read_csv(b / "t7_coverage_sensitivity.csv")

    assert len(t1) == 865
    assert t1["store_count"].median() == 10
    assert int((t1["store_count"] <= 2).sum()) == 230
    assert t1["total_index"].corr(t1["store_count"], method="spearman") == pytest.approx(0.9778, abs=1e-3)
    assert t1["total_index"].corr(t1["per_series_day"], method="spearman") == pytest.approx(0.5977, abs=1e-3)
    assert t1.head(86)["total_share_pct"].sum() == pytest.approx(72.2992, abs=1e-3)
    assert t1["zero_rate"].median() == pytest.approx(0.029798, abs=1e-5)
    assert t1["cv_series_median"].median() == pytest.approx(0.541587, abs=1e-5)
    assert int(t1["anomaly_days"].sum()) == 62999
    assert t1["risk_flag_count"].value_counts().sort_index().to_dict() == {0: 748, 1: 82, 2: 23, 3: 12}
    assert int(t7.iloc[0]["sku_count"]) == 865
    assert int(t7.iloc[-1]["sku_count"]) == 153
    assert int(t7.iloc[-1]["top10_eff_overlap_with_baseline"]) == 3


@pytest.mark.requires_clean
@requires_clean
def test_mad_zero_series_behavior_unchanged():
    p = str(p2.CLEAN).replace("\\", "/")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW clean AS SELECT * FROM read_parquet('{p}')")
    mad0 = con.execute("""
        WITH b AS (
            SELECT product_id, store_id, sales_index,
                   median(sales_index) OVER (PARTITION BY product_id, store_id) AS med
            FROM clean
        ),
        c AS (
            SELECT DISTINCT product_id, store_id,
                   median(abs(sales_index - med)) OVER (PARTITION BY product_id, store_id) AS mad
            FROM b
        )
        SELECT COUNT(*) FROM c WHERE mad = 0
    """).fetchone()[0]
    assert int(mad0) == 75
