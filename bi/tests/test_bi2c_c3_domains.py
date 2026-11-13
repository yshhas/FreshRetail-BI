"""BI-2-C C-3：至少命中组合筛选测试。"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from bi_api import config
from bi_api.main import app

D8B = pd.read_csv(config.PROJECT_ROOT / "data/analysis/p3d/d8b_pairwise_combinations.csv")
PAIRS = D8B[D8B["domain_a"] != D8B["domain_b"]]
NAME_TO_CODE = {
    "缺货": "stockout_domain",
    "持续低销": "R3",
    "高零销": "R4",
    "高波动": "R5",
    "高异常日": "R6",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_all_cross_domain_pairs_match_frozen(client):
    assert len(PAIRS) == 10
    for _, row in PAIRS.iterrows():
        a, b = NAME_TO_CODE[row.domain_a], NAME_TO_CODE[row.domain_b]
        body = client.get("/api/v1/stores", params={
            "domains": f"{a},{b}",
            "sample_scope": "risk",
            "page_size": 200,
        }).json()
        assert body["meta"]["n"] == int(row.stores_at_least), (row.domain_a, row.domain_b)
        assert len(body["data"]) == int(row.stores_at_least)
        assert all(r[a] is True and r[b] is True for r in body["data"])

        reverse = client.get("/api/v1/stores", params={
            "domains": f"{b},{a}", "sample_scope": "risk", "page_size": 1
        }).json()
        assert reverse["meta"]["n"] == int(row.stores_at_least)


def test_domains_invalid_and_conflicts(client):
    assert client.get("/api/v1/stores", params={"domains": "stockout_domain"}).status_code == 400
    assert client.get("/api/v1/stores", params={
        "domains": "stockout_domain,R4,R5"
    }).status_code == 400
    assert client.get("/api/v1/stores", params={
        "domains": "stockout_domain,R4,R4"
    }).status_code == 400
    assert client.get("/api/v1/stores", params={
        "domains": "stockout_domain,stockout_domain"
    }).status_code == 400
    assert client.get("/api/v1/stores", params={"domains": "R7,R4"}).status_code == 400
    assert client.get("/api/v1/stores", params={"domains": "R8,R4"}).status_code == 400
    assert client.get("/api/v1/stores", params={"domains": "r4,stockout_domain"}).status_code == 400
    assert client.get("/api/v1/stores", params={"domains": "unknown,R4"}).status_code == 400


def test_domains_injection_and_mutual_exclusion(client):
    assert client.get("/api/v1/stores", params={
        "domains": "stockout_domain) OR 1=1 --,R4"
    }).status_code == 400
    assert client.get("/api/v1/stores", params={
        "domains": "stockout_domain,R4", "risk_domain": "R4"
    }).status_code == 400
    assert client.get("/api/v1/stores", params={
        "domains": "stockout_domain,R4", "exact_combo": "缺货+高零销"
    }).status_code == 400


def test_empty_domains_and_defaults_unchanged(client):
    assert client.get("/api/v1/stores", params={
        "domains": "", "sample_scope": "risk", "page_size": 1
    }).status_code == 400
    assert client.get("/api/v1/stores", params={"sample_scope": "risk", "page_size": 1}).json()["meta"]["n"] == 888
    assert client.get("/api/v1/stores", params={
        "exact_combo": "缺货+高零销", "sample_scope": "risk", "page_size": 1
    }).json()["meta"]["n"] == 38
