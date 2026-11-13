"""BI-0 只读查询服务。"""

from __future__ import annotations

import csv
import io
from functools import lru_cache
from typing import Any

import pandas as pd

from . import catalog, config
from .db import ReadOnlyDB
from .models import Meta


@lru_cache(maxsize=1)
def get_db() -> ReadOnlyDB:
    return ReadOnlyDB()


def _meta(n: int = 0, sample_scope: str = "all", definitions: list[str] | None = None,
          suppressed: bool = False, display_window: str | None = None) -> Meta:
    return Meta(n=n, period=config.PERIOD_LABEL, data_version=config.data_version(),
                sample_scope=sample_scope, definitions=definitions or [],
                suppressed=suppressed, display_window=display_window)


def _records(df: pd.DataFrame) -> list[dict]:
    """把 NaN 转成 None，避免 Pydantic 把空值当作非有限数字。"""
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


def health() -> dict:
    return {"status": "ok", "data_version": config.data_version(),
            "period": config.PERIOD_LABEL, "views": get_db().view_counts()}


def catalog_data() -> dict:
    return {"metrics": catalog.load_metrics(), "pages": catalog.load_page_map(),
            "version": config.data_version()}


def filters() -> dict:
    db = get_db()
    cities = db.query_df("SELECT city_id, store_count, small_city FROM v_city ORDER BY city_id").to_dict("records")
    quadrants = [r[0] for r in db.query_df(
        "SELECT DISTINCT quadrant FROM v_store_profile WHERE quadrant IS NOT NULL ORDER BY 1").itertuples(index=False)]
    clusters = [r[0] for r in db.query_df(
        "SELECT DISTINCT cluster FROM v_store_profile WHERE cluster IN ('G1','G2','G3','G4') ORDER BY 1").itertuples(index=False)]
    categories = db.query_df(
        "SELECT display_code AS category_code, sku_count, store_count FROM v_category ORDER BY display_code").to_dict("records")
    return {
        "cities": cities, "quadrants": quadrants, "clusters": clusters,
        "risk_domains": ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"],
        "categories": categories, "sample_scopes": ["all", "risk"],
        "period": config.PERIOD_LABEL,
    }


def overview_kpis() -> tuple[list[dict], Meta]:
    db = get_db()
    s = db.query_one("""
        SELECT COUNT(*) AS stores,
               SUM(CASE WHEN profile_status='完整档案' THEN 1 ELSE 0 END) AS full_stores,
               SUM(CASE WHEN in_risk_sample IS TRUE THEN 1 ELSE 0 END) AS risk_stores,
               SUM(total_index) AS total_index,
               median(per_day_index) AS per_day_median,
               SUM(CASE WHEN multi_risk IS TRUE THEN 1 ELSE 0 END) AS multi_risk,
               COUNT(DISTINCT city_id) AS cities
        FROM v_store_profile
    """)
    skus = int(db.query_one("SELECT COUNT(*) AS n FROM v_sku")["n"])
    flagged = int(db.query_one("SELECT COUNT(*) AS n FROM v_flagged_sku")["n"])
    overall = db.query_df("SELECT metric, rate FROM v_overall").set_index("metric")["rate"].to_dict()
    r1 = float(next(v for k, v in overall.items() if "SKU-日" in k))
    r2 = float(next(v for k, v in overall.items() if "小时" in k))
    data = [
        {"key": "stores", "label": "门店数", "value": int(s["stores"]), "unit": "家",
         "metric_id": "SAMPLE-ALL", "sample_n": int(s["stores"]), "note": "全部门店"},
        {"key": "full_stores", "label": "完整档案门店", "value": int(s["full_stores"]), "unit": "家",
         "metric_id": "SAMPLE-RISK", "sample_n": int(s["full_stores"]), "note": "SKU≥10"},
        {"key": "total_index", "label": "90 天归一化销量指数", "value": float(s["total_index"]), "unit": "指数",
         "metric_id": "P1-TOTAL", "sample_n": int(s["stores"]), "note": "不是销售额/GMV"},
        {"key": "per_day_median", "label": "单店日均指数（中位）", "value": float(s["per_day_median"]), "unit": "指数/日",
         "metric_id": "P1-PER-DAY", "sample_n": int(s["stores"]), "note": "90 天"},
        {"key": "skus", "label": "SKU 数", "value": skus, "unit": "个",
         "metric_id": "P2-SKU", "sample_n": skus, "note": "链级去重"},
        {"key": "r1", "label": "SKU-日缺货率（池化）", "value": r1, "unit": "比例",
         "metric_id": "D1", "sample_n": int(s["stores"]), "note": "Σ分子/Σ分母"},
        {"key": "r2", "label": "小时槽位缺货率（池化）", "value": r2, "unit": "比例",
         "metric_id": "D6", "sample_n": int(s["stores"]), "note": "16 槽"},
        {"key": "multi_risk", "label": "多风险门店", "value": int(s["multi_risk"]), "unit": "家",
         "metric_id": "D17", "sample_n": int(s["risk_stores"]), "note": "≥2 运营域"},
        {"key": "flagged_skus", "label": "风险 SKU", "value": flagged, "unit": "个",
         "metric_id": "P2-RISK", "sample_n": skus, "note": "P2 冻结旗标"},
    ]
    return data, _meta(n=int(s["stores"]), sample_scope="all", definitions=["D1", "D6", "D17"])


