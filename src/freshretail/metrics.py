"""指标计算：只产出聚合结果，不做可视化、不做建模。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def daily_summary(con, table: str) -> pd.DataFrame:
    sql = f"""
    SELECT dt::DATE AS dt,
           SUM(sales_index) AS sales_index_total,
           COUNT(DISTINCT store_id) AS store_count,
           COUNT(*) AS series_rows,
           SUM(sales_index) / COUNT(DISTINCT store_id) AS per_store_index,
           AVG(sales_index) AS per_series_index,
           AVG(CASE WHEN sales_zero_flag THEN 1.0 ELSE 0 END) AS zero_sales_rate,
           AVG(CASE WHEN stockout_day_flag THEN 1.0 ELSE 0 END) AS stockout_day_rate
    FROM {table}
    GROUP BY 1
    ORDER BY 1
    """
    return con.execute(sql).df()


def store_day(con, table: str) -> pd.DataFrame:
    sql = f"""
    SELECT dt::DATE AS dt,
           store_id,
           SUM(sales_index) AS sales_index,
           SUM(stockout_hours_6_22) AS stockout_hours,
           MAX(stockout_day_flag::INT) AS any_sku_stockout_flag,
           AVG(CASE WHEN stockout_day_flag THEN 1.0 ELSE 0 END) AS stockout_sku_rate,
           AVG(CASE WHEN discount_valid THEN discount_raw END) AS avg_discount,
           AVG(CASE WHEN promo_flag THEN 1.0 ELSE 0 END) AS promo_rate
    FROM {table}
    GROUP BY 1, 2
    """
    return con.execute(sql).df()


def store_summary(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH sd AS (
        SELECT dt, store_id, MAX(city_id) AS city_id,
               SUM(sales_index) AS idx,
               AVG(CASE WHEN stockout_day_flag THEN 1.0 ELSE 0 END) AS sr,
               AVG(CASE WHEN promo_flag THEN 1.0 ELSE 0 END) AS pr
        FROM {table}
        GROUP BY 1, 2
    )
    SELECT store_id,
           MAX(city_id) AS city_id,
           SUM(idx) AS total_index,
           AVG(idx) AS per_day_index,
           STDDEV_POP(idx) / NULLIF(AVG(idx), 0) AS cv,
           AVG(sr) AS stockout_sku_day_rate,
           AVG(CASE WHEN sr > 0 THEN 1.0 ELSE 0 END) AS store_day_any_stockout_rate,
           AVG(pr) AS promo_rate,
           COUNT(*) AS store_days
    FROM sd
    GROUP BY store_id
    """
    return con.execute(sql).df()


