import duckdb
import pytest

from freshretail import config, metrics

RAW_AVAILABLE = config.TRAIN_PATH.exists()
requires_raw = pytest.mark.skipif(
    not RAW_AVAILABLE,
    reason=(
        "需要原始数据 data/raw/freshretailnet50k/train.parquet；"
        "请按 data/README.md 下载并校验，或设置 FRESH_RETAIL_RAW_DIR"
    ),
)


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute(
        """
        CREATE TABLE clean (
            city_id INT, store_id INT, product_id INT, dt DATE,
            sales_index DOUBLE, sales_zero_flag BOOLEAN,
            stockout_day_flag BOOLEAN, stockout_hours_6_22 INT,
            discount_valid BOOLEAN, discount_raw DOUBLE, promo_flag BOOLEAN,
            hours_sale DOUBLE[], avg_temperature DOUBLE, precpt DOUBLE
        )
        """
    )
    c.execute(
        """
        INSERT INTO clean VALUES
        (0,0,0,'2024-03-28',10,FALSE,FALSE,0,TRUE,1.0,FALSE,[1.0,2.0],20.0,0.0),
        (0,0,1,'2024-03-28', 5,FALSE,TRUE ,8,TRUE ,0.8,TRUE ,[0.5,0.5],20.0,0.0),
        (0,1,0,'2024-03-28',20,FALSE,FALSE,0,TRUE ,1.0,FALSE,[2.0,4.0],20.0,0.0),
        (0,1,1,'2024-03-28',10,FALSE,TRUE ,4,TRUE ,1.0,FALSE,[1.0,1.0],20.0,0.0),
        (0,0,0,'2024-03-29',10,FALSE,FALSE,0,TRUE ,1.0,FALSE,[1.0,2.0],20.0,0.0),
        (0,0,1,'2024-03-29',10,FALSE,FALSE,0,TRUE ,1.0,FALSE,[1.0,1.0],20.0,0.0),
        (0,1,0,'2024-03-29',20,FALSE,FALSE,0,TRUE ,1.0,FALSE,[2.0,4.0],20.0,0.0),
        (0,1,1,'2024-03-29',10,FALSE,FALSE,0,TRUE ,1.0,FALSE,[1.0,1.0],20.0,0.0)
        """
    )
    return c


def test_daily_summary(con):
    df = metrics.daily_summary(con, "clean").set_index("dt")
    assert df.loc["2024-03-28", "sales_index_total"] == pytest.approx(45.0)
    assert df.loc["2024-03-29", "sales_index_total"] == pytest.approx(50.0)
    assert df.loc["2024-03-28", "store_count"] == 2
    assert df.loc["2024-03-28", "per_store_index"] == pytest.approx(22.5)


def test_product_summary(con):
    df = metrics.product_summary(con, "clean").set_index("product_id")
    assert df.loc[0, "total_index"] == pytest.approx(60.0)
    assert df.loc[0, "store_count"] == 2
    assert df.loc[0, "series_days"] == 4
    assert df.loc[0, "per_series_day"] == pytest.approx(15.0)
    assert df.loc[0, "active_day_rate"] == pytest.approx(1.0)
    assert df.loc[1, "total_index"] == pytest.approx(35.0)
    assert df.loc[1, "stockout_day_rate"] == pytest.approx(0.5)
    assert df.loc[1, "promo_day_rate"] == pytest.approx(0.25)


def test_city_summary(con):
    df = metrics.city_summary(con, "clean").set_index("city_id")
    assert df.loc[0, "store_count"] == 2
    assert df.loc[0, "store_days"] == 4
    assert df.loc[0, "total_index"] == pytest.approx(95.0)
    assert df.loc[0, "per_store_day_mean"] == pytest.approx(23.75)
    assert df.loc[0, "stockout_sku_day_rate"] == pytest.approx(0.25)
    assert df.loc[0, "store_day_any_stockout_rate"] == pytest.approx(0.5)
    assert df.loc[0, "share"] == pytest.approx(1.0)
    assert df.loc[0, "store_cv"] == pytest.approx(6.25 / 23.75)


def test_store_summary(con):
    df = metrics.store_summary(con, "clean").set_index("store_id")
    assert df.loc[0, "total_index"] == pytest.approx(35.0)
    assert df.loc[0, "per_day_index"] == pytest.approx(17.5)
    assert df.loc[1, "per_day_index"] == pytest.approx(30.0)
    assert df.loc[1, "store_days"] == 2


def test_stockout_gradient(con):
    df = metrics.stockout_gradient(con, "clean").set_index("stockout_bin")
    assert df.loc["1-4", "series_days"] == 1
    assert df.loc["1-4", "avg_ratio_to_no_stockout"] == pytest.approx(1.0)
    assert df.loc["5-8", "avg_ratio_to_no_stockout"] == pytest.approx(0.5)


def test_promo_paired(con):
    df = metrics.promo_paired(con, "clean").iloc[0]
    assert df["series_count"] == 1
    assert df["avg_ratio"] == pytest.approx(0.5)


def test_hour_profile(con):
    df = metrics.hour_profile(con, "clean").set_index("hour")
    assert df.loc[0, "sales_index"] == pytest.approx(9.5)
    assert df.loc[1, "sales_index"] == pytest.approx(15.5)
    assert df.loc[1, "share"] == pytest.approx(15.5 / 25.0)


def test_weather_bins(con):
    df = metrics.weather_bins(con, "clean").iloc[0]
    assert df["temp_bin"] == "20-25"
    assert df["store_days"] == 4
    assert df["avg_store_day_index"] == pytest.approx(23.75)


def test_anomaly_days_and_health_score():
    import pandas as pd
    daily = pd.DataFrame({"sales_index_total": [10, 11, 9, 10, 11, 9, 10, 11, 9, 100]})
    out = metrics.anomaly_days(daily, z_threshold=3.0)
    assert out["is_anomaly"].sum() == 1
    assert bool(out.loc[9, "is_anomaly"]) is True

    stores = pd.DataFrame({
        "store_id": [1, 2, 3],
        "per_day_index": [10.0, 20.0, 30.0],
        "stockout_sku_day_rate": [0.5, 0.2, 0.0],
        "promo_rate": [0.5, 0.2, 0.0],
        "cv": [0.5, 0.2, 0.1],
    })
    scored = metrics.health_score(stores)
    assert scored["health_score"].between(0, 100).all()
    assert scored.loc[2, "health_score"] > scored.loc[0, "health_score"]


@pytest.mark.requires_raw
@requires_raw
def test_real_data_stock_window_contract():
    """真实数据抽样：缺货小时数必须等于 hours_stock_status[6:22] 之和。"""
    p = str(config.TRAIN_PATH).replace("\\", "/")
    c = duckdb.connect()
    bad = c.execute(
        f"""
        SELECT count(*) FROM (
            SELECT list_sum(list_slice(hours_stock_status, 7, 22)) AS s,
                   stock_hour6_22_cnt AS c
            FROM read_parquet('{p}') LIMIT 50000
        ) WHERE s <> c
        """
    ).fetchone()[0]
    assert bad == 0

    bad_hours = c.execute(
        f"""
        SELECT count(*) FROM (
            SELECT list_sum(hours_sale) AS s, sale_amount AS a
            FROM read_parquet('{p}') LIMIT 50000
        ) WHERE abs(s - a) > 1e-9
        """
    ).fetchone()[0]
    assert bad_hours == 0