def trend(start: str | None = None, end: str | None = None) -> tuple[list[dict], Meta]:
    db = get_db()
    sql = """
        SELECT CAST(dt AS VARCHAR) AS dt, sales_index_total, per_store_index,
               zero_sales_rate, stockout_day_rate
        FROM v_daily
    """
    params: list[Any] = []
    if start and end:
        sql += " WHERE CAST(dt AS DATE) BETWEEN ?::DATE AND ?::DATE"
        params = [start, end]
    sql += " ORDER BY dt"
    df = db.query_df(sql, params)
    window = f"{start}/{end}" if start and end else config.PERIOD_LABEL
    return _records(df), _meta(n=len(df), display_window=window)


def cities() -> tuple[list[dict], Meta]:
    df = get_db().query_df("SELECT * FROM v_city ORDER BY city_id")
    return _records(df), _meta(n=len(df), definitions=["D1", "D2", "D4"])


def time_profile() -> tuple[dict, Meta]:
    db = get_db()
    hours = _records(db.query_df("SELECT hour, sales_index, share FROM v_hour ORDER BY hour"))
    weekday = _records(db.query_df("""
        SELECT weekday, SUM(sales_index) AS sales_index
        FROM v_hour_weekday GROUP BY weekday ORDER BY weekday
    """))
    total = sum(float(x["sales_index"]) for x in weekday) or 1.0
    for x in weekday:
        x["share"] = float(x["sales_index"]) / total
    heatmap = _records(db.query_df(
        "SELECT weekday, hour, sales_index FROM v_hour_weekday ORDER BY weekday, hour"))
    return {"hours": hours, "weekday": weekday, "heatmap": heatmap}, _meta(
        n=len(heatmap), definitions=["P1-HOUR"])


def store_scatter() -> tuple[list[dict], Meta]:
    df = get_db().query_df("""
        SELECT store_id, city_id, per_day_index, eff_resid, quadrant, cluster, multi_risk, domain_count
        FROM v_store WHERE in_risk_sample IS TRUE ORDER BY store_id
    """)
    return _records(df), _meta(n=len(df), sample_scope="risk")


