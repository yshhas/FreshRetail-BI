"""BI-2-C C-2 后端契约测试：精确组合筛选与门店 SKU 列表。"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bi_api import config
from bi_api.main import app

EXACT = pd.read_csv(config.PROJECT_ROOT / "data/analysis/p4/p4_b_exact_combinations.csv")
INC = pd.read_csv(config.PROJECT_ROOT / "data/analysis/p4/p4_c_store_sku_incidence.csv")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_exact_combo_counts_match_frozen(client):
    for _, row in EXACT.iterrows():
        body = client.get("/api/v1/stores", params={
            "exact_combo": row.combination,
            "sample_scope": "risk",
            "page_size": 200,
        }).json()
        assert body["meta"]["n"] == int(row.stores), row.combination
        assert len(body["data"]) == int(row.stores)
        assert all(r["exact_combo"] == row.combination for r in body["data"])


def test_exact_combo_invalid_and_conflict(client):
    assert client.get("/api/v1/stores", params={"exact_combo": "缺货"}).status_code == 400
    assert client.get("/api/v1/stores", params={"exact_combo": "不存在组合"}).status_code == 400
    assert client.get("/api/v1/stores", params={
        "exact_combo": "缺货+高零销", "risk_domain": "R4"
    }).status_code == 400
    assert client.get("/api/v1/stores", params={"exact_combo": "A" * 41}).status_code == 400


def test_exact_combo_parameterized(client):
    injected = client.get("/api/v1/stores", params={"exact_combo": "' OR 1=1 --"})
    assert injected.status_code == 400


def test_store_skus_matches_incidence(client):
    expected = INC[INC.store_id == 35]
    body = client.get("/api/v1/stores/35/skus", params={"page_size": 200}).json()
    assert body["meta"]["n"] == len(expected) == 69
    assert len(body["data"]) == 69
    assert {r["product_id"] for r in body["data"]} == set(int(x) for x in expected.product_id)

    for r in body["data"]:
        if r["observed_rows"]:
            assert r["zero_rate"] == pytest.approx(r["zero_days"] / r["observed_rows"])
        assert r["days_present"] == 90


def test_store_skus_flagged_only_and_pagination(client):
    body = client.get("/api/v1/stores/35/skus", params={"flagged_only": "true", "page_size": 200}).json()
    assert body["meta"]["n"] == 6
    assert all(r["is_flagged"] is True for r in body["data"])

    first = client.get("/api/v1/stores/35/skus", params={"page": 1, "page_size": 50}).json()
    second = client.get("/api/v1/stores/35/skus", params={"page": 2, "page_size": 50}).json()
    ids = [r["product_id"] for r in first["data"] + second["data"]]
    assert len(ids) == 69 and len(set(ids)) == 69

    beyond = client.get("/api/v1/stores/35/skus", params={"page": 99, "page_size": 50}).json()
    assert beyond["data"] == [] and beyond["meta"]["n"] == 69


def test_store_skus_sort_whitelist(client):
    body = client.get("/api/v1/stores/35/skus", params={
        "sort": "total_index", "order": "desc", "page_size": 200
    }).json()
    values = [r["total_index"] for r in body["data"]]
    assert all(values[i] >= values[i + 1] for i in range(len(values) - 1))

    assert client.get("/api/v1/stores/35/skus", params={"sort": "drop"}).status_code == 422
    assert client.get("/api/v1/stores/35/skus", params={"order": "sideways"}).status_code == 422


def test_store_skus_404_and_low_sku_store(client):
    assert client.get("/api/v1/stores/999999/skus").status_code == 404

    low = client.get("/api/v1/stores/842/skus", params={"page_size": 200}).json()
    expected = INC[INC.store_id == 842]
    assert low["meta"]["n"] == len(expected) == 9
    assert all(r["is_flagged"] is False for r in low["data"])


def test_store_list_default_unchanged(client):
    assert client.get("/api/v1/stores", params={"sample_scope": "risk", "page_size": 1}).json()["meta"]["n"] == 888
    assert client.get("/api/v1/stores", params={"sample_scope": "all", "page_size": 1}).json()["meta"]["n"] == 898
