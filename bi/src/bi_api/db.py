"""DuckDB 只读视图层：仅查询 P1–P4 冻结 CSV/Parquet。"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import duckdb
import pandas as pd

from . import config


class ReadOnlyError(RuntimeError):
    pass


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|copy|attach|detach|pragma|call|export|import|install|load|truncate|"
    r"read_csv|read_csv_auto|read_parquet|read_json|parquet_scan|glob|httpfs|delta_scan|iceberg_scan)\b",
    re.IGNORECASE,
)


def _csv(path: Path) -> str:
    return f"read_csv_auto('{path.as_posix()}', header=true)"


def _parquet(path: Path) -> str:
    return f"read_parquet('{path.as_posix()}')"


class ReadOnlyDB:
    """内存 DuckDB + 只读视图；不写回任何源文件。"""

    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = Path(data_root or config.DATA_ROOT)
        self.con = duckdb.connect(":memory:")
        self.views: dict[str, str] = {}
        self._lock = threading.RLock()
        self._lock_external_access()
        self._create_views()
        self.con.execute("SET lock_configuration=true")

    def _lock_external_access(self) -> None:
        # 只允许读取 data_root；禁用扩展自动安装/加载与外部网络访问。
        root = self.data_root.resolve().as_posix().replace("'", "''")
        self.con.execute("SET autoinstall_known_extensions=false")
        self.con.execute("SET autoload_known_extensions=false")
        self.con.execute(f"SET allowed_directories=['{root}']")
        self.con.execute("SET enable_external_access=false")

    def _view(self, name: str, sql: str) -> None:
        self.con.execute(f"CREATE VIEW {name} AS {sql}")
        self.views[name] = sql

    def _create_views(self) -> None:
        d = self.data_root / "derived"
        a = self.data_root / "analysis"

        self._view("v_daily", f"SELECT * FROM {_parquet(d / 'agg_daily.parquet')}")
        self._view("v_hour", f"SELECT * FROM {_parquet(d / 'agg_hour_profile.parquet')}")
        self._view("v_hour_weekday", f"SELECT * FROM {_parquet(d / 'agg_hour_weekday.parquet')}")

        p4a = _csv(a / "p4" / "p4_a_store_profile.csv")
        p4b = _csv(a / "p4" / "p4_b_store_diagnosis.csv")
        p4n = _csv(a / "p4" / "p4_b_not_applicable.csv")
        self._view("v_store_profile", f"SELECT * FROM {p4a}")
        self._view("v_store_diagnosis", f"SELECT * FROM {p4b}")
        self._view("v_store_not_applicable", f"SELECT * FROM {p4n}")
        self._view("v_store", f"""
            SELECT a.*,
                   COALESCE(b.diagnosis_status, n.diagnosis_status, '不适用') AS diagnosis_status,
                   b.domain_labels, b.exact_combo, b.structural_notes
            FROM {p4a} a
            LEFT JOIN {p4b} b USING (store_id)
            LEFT JOIN {p4n} n USING (store_id)
        """)

        self._view("v_city", f"""
            SELECT a.city_id, a.store_count, a.city_total_index, a.city_store_day_avg,
                   a.sku_per_store_mean,
                   a.stockout_day_rate AS city_stockout_sku_day_pooled,
                   a.stockout_sku_day_rate AS city_stockout_store_mean,
                   a.stockout_hour_rate AS city_stockout_hour_pooled,
                   a.zero_rate AS city_zero_rate, a.small_city,
                   d.stores_all, d.stores_risk, d.stockout_sku_day_median,
                   d.stockout_hour_median, d.multi_risk,
                   d.multi_risk_rate_risk, d.multi_risk_rate_all
            FROM {_csv(a / 'p3' / 'a1_city_metrics.csv')} a
            LEFT JOIN {_csv(a / 'p3d' / 'd5_city_risk.csv')} d USING (city_id)
        """)

        self._view("v_store_sku_summary", f"SELECT * FROM {_csv(a / 'p4' / 'p4_c_store_sku_risk_summary.csv')}")
        self._view("v_flagged_sku", f"SELECT * FROM {_csv(a / 'p4' / 'p4_c_flagged_sku_distribution.csv')}")
        self._view("v_category_risk", f"SELECT * FROM {_csv(a / 'p4' / 'p4_c_category_risk_profile.csv')}")
        self._view("v_sku_pairs", f"SELECT * FROM {_csv(a / 'p4' / 'p4_c_sku_pair_cooccurrence.csv')}")
        self._view("v_store_groups", f"SELECT * FROM {_csv(a / 'p4' / 'p4_c_quadrant_cluster_cross.csv')}")

        self._view("v_risk_domain", f"SELECT * FROM {_csv(a / 'p3d' / 'd9_domain_count.csv')}")
        self._view("v_risk_exact", f"SELECT * FROM {_csv(a / 'p4' / 'p4_b_exact_combinations.csv')}")
        self._view("v_risk_at_least", f"SELECT * FROM {_csv(a / 'p3d' / 'd8b_pairwise_combinations.csv')} WHERE domain_a <> domain_b")
        self._view("v_risk_quadrant", f"SELECT * FROM {_csv(a / 'p3d' / 'd6_quadrant_risk.csv')}")
        self._view("v_risk_cluster", f"SELECT * FROM {_csv(a / 'p3d' / 'd7_structure_risk.csv')}")
        self._view("v_overall", f"SELECT * FROM {_csv(a / 'p3d' / 'd13_overall_rates.csv')}")

        self._view("v_sku", f"SELECT * FROM {_csv(a / 'p2' / 't1_sku_metrics.csv')}")
        self._view("v_sku_risk", f"SELECT * FROM {_csv(a / 'p2' / 't9_sku_risk_flags.csv')}")
        self._view("v_category", f"SELECT * FROM {_csv(a / 'p2' / 't4_category_l1.csv')}")

        # BI-2-A：商品 BI 只读视图（全部来自 BI-0 v2 冻结清单）
        self._view("v_store_sku", f"SELECT * FROM {_csv(a / 'p4' / 'p4_c_store_sku_incidence.csv')}")
        self._view("v_sku_head_tail", f"SELECT * FROM {_csv(a / 'p2' / 't8_head_tail.csv')}")
        self._view("v_category_penetration", f"SELECT * FROM {_csv(a / 'p3c' / 'c3_category_penetration.csv')}")

    def query_df(self, sql: str, params: list | tuple | None = None) -> pd.DataFrame:
        text = sql.strip()
        if not text:
            raise ReadOnlyError("empty SQL")
        if ";" in text.rstrip(";"):
            raise ReadOnlyError("multiple statements are not allowed")
        core = text.rstrip(";").lstrip()
        if not re.match(r"^(select|with)\b", core, flags=re.IGNORECASE):
            raise ReadOnlyError("only SELECT/CTE queries are allowed")
        if _FORBIDDEN.search(core):
            raise ReadOnlyError("write/DDL keyword is not allowed")
        with self._lock:
            return self.con.execute(sql, params or []).fetchdf()

    def query_one(self, sql: str, params: list | tuple | None = None) -> dict:
        df = self.query_df(sql, params)
        return {} if df.empty else df.iloc[0].to_dict()

    def view_counts(self) -> dict[str, int]:
        with self._lock:
            return {name: int(self.con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
                    for name in sorted(self.views)}

    def close(self) -> None:
        with self._lock:
            self.con.close()
