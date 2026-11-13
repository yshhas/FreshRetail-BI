"""生成 BI-0 只读源文件 freeze manifest（不修改源文件）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_FILES = [
    "data/derived/agg_daily.parquet",
    "data/derived/agg_hour_profile.parquet",
    "data/derived/agg_hour_weekday.parquet",
    "data/analysis/p2/t1_sku_metrics.csv",
    "data/analysis/p2/t9_sku_risk_flags.csv",
    "data/analysis/p2/t4_category_l1.csv",
    "data/analysis/p3/a1_city_metrics.csv",
    "data/analysis/p3d/d5_city_risk.csv",
    "data/analysis/p3d/d6_quadrant_risk.csv",
    "data/analysis/p3d/d7_structure_risk.csv",
    "data/analysis/p3d/d8b_pairwise_combinations.csv",
    "data/analysis/p3d/d9_domain_count.csv",
    "data/analysis/p3d/d13_overall_rates.csv",
    "data/analysis/p4/p4_a_store_profile.csv",
    "data/analysis/p4/p4_b_store_diagnosis.csv",
    "data/analysis/p4/p4_b_not_applicable.csv",
    "data/analysis/p4/p4_b_exact_combinations.csv",
    "data/analysis/p4/p4_c_store_sku_risk_summary.csv",
    "data/analysis/p4/p4_c_flagged_sku_distribution.csv",
    "data/analysis/p4/p4_c_category_risk_profile.csv",
    "data/analysis/p4/p4_c_sku_pair_cooccurrence.csv",
    "data/analysis/p4/p4_c_quadrant_cluster_cross.csv",
]

# BI-0 契约增量（bi0-contract-v2，BI-2 商品 BI 所需资产）
AMENDED_FILES = {
    "data/analysis/p4/p4_c_store_sku_incidence.csv": {
        "rows": 50000,
        "primary_key": ["store_id", "product_id"],
        "stage": "P4-C",
        "purpose": "BI-2 SKU→门店覆盖：覆盖门店列表、城市汇总、SKU 详情下钻",
    },
    "data/analysis/p2/t8_head_tail.csv": {
        "rows": 2,
        "primary_key": ["group"],
        "stage": "P2",
        "purpose": "BI-2 商品总览头部/长尾对比",
    },
    "data/analysis/p3c/c3_category_penetration.csv": {
        "rows": 32,
        "primary_key": ["raw_id"],
        "stage": "P3-C",
        "purpose": "BI-2 一级类别结构的类别渗透率与 rare 标记",
    },
}

DATA_VERSION = "p1-p4-freeze-2026-11-08"
CONTRACT_VERSION = "bi0-contract-v2"



def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = {}
    for rel in BASE_FILES:
        p = ROOT / rel
        if not p.exists():
            raise FileNotFoundError(rel)
        files[rel] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    for rel, meta in AMENDED_FILES.items():
        p = ROOT / rel
        if not p.exists():
            raise FileNotFoundError(rel)
        files[rel] = {
            "sha256": sha256(p),
            "bytes": p.stat().st_size,
            "rows": meta["rows"],
            "primary_key": meta["primary_key"],
            "stage": meta["stage"],
            "dataset_version": DATA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "purpose": meta["purpose"],
        }
    out = {
        "version": DATA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "contract_base": "bi0-contract-v1",
        "period": "2024-03-28/2024-06-25",
        "description": "BI-0 read-only source manifest; P1-P4 Feature Freeze; BI-2 product assets amendment",
        "amendments": [
            {
                "id": "bi0-amend-2026-11-08-bi2-product",
                "contract_version": CONTRACT_VERSION,
                "base_data_version": DATA_VERSION,
                "date": "2026-11-08",
                "stage": "BI-2",
                "files_added": len(AMENDED_FILES),
                "files_modified": 0,
                "note": "保留原 22 项记录与 SHA-256 不变；数据版本不变，仅扩展契约覆盖范围",
            }
        ],
        "files": files,
    }
    target = ROOT / "bi" / "data" / "freeze_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {target} ({len(files)} files)")


if __name__ == "__main__":
    main()