def product_summary(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH agg AS (
        SELECT product_id,
               SUM(sales_index) AS total_index,
               COUNT(DISTINCT store_id) AS store_count,
               COUNT(*) AS series_days,
               SUM(sales_index) / COUNT(*) AS per_series_day,
               AVG(CASE WHEN sales_index > 0 THEN 1.0 ELSE 0 END) AS active_day_rate,
               AVG(CASE WHEN stockout_day_flag THEN 1.0 ELSE 0 END) AS stockout_day_rate,
               AVG(CASE WHEN promo_flag THEN 1.0 ELSE 0 END) AS promo_day_rate
        FROM {table}
        GROUP BY 1
    ),
    ser AS (
        SELECT product_id, store_id,
               STDDEV_POP(sales_index) / NULLIF(AVG(sales_index), 0) AS cv
        FROM {table}
        GROUP BY 1, 2
    ),
    ser2 AS (
        SELECT product_id, MEDIAN(cv) AS cv_series_median FROM ser GROUP BY 1
    )
    SELECT a.*, s.cv_series_median
    FROM agg a LEFT JOIN ser2 s USING (product_id)
    """
    return con.execute(sql).df()


def city_summary(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH sd AS (
        SELECT city_id, store_id, dt,
               SUM(sales_index) AS idx,
               AVG(CASE WHEN stockout_day_flag THEN 1.0 ELSE 0 END) AS sr,
               AVG(CASE WHEN promo_flag THEN 1.0 ELSE 0 END) AS pr
        FROM {table}
        GROUP BY 1, 2, 3
    ),
    store_avg AS (
        SELECT city_id, store_id, AVG(idx) AS avg_idx
        FROM sd GROUP BY 1, 2
    ),
    city_agg AS (
        SELECT city_id,
               COUNT(DISTINCT store_id) AS store_count,
               COUNT(*) AS store_days,
               SUM(idx) AS total_index,
               AVG(idx) AS per_store_day_mean,
               MEDIAN(idx) AS per_store_day_median,
               AVG(sr) AS stockout_sku_day_rate,
               AVG(CASE WHEN sr > 0 THEN 1.0 ELSE 0 END) AS store_day_any_stockout_rate,
               AVG(pr) AS promo_rate
        FROM sd GROUP BY 1
    ),
    disp AS (
        SELECT city_id,
               STDDEV_POP(avg_idx) / NULLIF(AVG(avg_idx), 0) AS store_cv
        FROM store_avg GROUP BY 1
    )
    SELECT c.*, d.store_cv,
           c.total_index / SUM(c.total_index) OVER () AS share
    FROM city_agg c LEFT JOIN disp d USING (city_id)
    ORDER BY city_id
    """
    return con.execute(sql).df()


def category_day(con, table: str) -> pd.DataFrame:
    sql = f"""
    SELECT dt::DATE AS dt,
           MAX(first_category_id) AS first_category_id,
           MAX(second_category_id) AS second_category_id,
           third_category_id,
           SUM(sales_index) AS sales_index
    FROM {table}
    GROUP BY 1, 4
    ORDER BY 1, 4
    """
    return con.execute(sql).df()


def hour_profile(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH h AS (
        SELECT unnest(hours_sale) AS v,
               generate_subscripts(hours_sale, 1) - 1 AS hour
        FROM {table}
    )
    SELECT hour, SUM(v) AS sales_index,
           SUM(v) / SUM(SUM(v)) OVER () AS share
    FROM h GROUP BY 1 ORDER BY 1
    """
    return con.execute(sql).df()


def hour_weekday(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH h AS (
        SELECT dt::DATE AS dt,
               unnest(hours_sale) AS v,
               generate_subscripts(hours_sale, 1) - 1 AS hour
        FROM {table}
    )
    SELECT (dayofweek(dt) + 6) % 7 AS weekday,
           hour,
           SUM(v) AS sales_index
    FROM h GROUP BY 1, 2 ORDER BY 1, 2
    """
    return con.execute(sql).df()


def stockout_gradient(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH base AS (
        SELECT store_id, product_id, dt, sales_index, stockout_hours_6_22,
               AVG(CASE WHEN stockout_hours_6_22 = 0 THEN sales_index END)
                   OVER (PARTITION BY store_id, product_id) AS base_mean
        FROM {table}
    ),
    x AS (
        SELECT CASE
                   WHEN stockout_hours_6_22 = 0 THEN '0'
                   WHEN stockout_hours_6_22 <= 4 THEN '1-4'
                   WHEN stockout_hours_6_22 <= 8 THEN '5-8'
                   WHEN stockout_hours_6_22 <= 12 THEN '9-12'
                   ELSE '13-16'
               END AS stockout_bin,
               sales_index, base_mean
        FROM base
        WHERE base_mean IS NOT NULL AND base_mean > 0
    )
    SELECT stockout_bin,
           COUNT(*) AS series_days,
           AVG(sales_index) AS avg_sales_index,
           MEDIAN(sales_index) AS median_sales_index,
           AVG(sales_index / base_mean) AS avg_ratio_to_no_stockout
    FROM x GROUP BY 1 ORDER BY 1
    """
    return con.execute(sql).df()


def promo_paired(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH s AS (
        SELECT store_id, product_id,
               AVG(CASE WHEN promo_flag THEN sales_index END) AS promo_mean,
               AVG(CASE WHEN NOT promo_flag AND discount_valid THEN sales_index END) AS nonpromo_mean,
               COUNT(CASE WHEN promo_flag THEN 1 END) AS promo_days,
               COUNT(CASE WHEN NOT promo_flag AND discount_valid THEN 1 END) AS nonpromo_days
        FROM {table}
        GROUP BY 1, 2
    )
    SELECT COUNT(*) AS series_count,
           AVG(promo_mean) AS avg_promo_index,
           AVG(nonpromo_mean) AS avg_nonpromo_index,
           AVG(promo_mean / NULLIF(nonpromo_mean, 0)) AS avg_ratio,
           MEDIAN(promo_mean / NULLIF(nonpromo_mean, 0)) AS median_ratio
    FROM s
    WHERE promo_mean IS NOT NULL AND nonpromo_mean IS NOT NULL
    """
    return con.execute(sql).df()


def weather_bins(con, table: str) -> pd.DataFrame:
    sql = f"""
    WITH sd AS (
        SELECT store_id, dt,
               MAX(avg_temperature) AS t, MAX(precpt) AS p,
               SUM(sales_index) AS idx
        FROM {table} GROUP BY 1, 2
    )
    SELECT CASE
               WHEN t < 15 THEN '<15'
               WHEN t < 20 THEN '15-20'
               WHEN t < 25 THEN '20-25'
               WHEN t < 30 THEN '25-30'
               ELSE '>=30'
           END AS temp_bin,
           COUNT(*) AS store_days,
           AVG(idx) AS avg_store_day_index
    FROM sd GROUP BY 1 ORDER BY 1
    """
    return con.execute(sql).df()


def anomaly_days(daily: pd.DataFrame, z_threshold: float = 3.0) -> pd.DataFrame:
    """对日度总指数做稳健 z 检验（中位数/MAD）。"""
    out = daily.copy()
    x = out["sales_index_total"].astype(float)
    med = x.median()
    mad = (x - med).abs().median()
    out["robust_z"] = (x - med) / (1.4826 * mad) if mad > 0 else np.nan
    out["is_anomaly"] = out["robust_z"].abs() > z_threshold
    return out


def health_score(store_summary_df: pd.DataFrame) -> pd.DataFrame:
    """门店运营健康度：4 维 min-max 标准化后加权，仅作分群参考。"""
    out = store_summary_df.copy()

    def norm(s: pd.Series, reverse: bool = False) -> pd.Series:
        lo, hi = s.min(), s.max()
        if hi == lo:
            return pd.Series(0.5, index=s.index)
        z = (s - lo) / (hi - lo)
        return 1 - z if reverse else z

    out["score_sales"] = norm(out["per_day_index"])
    out["score_stockout"] = norm(out["stockout_sku_day_rate"], reverse=True)
    out["score_promo_dependence"] = norm(out["promo_rate"], reverse=True)
    out["score_stability"] = norm(out["cv"], reverse=True)
    out["health_score"] = 100 * (
        0.40 * out["score_sales"]
        + 0.25 * out["score_stockout"]
        + 0.20 * out["score_stability"]
        + 0.15 * out["score_promo_dependence"]
    )
    out["health_tier"] = pd.cut(
        out["health_score"], bins=[-0.1, 40, 60, 80, 100.1],
        labels=["低", "中", "良", "优"]
    )
    return out


def metric_catalog() -> list[dict]:
    """指标字典：供报告与追溯使用。"""
    return [
        {"id": "M1-01", "name": "样本总销量指数", "formula": "SUM(sales_index) BY dt",
         "fields": "sale_amount", "grain": "日", "note": "样本内 50k 序列合计"},
        {"id": "M1-02", "name": "单店日均销量指数", "formula": "SUM(sales_index)/COUNT(DISTINCT store_id)",
         "fields": "sale_amount,store_id", "grain": "日", "note": "横向对比主指标"},
        {"id": "M1-03", "name": "单序列日均销量指数", "formula": "SUM(sales_index)/COUNT(*)",
         "fields": "sale_amount", "grain": "序列", "note": "商品/门店对对比"},
        {"id": "M1-04", "name": "日环比", "formula": "x_t/x_{t-1}-1", "fields": "sale_amount", "grain": "日",
         "note": "需处理零值"},
        {"id": "M1-07", "name": "小时销量份额", "formula": "SUM(hours_sale[h])/SUM(hours_sale)",
         "fields": "hours_sale", "grain": "小时", "note": "0-23"},
        {"id": "M1-10", "name": "星期效应", "formula": "均值(某星期)/均值(全期)",
         "fields": "dt,sale_amount", "grain": "星期", "note": "周一=0"},
        {"id": "M4-03", "name": "SKU 单店日均销量指数", "formula": "SUM(sales_index)/COUNT(*)",
         "fields": "sale_amount,product_id", "grain": "SKU", "note": "受覆盖门店数影响，需同时报告 store_count"},
        {"id": "M4-04", "name": "SKU 动销率", "formula": "AVG(sales_index>0)", "fields": "sale_amount,dt",
         "grain": "SKU-门店", "note": "零销可能因缺货"},
        {"id": "M4-06", "name": "SKU 缺货天数占比", "formula": "AVG(stockout_day_flag)",
         "fields": "stock_hour6_22_cnt", "grain": "SKU-门店", "note": "分母为 90 天"},
        {"id": "M4-10", "name": "促销日销量比", "formula": "促销日均值/非促销日均值（同店同 SKU）",
         "fields": "discount,sale_amount", "grain": "序列", "note": "仅关联，不称弹性"},
        {"id": "M5-03", "name": "城市单店日均销量指数", "formula": "SUM/门店-日数",
         "fields": "city_id,sale_amount", "grain": "城市", "note": "必须同时报告门店数"},
        {"id": "M5-07", "name": "城市缺货率（SKU-日口径）", "formula": "AVG(stockout_day_flag)",
         "fields": "stock_hour6_22_cnt", "grain": "城市", "note": "6-21 点口径；另保留门店日任一缺货率"},
        {"id": "M6-01", "name": "缺货日销量差异", "formula": "同店同 SKU 缺货日/非缺货日均值",
         "fields": "stock_hour6_22_cnt,sale_amount", "grain": "序列-日", "note": "差异不等于因果"},
        {"id": "M6-03", "name": "缺货销量变化区间", "formula": "以非缺货日均值为基准的比值区间",
         "fields": "stock_hour6_22_cnt,sale_amount", "grain": "序列-日", "note": "不提供点估计或金额损失"},
    ]
