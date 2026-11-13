"""BI-0 FastAPI 只读接口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from . import config, freeze, service
from .models import (
    CatalogOut, CityRow, Envelope, FilterOptions, Health, Kpi, Meta,
    ProductDetail, ProductOverview, ProductPairRow, ProductRow, ProductStoreRow,
    RiskComboRow, RiskDomainRow, StoreGroupRow, StoreRow, StoreScatterRow, StoreSkuRow,
    TimeProfile, TrendPoint,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时校验 P1–P4 冻结文件；失败则拒绝启动
    freeze.verify_manifest()
    service.get_db()
    yield
    service.get_db().close()
    service.get_db.cache_clear()


app = FastAPI(
    title="零售经营 BI API（BI-0）",
    version="0.1.0",
    description="只读查询 P1–P4 冻结结果；不提供写入接口。",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=Health)
def health():
    return service.health()


@app.get("/api/v1/meta/catalog", response_model=CatalogOut)
def meta_catalog():
    return service.catalog_data()


@app.get("/api/v1/meta/filters", response_model=FilterOptions)
def meta_filters():
    return service.filters()


@app.get("/api/v1/overview/kpis", response_model=Envelope[list[Kpi]])
def overview_kpis():
    data, meta = service.overview_kpis()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/overview/trend", response_model=Envelope[list[TrendPoint]])
def overview_trend(start: str | None = None, end: str | None = None):
    data, meta = service.trend(start, end)
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/overview/time-profile", response_model=Envelope[TimeProfile])
def overview_time_profile():
    data, meta = service.time_profile()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/cities", response_model=Envelope[list[CityRow]])
def cities():
    data, meta = service.cities()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/stores/scatter", response_model=Envelope[list[StoreScatterRow]])
def store_scatter():
    data, meta = service.store_scatter()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/stores/groups", response_model=Envelope[list[StoreGroupRow]])
def store_groups():
    data, meta = service.store_groups()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/stores", response_model=Envelope[list[StoreRow]])
def stores(
    city_id: int | None = None,
    quadrant: str | None = None,
    cluster: str | None = None,
    risk_domain: str | None = None,
    exact_combo: str | None = None,
    domains: str | None = None,
    sample_scope: Literal["all", "risk"] = "all",
    profile_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: str = "store_id",
):
    try:
        data, meta = service.stores(
            {"city_id": city_id, "quadrant": quadrant, "cluster": cluster,
             "risk_domain": risk_domain, "exact_combo": exact_combo, "domains": domains,
             "sample_scope": sample_scope,
             "profile_status": profile_status},
            page=page, page_size=page_size, sort=sort)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/stores/{store_id}", response_model=Envelope[StoreRow])
def store_detail(store_id: int):
    data, meta = service.store_detail(store_id)
    if data is None:
        raise HTTPException(status_code=404, detail="store not found")
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/stores/{store_id}/skus", response_model=Envelope[list[StoreSkuRow]])
def store_skus(
    store_id: int,
    flagged_only: bool = False,
    sort: Literal["product_id", "total_index", "zero_days", "stockout_days", "days_present"] = "total_index",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    try:
        data, meta = service.store_skus(store_id, {"flagged_only": flagged_only},
                                        page=page, page_size=page_size,
                                        sort=sort, order=order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail="store not found")
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/products/overview", response_model=Envelope[ProductOverview])
def product_overview():
    data, meta = service.product_overview()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/products", response_model=Envelope[list[ProductRow]])
def products(
    scope: Literal["flagged", "all"] = "flagged",
    q: str | None = Query(None, max_length=40),
    category: str | None = None,
    head_tail: Literal["head", "tail"] | None = None,
    risk: Literal["flagged", "multi", "high_cv", "high_zero",
                  "many_anomaly_days", "store_concentration"] | None = None,
    coverage_min: int | None = Query(None, ge=0),
    coverage_max: int | None = Query(None, ge=0),
    sort: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    filters = {
        "scope": scope, "q": q, "category": category, "head_tail": head_tail,
        "risk": risk, "coverage_min": coverage_min, "coverage_max": coverage_max,
    }
    try:
        data, meta = service.products(filters, page=page, page_size=page_size,
                                      sort=sort, order=order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/products/{product_id}", response_model=Envelope[ProductDetail])
def product_detail(product_id: int):
    data, meta = service.product_detail(product_id)
    if data is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/products/{product_id}/stores", response_model=Envelope[list[ProductStoreRow]])
def product_stores(
    product_id: int,
    city_id: int | None = None,
    quadrant: str | None = None,
    cluster: str | None = None,
    flagged_only: bool = False,
    sort: Literal["store_id", "total_index", "zero_days", "stockout_days", "days_present"] = "total_index",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    filters = {"city_id": city_id, "quadrant": quadrant, "cluster": cluster,
               "flagged_only": flagged_only}
    try:
        data, meta = service.product_stores(product_id, filters, page=page,
                                            page_size=page_size, sort=sort, order=order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail="product not found")
    warnings = []
    if meta.suppressed:
        warnings.append("该 SKU 覆盖门店 n<20，统计与比例类指标不稳定，仅作计数展示。")
    return {"data": data, "meta": meta, "warnings": warnings}


@app.get("/api/v1/products/{product_id}/pairs", response_model=Envelope[list[ProductPairRow]])
def product_pairs(product_id: int, limit: int = Query(20, ge=1, le=200)):
    data, meta, warnings = service.product_pairs(product_id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {"data": data, "meta": meta, "warnings": warnings}


@app.get("/api/v1/risk/summary", response_model=Envelope[dict])
def risk_summary():
    data, meta = service.risk_summary()
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/risk/combinations", response_model=Envelope[list[RiskComboRow]])
def risk_combinations(definition: Literal["exact", "at_least"] = "exact"):
    data, meta = service.risk_combinations(definition)
    return {"data": data, "meta": meta, "warnings": []}


@app.get("/api/v1/export/stores.csv")
def export_stores(
    city_id: int | None = None,
    quadrant: str | None = None,
    cluster: str | None = None,
    risk_domain: str | None = None,
    sample_scope: Literal["all", "risk"] = "all",
):
    try:
        content = service.export_stores_csv({
            "city_id": city_id, "quadrant": quadrant, "cluster": cluster,
            "risk_domain": risk_domain, "sample_scope": sample_scope})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="bi_stores.csv"'})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bi_api.main:app", host="127.0.0.1", port=8000, reload=False)
