import pytest

from bi_api import freeze, service
from bi_api.db import ReadOnlyDB, ReadOnlyError


def test_freeze_manifest():
    info = freeze.verify_manifest()
    assert info["version"] == "p1-p4-freeze-2026-11-08"
    assert info["contract_version"] == "bi0-contract-v2"
    assert info["files_total"] == 25
    assert info["checked"] == 25
    assert info["amendments"] == 1


def test_manifest_amendment_entries():
    manifest = freeze._load_manifest_strict()
    files = manifest["files"]
    added = {
        "data/analysis/p4/p4_c_store_sku_incidence.csv": ("P4-C", 50000),
        "data/analysis/p2/t8_head_tail.csv": ("P2", 2),
        "data/analysis/p3c/c3_category_penetration.csv": ("P3-C", 32),
    }
    for rel, (stage, rows) in added.items():
        entry = files[rel]
        assert entry["stage"] == stage
        assert entry["rows"] == rows
        assert entry["contract_version"] == "bi0-contract-v2"
        assert entry["dataset_version"] == "p1-p4-freeze-2026-11-08"
        assert entry["purpose"]
        assert freeze.sha256(service.config.PROJECT_ROOT / rel) == entry["sha256"]
    assert len(files) == 22 + len(added)


def test_manifest_rejects_duplicate_keys():
    with pytest.raises(freeze.FreezeError):
        freeze._reject_duplicate_keys([("a", 1), ("a", 2)])


def test_view_counts():
    db = ReadOnlyDB()
    counts = db.view_counts()
    assert counts["v_store"] == 898
    assert counts["v_store_profile"] == 898
    assert counts["v_store_diagnosis"] == 888
    assert counts["v_store_not_applicable"] == 10
    assert counts["v_city"] == 18
    assert counts["v_flagged_sku"] == 117
    assert counts["v_sku_pairs"] == 1237
    assert counts["v_store_groups"] == 16
    assert counts["v_risk_exact"] == 16
    assert counts["v_risk_at_least"] == 10
    assert counts["v_daily"] == 90
    assert counts["v_hour"] == 24
    db.close()


def test_kpis_and_contracts():
    kpis, meta = service.overview_kpis()
    by_key = {k["key"]: k for k in kpis}
    assert by_key["stores"]["value"] == 898
    assert by_key["full_stores"]["value"] == 888
    assert by_key["total_index"]["value"] == pytest.approx(4493660.787, abs=1e-3)
    assert by_key["multi_risk"]["value"] == 132
    assert by_key["flagged_skus"]["value"] == 117
    assert meta.period == "2024-03-28/2024-06-25"
    assert meta.data_version == "p1-p4-freeze-2026-11-08"


def test_city_and_store_contracts():
    cities, meta = service.cities()
    assert len(cities) == 18 and meta.n == 18
    rows, meta = service.stores({"sample_scope": "risk"}, page=1, page_size=5)
    assert len(rows) == 5 and meta.n == 888
    rows, meta = service.stores({"risk_domain": "R1", "sample_scope": "risk"}, page=1, page_size=200)
    assert meta.n == 89
    assert all(r["R1"] is True for r in rows)
    detail, meta = service.store_detail(35)
    assert detail is not None and detail["store_id"] == 35
    assert detail["profile_status"] == "完整档案"


def test_low_sku_store_not_applicable():
    import pandas as pd
    na = pd.read_csv(service.config.PROJECT_ROOT / "data/analysis/p4/p4_b_not_applicable.csv")
    sid = int(na.store_id.iloc[0])
    detail, _ = service.store_detail(sid)
    assert detail is not None
    assert detail["diagnosis_status"] == "不适用"
    assert detail["R1"] is None or pd.isna(detail["R1"])


def test_groups_suppression():
    rows, meta = service.store_groups()
    assert len(rows) == 16
    assert sum(r["stores"] for r in rows) == 888
    assert meta.suppressed is True
    q2g1 = [r for r in rows if r["quadrant"].startswith("Q2") and r["cluster"] == "G1"][0]
    assert q2g1["stores"] == 0 and q2g1["suppressed"] is True
    suppressed = [r for r in rows if r["sample_insufficient"]]
    assert len(suppressed) == 5
    for r in suppressed:
        assert r["n_flagged_median"] is None
        assert r["share_flagged_median"] is None
        assert r["multi_risk_rate"] is None


def test_risk_combinations_and_readonly():
    exact, meta = service.risk_combinations("exact")
    assert len(exact) == 16 and meta.sample_scope == "risk"
    at_least, _ = service.risk_combinations("at_least")
    assert len(at_least) == 10
    db = ReadOnlyDB()
    with pytest.raises(ReadOnlyError):
        db.query_df("DELETE FROM v_store")
    with pytest.raises(ReadOnlyError):
        db.query_df("SELECT 1; SELECT 2")
    with pytest.raises(ReadOnlyError):
        db.query_df("SELECT * FROM read_csv_auto('C:/Windows/win.ini')")
    db.close()


def test_duckdb_external_access_is_blocked():
    import duckdb
    db = ReadOnlyDB()
    with pytest.raises(duckdb.PermissionException):
        db.con.execute("SELECT * FROM read_csv_auto('C:/Windows/win.ini')")
    db.close()


def test_no_eval_reference():
    import pathlib
    root = service.config.BI_ROOT / "src"
    for p in pathlib.Path(root).rglob("*.py"):
        text = p.read_text(encoding="utf-8").lower()
        assert "eval.parquet" not in text
        assert "clean_eval" not in text
