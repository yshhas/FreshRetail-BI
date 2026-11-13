"""P1–P4 冻结文件校验：只读 SHA-256 manifest。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import config

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FreezeError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    out: dict = {}
    for key, value in pairs:
        if key in seen:
            raise FreezeError(f"duplicate manifest key: {key}")
        seen.add(key)
        out[key] = value
    return out


def _load_manifest_strict() -> dict:
    text = config.MANIFEST_PATH.read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def verify_manifest() -> dict:
    manifest = _load_manifest_strict()
    files: dict = manifest.get("files", {})
    errors: list[str] = []
    checked = 0

    for rel, expected in files.items():
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            errors.append(f"invalid path: {rel}")
            continue

        path = config.PROJECT_ROOT / rel
        if not path.exists():
            errors.append(f"missing: {rel}")
            continue

        digest = expected.get("sha256", "")
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            errors.append(f"invalid sha256 field: {rel}")
            continue

        actual = sha256(path)
        if actual != digest:
            errors.append(f"sha256 mismatch: {rel}")
        if "bytes" in expected and path.stat().st_size != expected["bytes"]:
            errors.append(f"bytes mismatch: {rel}")
        checked += 1

    contract_version = manifest.get("contract_version")
    amendments = manifest.get("amendments", [])
    if contract_version:
        added = [r for r, e in files.items() if e.get("contract_version") == contract_version]
        declared = sum(int(a.get("files_added", 0)) for a in amendments)
        if declared and declared != len(added):
            errors.append(f"amendment files_added mismatch: declared={declared}, actual={len(added)}")

    if errors:
        raise FreezeError("; ".join(errors))

    return {
        "version": manifest.get("version"),
        "contract_version": contract_version,
        "files_total": len(files),
        "checked": checked,
        "amendments": len(amendments),
    }
