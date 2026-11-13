"""BI-0 查询性能基准（只读；输出 BI 专属结果文件）。"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bi" / "src"))

from bi_api import config, service  # noqa: E402
from bi_api.db import ReadOnlyDB  # noqa: E402


def timed(fn, n=20):
    for _ in range(2):
        fn()
    vals = []
    rows = 0
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        vals.append((time.perf_counter() - t0) * 1000)
        if isinstance(out, tuple) and len(out) == 2:
            data, meta = out
            rows = getattr(meta, "n", 0)
        elif isinstance(out, list):
            rows = len(out)
        elif isinstance(out, str):
            rows = out.count("\n")
        else:
            rows = 1
    return {
        "rows": int(rows),
        "p50_ms": round(statistics.median(vals), 3),
        "p95_ms": round(sorted(vals)[int(len(vals) * 0.95) - 1], 3),
        "min_ms": round(min(vals), 3),
        "max_ms": round(max(vals), 3),
    }


def main() -> None:
    t0 = time.perf_counter()
    db = ReadOnlyDB()
    init_ms = (time.perf_counter() - t0) * 1000
    ops = {
        "view_counts": lambda: db.view_counts(),
        "overview_kpis": service.overview_kpis,
        "trend_90d": lambda: service.trend(),
        "cities": service.cities,
        "stores_page50": lambda: service.stores({"sample_scope": "risk"}, 1, 50),
        "store_detail": lambda: service.store_detail(35),
        "store_groups": service.store_groups,
        "products_50": lambda: service.products(1, 50),
        "risk_exact": lambda: service.risk_combinations("exact"),
        "risk_at_least": lambda: service.risk_combinations("at_least"),
        "export_stores": lambda: service.export_stores_csv({"sample_scope": "risk"}),
    }
    result = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "data_version": config.data_version(),
        "period": config.PERIOD_LABEL,
        "view_init_ms": round(init_ms, 3),
        "views": db.view_counts(),
        "iterations": 20,
        "operations": {},
    }
    for name, fn in ops.items():
        result["operations"][name] = timed(fn)
    target = ROOT / "bi" / "benchmarks" / "benchmark_results.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    db.close()


if __name__ == "__main__":
    main()
