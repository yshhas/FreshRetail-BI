"""文件读写、哈希校验、JSON 输出。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pyarrow.parquet as pq

from . import config


def ensure_dirs() -> None:
    for d in (config.DERIVED_DIR, config.LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file(path: Path, expected: dict) -> dict:
    """核对大小与 SHA256，返回核验结果。"""
    size = os.path.getsize(path)
    digest = sha256_file(path)
    result = {
        "file": path.name,
        "size": size,
        "size_match": size == expected["size"],
        "sha256": digest,
        "hash_match": digest == expected["sha256"],
    }
    if not result["size_match"] or not result["hash_match"]:
        raise ValueError(f"文件校验失败：{result}")
    return result


def read_columns(path: Path, columns: list[str] | None = None):
    return pq.read_table(path, columns=columns).to_pandas()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def sql_path(path: Path) -> str:
    """把 Windows 路径转成 DuckDB SQL 字符串字面量。"""
    return str(path).replace("\\", "/").replace("'", "''")
