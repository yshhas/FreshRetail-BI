"""DuckDB 访问层：原始视图、清洗表、派生表导出。"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from . import cleaning
from .io import sql_path


def connect(db_path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("SET threads = 4")
    return con


def create_raw_view(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{sql_path(path)}')")


def query_df(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def export_sql(con: duckdb.DuckDBPyConnection, sql: str, out_path: Path) -> int:
    """把查询结果写成 Parquet，返回行数。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({sql}) TO '{sql_path(out_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return int(con.execute(f"SELECT count(*) FROM read_parquet('{sql_path(out_path)}')").fetchone()[0])


def build_clean_table(con: duckdb.DuckDBPyConnection, raw_view: str, out_path: Path) -> int:
    """原始表 + 派生列，写为独立 Parquet；不触碰原始文件。"""
    return export_sql(con, cleaning.select_clean_sql(raw_view), out_path)
