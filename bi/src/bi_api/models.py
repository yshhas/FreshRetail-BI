"""BI-0 Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    n: int = 0
    period: str
    data_version: str
    sample_scope: str = "all"
    suppressed: bool = False
    definitions: list[str] = Field(default_factory=list)
    display_window: str | None = None


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta
    warnings: list[str] = Field(default_factory=list)


class Health(BaseModel):
    status: str
    data_version: str
    period: str
    views: dict[str, int]


class Kpi(BaseModel):
    key: str
    label: str
    value: float | int | None
    unit: str
    metric_id: str
    sample_n: int
    note: str = ""


class TrendPoint(BaseModel):
    dt: str
    sales_index_total: float
    per_store_index: float
    zero_sales_rate: float | None = None
    stockout_day_rate: float | None = None


class HourPoint(BaseModel):
    hour: int
    sales_index: float
    share: float | None = None


class WeekdayPoint(BaseModel):
    weekday: int
    sales_index: float
    share: float | None = None


class WeekdayHourPoint(BaseModel):
    weekday: int
    hour: int
    sales_index: float


class TimeProfile(BaseModel):
    hours: list[HourPoint]
    weekday: list[WeekdayPoint]
    heatmap: list[WeekdayHourPoint]


class StoreScatterRow(BaseModel):
    store_id: int
    city_id: int
    per_day_index: float | None = None
    eff_resid: float | None = None
    quadrant: str | None = None
    cluster: str | None = None
    multi_risk: bool | None = None
    domain_count: int | None = None


class CityRow(BaseModel):
    city_id: int
    store_count: int
    city_total_index: float
    city_store_day_avg: float
    sku_per_store_mean: float | None = None
    city_stockout_sku_day_pooled: float | None = None
    city_stockout_store_mean: float | None = None
    city_stockout_hour_pooled: float | None = None
    city_zero_rate: float | None = None
    small_city: bool | None = None
    stores_all: int | None = None
    stores_risk: int | None = None
    stockout_sku_day_median: float | None = None
    stockout_hour_median: float | None = None
    multi_risk: int | None = None
    multi_risk_rate_risk: float | None = None
    multi_risk_rate_all: float | None = None


class StoreRow(BaseModel):
    store_id: int
    city_id: int
    profile_status: str
    total_index: float | None = None
    per_day_index: float | None = None
    sku_count: int | None = None
    per_sku_day_index: float | None = None
    cv: float | None = None
    zero_rate: float | None = None
    stockout_sku_day_rate: float | None = None
    stockout_hour_rate: float | None = None
    eff_resid: float | None = None
    quadrant: str | None = None
    cluster: str | None = None
    sku_hhi: float | None = None
    n_cat: float | None = None
    R1: bool | None = None
    R2: bool | None = None
    R3: bool | None = None
    R4: bool | None = None
    R5: bool | None = None
    R6: bool | None = None
    R7: bool | None = None
    R8: bool | None = None
    stockout_domain: bool | None = None
    domain_count: int | None = None
    multi_risk: bool | None = None
    in_risk_sample: bool | None = None
    diagnosis_status: str | None = None
    domain_labels: str | None = None
    exact_combo: str | None = None
    structural_notes: str | None = None


class StoreGroupRow(BaseModel):
    quadrant: str
    cluster: str
    stores: int
    n_flagged_median: float | None = None
    share_flagged_median: float | None = None
    multi_risk_rate: float | None = None
    sample_insufficient: bool
    suppressed: bool = False


class StoreSkuRow(BaseModel):
    product_id: int
    product_code: str | None = None
    category_code: str | None = None
    days_present: int | None = None
    observed_rows: int | None = None
    total_index: float | None = None
    zero_days: int | None = None
    stockout_days: int | None = None
    zero_rate: float | None = None
    risk_flag_count: int | None = None
    flag_high_cv: bool | None = None
    flag_high_zero: bool | None = None
    flag_many_anomaly_days: bool | None = None
    flag_store_concentration: bool | None = None
    is_flagged: bool | None = None
    is_multi_flag: bool | None = None


class ProductRow(BaseModel):
    product_id: int
    product_code: str | None = None
    category_code: str | None = None
    store_count: int | None = None
    store_coverage: float | None = None
    total_index: float | None = None
    total_share: float | None = None
    cum_share: float | None = None
    per_series_day: float | None = None
    zero_rate: float | None = None
    cv_series_median: float | None = None
    hhi: float | None = None
    risk_flag_count: int | None = None
    flag_high_cv: bool | None = None
    flag_high_zero: bool | None = None
    flag_many_anomaly_days: bool | None = None
    flag_store_concentration: bool | None = None
    rank_scale: int | None = None
    rank_eff_all: int | None = None
    rank_eff_cov5: float | None = None
    head_tail_group: str | None = None
    is_flagged: bool | None = None


class ProductRiskFlag(BaseModel):
    code: str
    label: str
    definition: str
    hit: bool


class ProductDetail(ProductRow):
    series_days: int | None = None
    active_day_rate: float | None = None
    stockout_day_rate: float | None = None
    promo_rate: float | None = None
    anomaly_rate: float | None = None
    effective_stores: float | None = None
    rank_diff: int | None = None
    stability_tier: str | None = None
    risk_flags: list[ProductRiskFlag] = Field(default_factory=list)


class ProductStoreRow(BaseModel):
    store_id: int
    city_id: int | None = None
    quadrant: str | None = None
    cluster: str | None = None
    days_present: int | None = None
    observed_rows: int | None = None
    total_index: float | None = None
    zero_days: int | None = None
    stockout_days: int | None = None
    risk_flag_count: int | None = None
    is_flagged: bool | None = None
    is_multi_flag: bool | None = None


class ProductPairRow(BaseModel):
    other_product_id: int
    other_product_code: str | None = None
    stores_both: int
    share_stores_both: float
    definition: str


class CoverageBucket(BaseModel):
    bucket: str
    min_store_count: int
    max_store_count: int
    skus: int


class HeadTailRow(BaseModel):
    group: str
    skus: int
    share: float


class ProductCategoryRow(BaseModel):
    category_code: str
    sku_count: int
    store_count: int
    total_index: float
    share_pct: float
    n_flagged_skus: int = 0
    n_multi_flag_skus: int = 0
    flagged_sku_share: float | None = None
    flagged_total_index_share: float | None = None
    coverage: float | None = None
    rare: bool | None = None


class ProductOverview(BaseModel):
    sku_count: int
    total_index: float
    store_count_median: float
    store_count_p90: float
    store_count_max: int
    coverage_distribution: list[CoverageBucket]
    head_tail: list[HeadTailRow]
    flagged_skus: int
    multi_flag_skus: int
    categories: list[ProductCategoryRow]


class RiskDomainRow(BaseModel):
    domain_count: int
    stores: int


class RiskComboRow(BaseModel):
    combination: str
    stores: int
    rank: int | None = None
    definition: str | None = None


class FilterOptions(BaseModel):
    cities: list[dict]
    quadrants: list[str]
    clusters: list[str]
    risk_domains: list[str]
    categories: list[dict]
    sample_scopes: list[str]
    period: str


class CatalogOut(BaseModel):
    metrics: list[dict]
    pages: list[dict]
    version: str
