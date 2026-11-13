from fastapi.testclient import TestClient

from bi_api.main import app


def test_health_and_meta():
    with TestClient(app) as c:
        r = c.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["data_version"] == "p1-p4-freeze-2026-11-08"
        assert body["views"]["v_store"] == 898
        f = c.get("/api/v1/meta/filters").json()
        assert len(f["cities"]) == 18
        assert "Q1 高规模·相对高效率" in f["quadrants"]
        assert set(f["clusters"]) == {"G1", "G2", "G3", "G4"}
        cat = c.get("/api/v1/meta/catalog").json()
        assert any(m["metric_id"] == "D1" for m in cat["metrics"])


def test_kpis_trend_cities():
    with TestClient(app) as c:
        k = c.get("/api/v1/overview/kpis").json()
        assert k["meta"]["period"] == "2024-03-28/2024-06-25"
        by = {x["key"]: x["value"] for x in k["data"]}
        assert by["stores"] == 898 and by["full_stores"] == 888
        assert by["multi_risk"] == 132 and by["flagged_skus"] == 117
        t = c.get("/api/v1/overview/trend?start=2024-04-01&end=2024-04-30").json()
        assert 1 <= len(t["data"]) <= 30
        assert t["meta"]["display_window"] == "2024-04-01/2024-04-30"
        tp = c.get("/api/v1/overview/time-profile").json()["data"]
        assert len(tp["hours"]) == 24 and len(tp["weekday"]) == 7 and len(tp["heatmap"]) == 168
        cities = c.get("/api/v1/cities").json()
        assert len(cities["data"]) == 18


def test_stores_filters_and_detail():
    with TestClient(app) as c:
        r = c.get("/api/v1/stores?sample_scope=risk&page_size=5")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["n"] == 888 and len(body["data"]) == 5
        sc = c.get("/api/v1/stores/scatter").json()
        assert sc["meta"]["n"] == 888 and len(sc["data"]) == 888
        r = c.get("/api/v1/stores?risk_domain=R1&sample_scope=risk&page_size=200")
        body = r.json()
        assert body["meta"]["n"] == 89 and all(x["R1"] is True for x in body["data"])
        assert c.get("/api/v1/stores?risk_domain=bad").status_code == 400
        # 非白名单 sort 回退，不接受 SQL 片段
        assert c.get("/api/v1/stores?sort=total_index%3BDROP").status_code == 200
        d = c.get("/api/v1/stores/35")
        assert d.status_code == 200
        assert d.json()["data"]["store_id"] == 35
        assert c.get("/api/v1/stores/999999").status_code == 404
        import pandas as pd
        na = pd.read_csv("data/analysis/p4/p4_b_not_applicable.csv")
        sid = int(na.store_id.iloc[0])
        low = c.get(f"/api/v1/stores/{sid}")
        assert low.status_code == 200
        assert low.json()["data"]["diagnosis_status"] == "不适用"
        assert low.json()["data"]["R1"] is None


def test_groups_suppressed():
    with TestClient(app) as c:
        r = c.get("/api/v1/stores/groups")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 16
        assert sum(x["stores"] for x in body["data"]) == 888
        q2g1 = [x for x in body["data"] if x["quadrant"].startswith("Q2") and x["cluster"] == "G1"][0]
        assert q2g1["stores"] == 0 and q2g1["suppressed"] is True
        assert sum(1 for x in body["data"] if x["sample_insufficient"]) == 5


def test_products_risk_and_export():
    with TestClient(app) as c:
        p = c.get("/api/v1/products?page_size=5").json()
        assert p["meta"]["n"] == 117 and len(p["data"]) == 5
        assert c.get("/api/v1/products/860").status_code == 200
        exact = c.get("/api/v1/risk/combinations?definition=exact").json()
        assert len(exact["data"]) == 16
        at_least = c.get("/api/v1/risk/combinations?definition=at_least").json()
        assert len(at_least["data"]) == 10
        rs = c.get("/api/v1/risk/summary").json()["data"]
        assert rs["multi_risk"] == 132
        assert rs["flags"] == {"stockout_domain": 154, "R3": 90, "R4": 89,
                               "R5": 89, "R6": 56, "R7": 93, "R8": 90}
        exp = c.get("/api/v1/export/stores.csv?sample_scope=risk")
        assert exp.status_code == 200
        text = exp.text
        assert "# data_version=" in text
        assert "product_id" not in text and "store_sku" not in text
        assert "store_id,city_id" in text


def test_concurrent_reads_are_safe():
    from concurrent.futures import ThreadPoolExecutor
    urls = [
        "/api/v1/overview/kpis", "/api/v1/overview/time-profile",
        "/api/v1/cities", "/api/v1/stores/scatter", "/api/v1/stores/groups",
    ]
    with TestClient(app) as c:
        def hit(url: str) -> int:
            return c.get(url).status_code
        with ThreadPoolExecutor(max_workers=5) as ex:
            assert list(ex.map(hit, urls)) == [200] * len(urls)