def _store_where(f: dict) -> tuple[str, list]:
    where = ["1=1"]
    params: list = []
    if f.get("city_id") is not None:
        where.append("city_id = ?"); params.append(int(f["city_id"]))
    if f.get("quadrant"):
        where.append("quadrant = ?"); params.append(f["quadrant"])
    if f.get("cluster"):
        where.append("cluster = ?"); params.append(f["cluster"])
    if f.get("risk_domain"):
        rd = str(f["risk_domain"])
        allowed = {"R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "stockout_domain", "multi_risk"}
        if rd not in allowed:
            raise ValueError("invalid risk_domain")
        where.append(f"{rd} IS TRUE")
    if f.get("exact_combo"):
        if f.get("risk_domain"):
            raise ValueError("exact_combo and risk_domain are mutually exclusive")
        combo = str(f["exact_combo"])
        if len(combo) > 40:
            raise ValueError("exact_combo is too long")
        where.append("exact_combo = ?")
        params.append(combo)
    if f.get("domains") is not None:
        if f.get("risk_domain") or f.get("exact_combo"):
            raise ValueError("domains cannot be combined with risk_domain or exact_combo")
        raw = str(f["domains"]).strip()
        if not raw:
            raise ValueError("domains must not be empty")
        if len(raw) > 40:
            raise ValueError("domains is too long")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        allowed = {"stockout_domain", "R3", "R4", "R5", "R6"}
        if len(parts) != 2 or len(set(parts)) != 2:
            raise ValueError("domains must contain exactly two distinct operational domains")
        if any(p not in allowed for p in parts):
            raise ValueError("invalid domains")
        for p in parts:
            where.append(f"{p} IS TRUE")
    if f.get("sample_scope") == "risk":
        where.append("in_risk_sample IS TRUE")
    if f.get("profile_status"):
        where.append("profile_status = ?"); params.append(f["profile_status"])
    return " AND ".join(where), params


def stores(f: dict, page: int = 1, page_size: int = 50, sort: str = "store_id") -> tuple[list[dict], Meta]:
    db = get_db()
    allowed_sort = {"store_id", "city_id", "total_index", "per_day_index", "sku_count",
                    "cv", "zero_rate", "stockout_sku_day_rate", "stockout_hour_rate", "domain_count"}
    sort_col = sort if sort in allowed_sort else "store_id"
    combo = f.get("exact_combo")
    if combo:
        allowed_combos = set(db.query_df("SELECT combination FROM v_risk_exact")["combination"])
        if combo not in allowed_combos:
            raise ValueError("invalid exact_combo")
    where, params = _store_where(f)
    total = int(db.query_one(f"SELECT COUNT(*) AS n FROM v_store WHERE {where}", params)["n"])
    offset = max(0, (page - 1) * page_size)
    sql = f"""
        SELECT store_id, city_id, profile_status, total_index, per_day_index, sku_count,
               per_sku_day_index, cv, zero_rate, stockout_sku_day_rate, stockout_hour_rate,
               eff_resid, quadrant, cluster, sku_hhi, n_cat, R1, R2, R3, R4, R5, R6, R7, R8,
               stockout_domain, domain_count, multi_risk, in_risk_sample,
               diagnosis_status, domain_labels, exact_combo, structural_notes
        FROM v_store WHERE {where}
        ORDER BY {sort_col} LIMIT ? OFFSET ?
    """
    df = db.query_df(sql, params + [page_size, offset])
    scope = "risk" if f.get("sample_scope") == "risk" else "all"
    return _records(df), _meta(n=total, sample_scope=scope)


def store_detail(store_id: int) -> tuple[dict | None, Meta]:
    df = get_db().query_df("SELECT * FROM v_store WHERE store_id = ?", [store_id])
    if df.empty:
        return None, _meta(n=0)
    return _records(df)[0], _meta(n=1, sample_scope="all")


def store_groups() -> tuple[list[dict], Meta]:
    df = get_db().query_df("SELECT * FROM v_store_groups ORDER BY quadrant, cluster")
    rows = []
    for r in df.to_dict("records"):
        suppressed = bool(r.get("sample_insufficient"))
        if suppressed:
            for c in ["n_flagged_median", "share_flagged_median", "multi_risk_rate"]:
                r[c] = None
        r["suppressed"] = suppressed
        rows.append(r)
    return rows, _meta(n=int(df["stores"].sum()), suppressed=any(r["suppressed"] for r in rows),
                       definitions=["P4-C-GROUP"])


_STORE_SKU_SORTS = {"product_id", "total_index", "zero_days", "stockout_days", "days_present"}


def store_skus(store_id: int, f: dict | None = None, page: int = 1, page_size: int = 50,
               sort: str = "total_index", order: str = "desc") -> tuple[list[dict] | None, Meta]:
    db = get_db()
    if db.query_df("SELECT 1 AS x FROM v_store WHERE store_id = ?", [int(store_id)]).empty:
        return None, _meta(n=0)

    filters = f or {}
    if sort not in _STORE_SKU_SORTS:
        raise ValueError("invalid sort")
    if order not in {"asc", "desc"}:
        raise ValueError("invalid order")

    where = ["i.store_id = ?"]
    params: list = [int(store_id)]
    if filters.get("flagged_only"):
        where.append("i.is_flagged IS TRUE")
    clause = " AND ".join(where)

    sql = f"""
        SELECT i.product_id, s.display_code AS product_code, c.display_code AS category_code,
               i.days_present, i.observed_rows, i.total_index,
               i.zero_days, i.stockout_days,
               CASE WHEN i.observed_rows > 0
                    THEN i.zero_days * 1.0 / i.observed_rows ELSE NULL END AS zero_rate,
               i.risk_flag_count, i.flag_high_cv, i.flag_high_zero,
               i.flag_many_anomaly_days, i.flag_store_concentration,
               i.is_flagged, i.is_multi_flag,
               COUNT(*) OVER () AS total_count
        FROM v_store_sku i
        LEFT JOIN v_sku s ON i.product_id = s.product_id
        LEFT JOIN v_category c ON s.first_category_id = c.raw_id
        WHERE {clause}
        ORDER BY i.{sort} {'DESC' if order == 'desc' else 'ASC'}, i.product_id ASC
        LIMIT ? OFFSET ?
    """
    df = db.query_df(sql, params + [page_size, max(0, (page - 1) * page_size)])
    if df.empty:
        total = int(db.query_one(f"SELECT COUNT(*) AS n FROM v_store_sku i WHERE {clause}", params)["n"])
    else:
        total = int(df["total_count"].iloc[0])
        df = df.drop(columns=["total_count"])
    return _records(df), _meta(n=total, sample_scope="all")


_STORE_DENOMINATOR = 898

_PRODUCT_SORTS = {
    "product_id", "total_index", "store_count", "per_series_day", "zero_rate",
    "cv_series_median", "hhi", "risk_flag_count", "rank_scale", "rank_eff_all",
}

_PRODUCT_RISK_FILTERS = {
    "flagged": "s.risk_flag_count > 0",
    "multi": "s.risk_flag_count >= 2",
    "high_cv": "s.flag_high_cv IS TRUE",
    "high_zero": "s.flag_high_zero IS TRUE",
    "many_anomaly_days": "s.flag_many_anomaly_days IS TRUE",
    "store_concentration": "s.flag_store_concentration IS TRUE",
}

_HEAD_SQL = """s.rank_scale <= (SELECT sku_count FROM v_sku_head_tail WHERE "group" LIKE '头部%')"""
_TAIL_SQL = """s.rank_scale > (SELECT COUNT(*) FROM v_sku) - (SELECT sku_count FROM v_sku_head_tail WHERE "group" LIKE '长尾%')"""

_PRODUCT_FLAG_DEFS = [
    ("high_cv", "flag_high_cv", "高波动", "序列 CV 中位数 > 全部 865 个 SKU 的 P95 = 1.060"),
    ("high_zero", "flag_high_zero", "高零销", "SKU 零销率 > 全部 865 个 SKU 的 P95 = 24.44%"),
    ("many_anomaly_days", "flag_many_anomaly_days", "异常日频繁", "异常日占比 > 5%（序列内稳健 z 绝对值 > 3.5 记为异常日）"),
    ("store_concentration", "flag_store_concentration", "门店集中", "覆盖≥5 店且门店销量 HHI > 多店 SKU 的 P95 = 0.184"),
]

_PAIR_DEFINITION = (
    "两个均为 P2 flagged SKU，且在观察期内同时进入同一门店的商品集合"
    "（观察期内同店共同出现）；不代表同日销售、同日缺货、同时缺货、"
    "消费者购买搭配关系或商品间因果关系。"
)
_PRODUCT_STORE_SORTS = {"store_id", "total_index", "zero_days", "stockout_days", "days_present"}


def _product_select() -> str:
    return f"""
        SELECT s.product_id, s.display_code AS product_code,
               c.display_code AS category_code,
               s.store_count,
               s.store_count / {_STORE_DENOMINATOR}.0 AS store_coverage,
               s.total_index,
               s.total_share_pct / 100.0 AS total_share,
               s.cum_share_pct / 100.0 AS cum_share,
               s.per_series_day, s.zero_rate, s.cv_series_median, s.hhi,
               s.risk_flag_count, s.flag_high_cv, s.flag_high_zero,
               s.flag_many_anomaly_days, s.flag_store_concentration,
               s.rank_scale, s.rank_eff_all, s.rank_eff_cov5, s.rank_diff,
               s.series_days, s.active_day_rate, s.stockout_day_rate, s.promo_rate,
               s.anomaly_rate, s.effective_stores, s.stability_tier,
               CASE
                 WHEN {_HEAD_SQL} THEN '头部 Top20%'
                 WHEN {_TAIL_SQL} THEN '长尾 Bottom50%'
                 ELSE '中部'
               END AS head_tail_group,
               (s.risk_flag_count > 0) AS is_flagged
        FROM v_sku s
        LEFT JOIN v_category c ON s.first_category_id = c.raw_id
    """


def _product_where(f: dict) -> tuple[str, list]:
    where = ["1=1"]
    params: list = []
    scope = f.get("scope") or "flagged"
    if scope not in {"flagged", "all"}:
        raise ValueError("invalid scope")
    if scope == "flagged":
        where.append("s.risk_flag_count > 0")

    q = (f.get("q") or "").strip()
    if q:
        if len(q) > 40:
            raise ValueError("q is too long")
        where.append("upper(s.display_code) LIKE ?")
        params.append(f"%{q.upper()}%")

    category = f.get("category")
    if category:
        where.append("s.first_category_id = (SELECT raw_id FROM v_category WHERE display_code = ?)")
        params.append(category)

    head_tail = f.get("head_tail")
    if head_tail == "head":
        where.append(_HEAD_SQL)
    elif head_tail == "tail":
        where.append(_TAIL_SQL)
    elif head_tail:
        raise ValueError("invalid head_tail")

    risk = f.get("risk")
    if risk:
        if risk not in _PRODUCT_RISK_FILTERS:
            raise ValueError("invalid risk")
        where.append(_PRODUCT_RISK_FILTERS[risk])

    cmin = f.get("coverage_min")
    cmax = f.get("coverage_max")
    if cmin is not None:
        if int(cmin) < 0:
            raise ValueError("coverage_min must be >= 0")
        where.append("s.store_count >= ?")
        params.append(int(cmin))
    if cmax is not None:
        if int(cmax) < 0:
            raise ValueError("coverage_max must be >= 0")
        where.append("s.store_count <= ?")
        params.append(int(cmax))
    if cmin is not None and cmax is not None and int(cmin) > int(cmax):
        raise ValueError("coverage_min must be <= coverage_max")
    return " AND ".join(where), params


def products(f: dict | None = None, page: int = 1, page_size: int = 50,
             sort: str | None = None, order: str = "desc") -> tuple[list[dict], Meta]:
    db = get_db()
    filters = f or {}
    where, params = _product_where(filters)

    if order not in {"asc", "desc"}:
        raise ValueError("invalid order")
    if sort:
        if sort not in _PRODUCT_SORTS:
            raise ValueError("invalid sort")
        order_sql = f"s.{sort} {'DESC' if order == 'desc' else 'ASC'}, s.product_id ASC"
    elif (filters.get("scope") or "flagged") == "flagged":
        order_sql = "s.risk_flag_count DESC, s.store_count DESC, s.product_id ASC"
    else:
        order_sql = "s.rank_scale ASC, s.product_id ASC"

    total = int(db.query_one(f"SELECT COUNT(*) AS n FROM v_sku s WHERE {where}", params)["n"])
    sql = f"""
        {_product_select()}
        WHERE {where}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    df = db.query_df(sql, params + [page_size, max(0, (page - 1) * page_size)])
    return _records(df), _meta(n=total, sample_scope="all", definitions=["P2-SKU"])


def product_detail(product_id: int) -> tuple[dict | None, Meta]:
    db = get_db()
    df = db.query_df(f"{_product_select()} WHERE s.product_id = ?", [product_id])
    if df.empty:
        return None, _meta(n=0)
    row = _records(df)[0]
    row["risk_flags"] = [
        {"code": code, "label": label, "definition": definition, "hit": bool(row.get(column))}
        for code, column, label, definition in _PRODUCT_FLAG_DEFS
    ]
    return row, _meta(n=1, sample_scope="all", definitions=["P2-SKU", "P2-RISK"])


def product_overview() -> tuple[dict, Meta]:
    db = get_db()
    base = db.query_one("""
        SELECT COUNT(*) AS sku_count,
               SUM(total_index) AS total_index,
               median(store_count) AS store_count_median,
               quantile_cont(store_count, 0.9) AS store_count_p90,
               MAX(store_count) AS store_count_max
        FROM v_sku
    """)
    buckets = db.query_df("""
        SELECT CASE
                 WHEN store_count = 1 THEN '1'
                 WHEN store_count <= 4 THEN '2-4'
                 WHEN store_count <= 9 THEN '5-9'
                 WHEN store_count <= 19 THEN '10-19'
                 WHEN store_count <= 49 THEN '20-49'
                 WHEN store_count <= 99 THEN '50-99'
                 ELSE '100+'
               END AS bucket,
               MIN(store_count) AS min_store_count,
               MAX(store_count) AS max_store_count,
               COUNT(*) AS skus
        FROM v_sku GROUP BY 1 ORDER BY min_store_count
    """)
    head_tail = db.query_df('SELECT "group" AS "group", sku_count AS skus FROM v_sku_head_tail ORDER BY skus DESC')
    risk = db.query_one("""
        SELECT SUM(CASE WHEN risk_flag_count > 0 THEN 1 ELSE 0 END) AS flagged_skus,
               SUM(CASE WHEN risk_flag_count >= 2 THEN 1 ELSE 0 END) AS multi_flag_skus
        FROM v_sku
    """)
    cats = db.query_df("""
        SELECT c.display_code AS category_code, c.sku_count, c.store_count, c.total_index, c.share_pct,
               CAST(COALESCE(r.n_flagged_skus, 0) AS INTEGER) AS n_flagged_skus,
               CAST(COALESCE(r.n_multi_flag_skus, 0) AS INTEGER) AS n_multi_flag_skus,
               r.flagged_sku_share, r.flagged_total_index_share,
               p.coverage, COALESCE(p.rare, FALSE) AS rare
        FROM v_category c
        LEFT JOIN v_category_risk r ON c.raw_id = r.raw_id
        LEFT JOIN v_category_penetration p ON c.raw_id = p.raw_id
        ORDER BY c.total_index DESC
    """)

    sku_count = int(base["sku_count"])
    rows = _records(head_tail)
    for row in rows:
        row["share"] = float(row["skus"]) / sku_count
    data = {
        "sku_count": sku_count,
        "total_index": float(base["total_index"]),
        "store_count_median": float(base["store_count_median"]),
        "store_count_p90": float(base["store_count_p90"]),
        "store_count_max": int(base["store_count_max"]),
        "coverage_distribution": _records(buckets),
        "head_tail": rows,
        "flagged_skus": int(risk["flagged_skus"]),
        "multi_flag_skus": int(risk["multi_flag_skus"]),
        "categories": _records(cats),
    }
    return data, _meta(n=sku_count, sample_scope="all", definitions=["P2-SKU", "P2-RISK"])


def product_stores(product_id: int, f: dict | None = None, page: int = 1, page_size: int = 50,
                   sort: str = "total_index", order: str = "desc") -> tuple[list[dict] | None, Meta]:
    db = get_db()
    if db.query_df("SELECT 1 AS x FROM v_sku WHERE product_id = ?", [product_id]).empty:
        return None, _meta(n=0)

    filters = f or {}
    if sort not in _PRODUCT_STORE_SORTS:
        raise ValueError("invalid sort")
    if order not in {"asc", "desc"}:
        raise ValueError("invalid order")

    where = ["i.product_id = ?"]
    params: list = [int(product_id)]
    if filters.get("city_id") is not None:
        where.append("s.city_id = ?")
        params.append(int(filters["city_id"]))
    if filters.get("quadrant"):
        where.append("s.quadrant = ?")
        params.append(filters["quadrant"])
    if filters.get("cluster"):
        where.append("s.cluster = ?")
        params.append(filters["cluster"])
    if filters.get("flagged_only"):
        where.append("i.is_flagged IS TRUE")

    clause = " AND ".join(where)
    sql = f"""
        SELECT i.store_id, s.city_id, s.quadrant, s.cluster,
               i.days_present, i.observed_rows, i.total_index,
               i.zero_days, i.stockout_days, i.risk_flag_count,
               i.is_flagged, i.is_multi_flag,
               COUNT(*) OVER () AS total_count
        FROM v_store_sku i
        LEFT JOIN v_store s USING (store_id)
        WHERE {clause}
        ORDER BY i.{sort} {'DESC' if order == 'desc' else 'ASC'}, i.store_id ASC
        LIMIT ? OFFSET ?
    """
    df = db.query_df(sql, params + [page_size, max(0, (page - 1) * page_size)])
    if df.empty:
        total = int(db.query_one(
            f"SELECT COUNT(*) AS n FROM v_store_sku i LEFT JOIN v_store s USING (store_id) WHERE {clause}",
            params)["n"])
    else:
        total = int(df["total_count"].iloc[0])
        df = df.drop(columns=["total_count"])
    return _records(df), _meta(n=total, sample_scope="all", suppressed=total < 20)


def product_pairs(product_id: int, limit: int = 20) -> tuple[list[dict] | None, Meta, list[str]]:
    db = get_db()
    sku = db.query_one("SELECT risk_flag_count FROM v_sku WHERE product_id = ?", [product_id])
    if not sku:
        return None, _meta(n=0), []

    total = int(db.query_one(
        "SELECT COUNT(*) AS n FROM v_sku_pairs WHERE product_a = ? OR product_b = ?",
        [int(product_id), int(product_id)])["n"])
    df = db.query_df("""
        SELECT CASE WHEN product_a = ? THEN product_b ELSE product_a END AS other_product_id,
               CASE WHEN product_a = ? THEN sku_b ELSE sku_a END AS other_product_code,
               stores_both, share_stores_both
        FROM v_sku_pairs
        WHERE product_a = ? OR product_b = ?
        ORDER BY stores_both DESC, other_product_id ASC
        LIMIT ?
    """, [int(product_id), int(product_id), int(product_id), int(product_id), int(limit)])
    rows = _records(df)
    for row in rows:
        row["definition"] = _PAIR_DEFINITION

    warnings: list[str] = []
    if int(sku["risk_flag_count"] or 0) == 0:
        warnings.append("该 SKU 未命中 P2 风险旗标；P4-C 共现仅覆盖 117 个风险 SKU，因此无共现记录。")
    return rows, _meta(n=total, sample_scope="all", definitions=["P4C-PAIRS"]), warnings


def risk_summary() -> tuple[dict, Meta]:
    db = get_db()
    domains = db.query_df("SELECT * FROM v_risk_domain ORDER BY domain_count").to_dict("records")
    multi = int(db.query_one("SELECT COUNT(*) AS n FROM v_store_profile WHERE multi_risk IS TRUE")["n"])
    flags = db.query_one("""
        SELECT
          SUM(CASE WHEN stockout_domain IS TRUE THEN 1 ELSE 0 END) AS stockout_domain,
          SUM(CASE WHEN R3 IS TRUE THEN 1 ELSE 0 END) AS R3,
          SUM(CASE WHEN R4 IS TRUE THEN 1 ELSE 0 END) AS R4,
          SUM(CASE WHEN R5 IS TRUE THEN 1 ELSE 0 END) AS R5,
          SUM(CASE WHEN R6 IS TRUE THEN 1 ELSE 0 END) AS R6,
          SUM(CASE WHEN R7 IS TRUE THEN 1 ELSE 0 END) AS R7,
          SUM(CASE WHEN R8 IS TRUE THEN 1 ELSE 0 END) AS R8
        FROM v_store_profile
    """)
    flags = {k: int(v) for k, v in flags.items() if v is not None}
    return {"domains": domains, "multi_risk": multi, "flags": flags}, _meta(
        n=888, sample_scope="risk", definitions=["D17"])


def risk_combinations(definition: str = "exact") -> tuple[list[dict], Meta]:
    db = get_db()
    if definition not in {"exact", "at_least"}:
        raise ValueError("definition must be exact or at_least")
    if definition == "exact":
        df = db.query_df("SELECT combination, stores, rank, definition FROM v_risk_exact ORDER BY rank, stores DESC")
    else:
        df = db.query_df("SELECT domain_a || '+' || domain_b AS combination, stores_at_least AS stores, definition FROM v_risk_at_least ORDER BY stores_at_least DESC")
        df.insert(2, "rank", range(1, len(df) + 1))
    return df.to_dict("records"), _meta(n=len(df), sample_scope="risk", definitions=["D17"])


def export_stores_csv(f: dict) -> str:
    rows, meta = stores(f, page=1, page_size=2000, sort="store_id")
    cols = ["store_id", "city_id", "profile_status", "total_index", "per_day_index", "sku_count",
            "cv", "zero_rate", "stockout_sku_day_rate", "stockout_hour_rate", "quadrant", "cluster",
            "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "domain_count", "multi_risk"]
    buf = io.StringIO()
    buf.write(f"# data_version={meta.data_version}\n")
    buf.write(f"# period={meta.period}\n")
    buf.write(f"# filters={f}\n")
    buf.write("# note=聚合门店档案；不含 store×SKU 明细；归一化销量指数不是销售额\n")
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
