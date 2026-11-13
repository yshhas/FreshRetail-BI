"""BI-2-A 商品数据层契约测试。"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bi_api import config, service
from bi_api.main import app

T1 = pd.read_csv(config.PROJECT_ROOT / "data/analysis/p2/t1_sku_metrics.csv")
INC = pd.read_csv(config.PROJECT_ROOT / "data/analysis/p4/p4_c_store_sku_incidence.csv")
PAIRS = pd.read_csv(config.PROJECT_ROOT / "data/analysis/p4/p4_c_sku_pair_cooccurrence.csv")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _all_products(client, page_size=200):
    rows, page = [], 1
    while True:
        body = client.get(f"/api/v1/products?scope=all&page={page}&page_size={page_size}").json()
        rows.extend(body["data"])
        if page * page_size >= body["meta"]["n"]:
            break
        page += 1
    return rows


def test_product_list_covers_all_865(client):
    rows = _all_products(client)
    ids = [r["product_id"] for r in rows]
    assert len(rows) == 865
    assert len(set(ids)) == 865
    assert set(ids) == set(int(x) for x in T1.product_id)
    assert rows[0]["product_code"] == "P0268"
    assert rows[0]["head_tail_group"] == "头部 Top20%"


def test_product_list_default_is_backward_compatible(client):
    body = client.get("/api/v1/products?page_size=5").json()
    assert body["meta"]["n"] == 117
    assert len(body["data"]) == 5
    row = body["data"][0]
    for key in ["product_id", "product_code", "category_code", "store_count",
                "store_coverage", "total_index", "risk_flag_count",
                "flag_high_cv", "flag_high_zero", "flag_many_anomaly_days",
                "flag_store_concentration"]:
        assert key in row


def test_product_overview_contract(client):
    data = client.get("/api/v1/products/overview").json()["data"]
    assert data["sku_count"] == 865
    assert data["total_index"] == pytest.approx(4493660.787, abs=1e-3)
    assert data["store_count_median"] == 10
    assert data["store_count_p90"] == pytest.approx(173.6, abs=1e-6)
    assert data["store_count_max"] == 783
    assert data["flagged_skus"] == 117
    assert data["multi_flag_skus"] == 35

    buckets = {b["bucket"]: b["skus"] for b in data["coverage_distribution"]}
    assert buckets == {"1": 150, "2-4": 175, "5-9": 97, "10-19": 87,
                       "20-49": 115, "50-99": 88, "100+": 153}
    assert sum(buckets.values()) == 865

    ht = {h["group"]: h for h in data["head_tail"]}
    assert ht["头部 Top20%"]["skus"] == 173
    assert ht["长尾 Bottom50%"]["skus"] == 432
    assert ht["头部 Top20%"]["share"] == pytest.approx(173 / 865)
    assert ht["长尾 Bottom50%"]["share"] == pytest.approx(432 / 865)

    assert len(data["categories"]) == 32
    c05 = next(c for c in data["categories"] if c["category_code"] == "C05")
    assert c05["sku_count"] == 95
    assert c05["store_count"] == 886
    assert c05["share_pct"] == pytest.approx(25.81, abs=0.01)


def test_product_filters(client):
    def n(query):
        return client.get(f"/api/v1/products?scope=all&page_size=1&{query}").json()["meta"]["n"]

    assert n("head_tail=head") == 173
    assert n("head_tail=tail") == 432
    assert n("risk=multi") == 35
    assert n("risk=high_cv") == int((T1.cv_series_median > 1.0600866969184302).sum())
    assert n("coverage_min=20&coverage_max=49") == 115
    assert n("category=C05") == int((T1.first_category_id == 4).sum())
    assert n("q=P0005") == 1
    assert n("q=p0005") == 1
    assert n("q=NOT-EXIST") == 0


def test_product_detail_matches_list(client):
    detail = client.get("/api/v1/products/4").json()
    assert detail["meta"]["n"] == 1
    d = detail["data"]
    assert d["product_code"] == "P0005"
    assert d["category_code"] == "C30"
    assert d["store_count"] == 783
    assert d["head_tail_group"] == "头部 Top20%"

    listed = client.get("/api/v1/products?scope=all&q=P0005").json()["data"][0]
    for key in ["store_count", "total_index", "zero_rate", "cv_series_median",
                "hhi", "risk_flag_count", "store_coverage"]:
        assert d[key] == pytest.approx(listed[key])

    assert len(d["risk_flags"]) == 4
    assert {f["code"] for f in d["risk_flags"]} == {
        "high_cv", "high_zero", "many_anomaly_days", "store_concentration"}
    assert all(f["definition"] for f in d["risk_flags"])

    non_flagged = int(T1.loc[T1.risk_flag_count == 0, "product_id"].iloc[0])
    body = client.get(f"/api/v1/products/{non_flagged}").json()
    assert body["meta"]["n"] == 1
    assert all(f["hit"] is False for f in body["data"]["risk_flags"])

    assert client.get("/api/v1/products/999999").status_code == 404


def test_product_stores_matches_incidence(client):
    expected = INC[INC.product_id == 4]
    body = client.get("/api/v1/products/4/stores?page_size=200").json()
    assert body["meta"]["n"] == len(expected) == 783
    assert len(body["data"]) == 200
    assert body["data"][0]["total_index"] >= body["data"][-1]["total_index"]

    ids, page = set(), 1
    while True:
        part = client.get(f"/api/v1/products/4/stores?page={page}&page_size=200").json()
        ids.update(r["store_id"] for r in part["data"])
        if page * 200 >= part["meta"]["n"]:
            break
        page += 1
    assert ids == set(int(x) for x in expected.store_id)

    city0 = expected.merge(pd.read_csv(config.PROJECT_ROOT / "data/analysis/p4/p4_a_store_profile.csv")[["store_id", "city_id"]], on="store_id")
    n_city0 = int((city0.city_id == 0).sum())
    assert client.get("/api/v1/products/4/stores?city_id=0&page_size=1").json()["meta"]["n"] == n_city0


def test_product_pairs_match_frozen(client):
    expected = PAIRS[(PAIRS.product_a == 4) | (PAIRS.product_b == 4)]
    body = client.get("/api/v1/products/4/pairs?limit=5").json()
    assert body["meta"]["n"] == len(expected) == 110
    assert len(body["data"]) == 5
    top = body["data"][0]
    assert top["other_product_id"] == 600
    assert top["other_product_code"] == "P0601"
    assert top["stores_both"] == 440
    assert top["share_stores_both"] == pytest.approx(440 / 898)
    assert "观察期内同店共同出现" in top["definition"]

    non_flagged = int(T1.loc[T1.risk_flag_count == 0, "product_id"].iloc[0])
    empty = client.get(f"/api/v1/products/{non_flagged}/pairs").json()
    assert empty["meta"]["n"] == 0 and empty["data"] == []
    assert empty["warnings"]

    assert client.get("/api/v1/products/999999/pairs").status_code == 404


def test_low_coverage_suppression(client):
    pid = int(T1.loc[T1.store_count == 1, "product_id"].iloc[0])
    body = client.get(f"/api/v1/products/{pid}/stores").json()
    assert body["meta"]["n"] == 1
    assert body["meta"]["suppressed"] is True
    assert body["warnings"]


def test_whitelists_and_invalid_params(client):
    assert client.get("/api/v1/products?scope=all&sort=drop").status_code == 400
    assert client.get("/api/v1/products?scope=all&risk=foo").status_code == 422
    assert client.get("/api/v1/products?scope=all&order=sideways").status_code == 422
    assert client.get("/api/v1/products?scope=all&coverage_min=50&coverage_max=10").status_code == 400
    assert client.get("/api/v1/products?scope=all&page_size=201").status_code == 422
    assert client.get("/api/v1/products/4/stores?sort=drop").status_code == 422

    injected = client.get("/api/v1/products", params={"scope": "all", "q": "' OR 1=1 --"})
    assert injected.status_code == 200
    assert injected.json()["meta"]["n"] == 0


def test_new_views_registered():
    db = service.get_db()
    counts = db.view_counts()
    assert counts["v_store_sku"] == 50000
    assert counts["v_sku_head_tail"] == 2
    assert counts["v_category_penetration"] == 32
    assert len(counts) == 25
